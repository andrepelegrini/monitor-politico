"""Imagem de compartilhamento (og:image) do perfil ampliado.

O SVG sai dos dados do perfil. A imagem é gerada por um navegador, como arte/compartilhar.svg, porque as
fontes vêm do Google Fonts. Por isso ela é gerada junto com a coleta e vai no pacote de dados, e o build
do site só copia o arquivo.

Uso: python -m monitor_politico.compartilhar  (precisa de pip install ".[imagens]" e do Chromium do Playwright)
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

import httpx

from monitor_politico import perfis
from monitor_politico.models import Deputado, Senador

LARGURA, ALTURA = 1200, 630
COLUNAS, LARGURA_DA_COLUNA = 4, 275
DEPUTADOS_PADRAO = Path("data/deputados.json")
SENADORES_PADRAO = Path("data/senadores.json")
PASTA_SENADO = perfis.SAIDA_PADRAO / "senado"
NOME_DA_IMAGEM = "{id}-compartilhar.jpg"


def numeros_do_perfil(visao: dict[str, Any]) -> list[tuple[str, str]]:
    """Os mesmos números do topo da página, em texto curto, cada um com o que mede."""
    numeros: list[tuple[str, str]] = []
    plenario = visao.get("plenario")
    if plenario:
        numeros.append((perfis.numero(plenario["votos_registrados"]), f"votos em {perfis.numero(plenario['votacoes_nominais'])} votações nominais"))
        if plenario.get("participacao"):
            total = plenario["participacao"]["total"]
            numeros.append((perfis.numero(total["votou"]), f"participações, em {perfis.numero(total['votacoes'])} votações nominais"))
        else:
            total = plenario["presenca"]["total"]
            numeros.append((perfis.numero(total["presencas"]), f"dias com presença, de {perfis.numero(total['dias'])} com sessão"))
    dinheiro = visao.get("dinheiro")
    if dinheiro and dinheiro["cota"]["total"]:
        numeros.append((perfis.milhoes(dinheiro["cota"]["total"]), "em cota parlamentar no mandato"))
    propostas = visao.get("propostas")
    if propostas:
        normas = len(propostas["normas"])
        sujeito = "proposta virou" if normas == 1 else "propostas viraram"
        numeros.append((str(normas), f"{sujeito} {propostas['palavra_norma']} desde {propostas['ano_inicial']}, {len(propostas['normas_principais'])} de autoria principal"))
    return numeros


def _quebrar(texto: str, limite: int = 30) -> list[str]:
    linhas, atual = [], ""
    for palavra in texto.split():
        if atual and len(atual) + 1 + len(palavra) > limite:
            linhas.append(atual)
            atual = palavra
        else:
            atual = f"{atual} {palavra}".strip()
    return linhas + [atual] if atual else linhas


def svg_do_perfil(deputado: Any, visao: dict[str, Any], foto_base64: Optional[str] = None) -> str:
    senado = visao.get("casa") == "senado"
    foto = (
        f'<image href="data:image/jpeg;base64,{foto_base64}" x="60" y="60" width="210" height="280" preserveAspectRatio="xMidYMid slice" clip-path="url(#recorte)"/>'
        if foto_base64 else '<rect x="60" y="60" width="210" height="280" rx="10" fill="#F0EBE2"/>'
    )
    blocos = []
    for indice, (valor, rotulo) in enumerate(numeros_do_perfil(visao)[:COLUNAS]):
        x = 60 + indice * LARGURA_DA_COLUNA
        linhas = "".join(f'<tspan x="{x}" dy="{0 if i == 0 else 27}">{escape(linha)}</tspan>' for i, linha in enumerate(_quebrar(rotulo, 26)[:3]))
        blocos.append(
            f'<text class="numero" x="{x}" y="428" font-size="34" fill="#26221E">{escape(valor)}</text>'
            f'<text class="texto" x="{x}" y="470" font-size="21" fill="#62594F">{linhas}</text>'
        )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{LARGURA}" height="{ALTURA}" viewBox="0 0 {LARGURA} {ALTURA}">
  <style>
    @import url("https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,480&amp;family=Instrument+Sans:wght@400;500;700&amp;display=swap");
    .titulo, .numero {{ font-family: Fraunces, Georgia, serif; font-weight: 480; }}
    .titulo {{ letter-spacing: -2px; }}
    .texto {{ font-family: "Instrument Sans", system-ui, sans-serif; }}
    .rotulo {{ font-family: "Instrument Sans", system-ui, sans-serif; font-weight: 700; letter-spacing: 2px; }}
  </style>
  <defs><clipPath id="recorte"><rect x="60" y="60" width="210" height="280" rx="10"/></clipPath></defs>
  <rect width="{LARGURA}" height="{ALTURA}" fill="#FAF8F4"/>
  {foto}
  <text class="rotulo" x="310" y="104" font-size="20" fill="#B75131">{"SENADO FEDERAL" if senado else "CÂMARA DOS DEPUTADOS"}</text>
  <text class="titulo" x="310" y="190" font-size="{_tamanho_do_nome(deputado.nome)}" fill="#26221E">{escape(deputado.nome)}</text>
  <text class="texto" x="310" y="248" font-size="30" fill="#62594F">{escape(deputado.partido)}-{escape(deputado.uf)}</text>
  <text class="texto" x="310" y="302" font-size="24" font-weight="500" fill="#513C2D">Na Galeria</text>
  <rect x="60" y="358" width="1080" height="1" fill="#D9D2C8"/>
  {"".join(blocos)}
  <text class="texto" x="60" y="602" font-size="19" fill="#62594F">Dados oficiais {"do Senado" if senado else "da Câmara"}, do TSE e do Portal da Transparência. Coleta em {visao_data(visao)}.</text>
</svg>
"""


def _tamanho_do_nome(nome: str) -> int:
    return 76 if len(nome) <= 22 else 58


def visao_data(visao: dict[str, Any]) -> str:
    ano, mes, dia = visao["coleta_local"].split("-")
    return f"{dia}/{mes}/{ano}"


def gerar_imagens(pasta: Path = perfis.SAIDA_PADRAO, deputados_json: Path = DEPUTADOS_PADRAO, senado: bool = False) -> int:
    """Um navegador só, reaproveitado: abrir um por imagem levaria horas com 513 deputados."""
    from playwright.sync_api import sync_playwright

    doc = json.loads(deputados_json.read_text(encoding="utf-8"))
    deputados = {d["id"]: (Senador if senado else Deputado).de_dict(d) for d in doc["senadores" if senado else "deputados"]}
    disco = perfis.PerfisEmDisco(pasta)
    geradas = 0
    with sync_playwright() as playwright, httpx.Client(timeout=30, follow_redirects=True) as http:
        navegador = playwright.chromium.launch()
        pagina = navegador.new_page(viewport={"width": LARGURA, "height": ALTURA})
        for id_, deputado in deputados.items():
            documento = disco.get(id_)
            if documento is None:
                continue
            foto = None
            if deputado.url_foto:
                try:
                    foto = base64.b64encode(http.get(deputado.url_foto).raise_for_status().content).decode()
                except httpx.HTTPError as erro:
                    print(f"aviso: foto de {id_} indisponível ({erro})", file=sys.stderr)
            pagina.set_content(f"<!doctype html><html><body style='margin:0'>{svg_do_perfil(deputado, perfis.visao(documento), foto)}</body></html>", wait_until="load")
            pagina.evaluate("document.fonts.ready")
            pagina.screenshot(path=str(pasta / NOME_DA_IMAGEM.format(id=id_)), type="jpeg", quality=85)
            geradas += 1
        navegador.close()
    return geradas


if __name__ == "__main__":
    print(f"{gerar_imagens()} imagens geradas")
    print(f"{gerar_imagens(PASTA_SENADO, SENADORES_PADRAO, senado=True)} imagens de senadores geradas")

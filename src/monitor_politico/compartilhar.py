"""Imagem de compartilhamento (og:image) do perfil ampliado.

O SVG sai dos dados do perfil. O PNG é gerado por um navegador, como arte/compartilhar.svg, porque as
fontes vêm do Google Fonts. Por isso o arquivo é gerado junto com a coleta e guardado em data/perfis/,
e o build do site só copia o PNG.

Uso: python -m monitor_politico.compartilhar  (precisa da CLI do Playwright com o Chromium instalado)
"""

from __future__ import annotations

import base64
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

import httpx

from monitor_politico import perfis
from monitor_politico.models import Deputado

LARGURA, ALTURA = 1200, 630
COLUNAS, LARGURA_DA_COLUNA = 4, 275
DEPUTADOS_PADRAO = Path("data/deputados.json")
NOME_DA_IMAGEM = "{id}-compartilhar.png"


def numeros_do_perfil(visao: dict[str, Any]) -> list[tuple[str, str]]:
    """Os mesmos números do topo da página, em texto curto, cada um com o que mede."""
    numeros: list[tuple[str, str]] = []
    plenario = visao.get("plenario")
    if plenario:
        numeros.append((perfis.numero(plenario["votos_registrados"]), f"votos em {perfis.numero(plenario['votacoes_nominais'])} votações nominais"))
        total = plenario["presenca"]["total"]
        numeros.append((perfis.numero(total["presencas"]), f"dias com presença, de {perfis.numero(total['dias'])} com sessão"))
    dinheiro = visao.get("dinheiro")
    if dinheiro:
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


def svg_do_perfil(deputado: Deputado, visao: dict[str, Any], foto_base64: Optional[str] = None) -> str:
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
  <text class="rotulo" x="310" y="104" font-size="20" fill="#B75131">CÂMARA DOS DEPUTADOS</text>
  <text class="titulo" x="310" y="190" font-size="{_tamanho_do_nome(deputado.nome)}" fill="#26221E">{escape(deputado.nome)}</text>
  <text class="texto" x="310" y="248" font-size="30" fill="#62594F">{escape(deputado.partido)}-{escape(deputado.uf)}</text>
  <text class="texto" x="310" y="302" font-size="24" font-weight="500" fill="#513C2D">Monitor Político</text>
  <rect x="60" y="358" width="1080" height="1" fill="#D9D2C8"/>
  {"".join(blocos)}
  <text class="texto" x="60" y="602" font-size="19" fill="#62594F">Dados oficiais da Câmara, do TSE e do Portal da Transparência. Coleta em {visao_data(visao)}.</text>
</svg>
"""


def _tamanho_do_nome(nome: str) -> int:
    return 76 if len(nome) <= 22 else 58


def visao_data(visao: dict[str, Any]) -> str:
    ano, mes, dia = visao["coleta_local"].split("-")
    return f"{dia}/{mes}/{ano}"


def gerar_png(svg: str, destino: Path) -> None:
    with tempfile.TemporaryDirectory() as pasta:
        entrada = Path(pasta) / "perfil.svg"
        entrada.write_text(svg, encoding="utf-8")
        subprocess.run(
            ["playwright", "screenshot", "--browser=chromium", f"--viewport-size={LARGURA},{ALTURA}", "--wait-for-timeout=2500", entrada.as_uri(), str(destino)],
            check=True, capture_output=True,
        )


if __name__ == "__main__":
    deputados = {d["id"]: Deputado.de_dict(d) for d in json.loads(DEPUTADOS_PADRAO.read_text(encoding="utf-8"))["deputados"]}
    for id_parlamentar, documento in perfis.ler_perfis(perfis.SAIDA_PADRAO).items():
        deputado = deputados[id_parlamentar]
        conteudo_foto = None
        if deputado.url_foto:
            resposta = httpx.get(deputado.url_foto, timeout=30, follow_redirects=True)
            resposta.raise_for_status()
            conteudo_foto = base64.b64encode(resposta.content).decode()
        saida = perfis.SAIDA_PADRAO / NOME_DA_IMAGEM.format(id=id_parlamentar)
        gerar_png(svg_do_perfil(deputado, perfis.visao(documento), conteudo_foto), saida)
        print(f"Imagem gerada em {saida}")

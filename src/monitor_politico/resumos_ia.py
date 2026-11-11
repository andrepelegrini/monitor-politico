"""Resumos em linguagem simples das proposições, gerados pelo Claude a partir do
texto oficial (o inteiro teor, quando disponível, mais a ementa).

Para economizar, vai só o texto extraído do PDF, que custa uma fração do PDF como documento. O PDF
inteiro só é enviado quando não tem texto (digitalizado). O consumo de cada resumo fica registrado.

Cada resumo é gerado uma vez e guardado em data/resumos.json com a impressão
digital da fonte; só é refeito quando a ementa ou o texto mudam. Uma falha
numa proposição só deixa aquela sem resumo: o site mostra a ementa oficial.

Uso: python -m monitor_politico.resumos_ia [congresso.json] [resumos.json]
     python -m monitor_politico.resumos_ia comparar [saida.json]   compara modelos em 8 proposições
Requer ANTHROPIC_API_KEY e o extra `ia` (pip install ".[ia]"). O modelo pode ser trocado com a
variável RESUMOS_MODELO.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

CONGRESSO_PADRAO = Path("data/congresso.json")
SAIDA_PADRAO = Path("data/resumos.json")
# Sonnet 5.5: no teste de 11/11/2026 (8 proposições), resumos equivalentes aos do Opus pela metade do custo.
MODELO = os.environ.get("RESUMOS_MODELO") or "claude-sonnet-5-5"
ESFORCO = "low"  # resumir um texto não pede raciocínio longo, e o raciocínio é cobrado como saída
MIN_CARACTERES_POR_PAGINA = 200  # abaixo disso, o PDF é tratado como digitalizado
# Dólares por milhão de tokens (entrada, saída), para a estimativa no fim de cada execução.
PRECOS = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
# Modelos que aceitam a reserva automática do servidor quando recusam um pedido.
COM_RESERVA = {"claude-opus-5-5", "claude-sonnet-5-5"}
MAX_POR_EXECUCAO = 30  # teto de custo por coleta; o que sobrar fica para a próxima
MAX_PDF_BYTES = 30 * 1024 * 1024  # a API aceita até 32 MB por requisição
LIMITES = {"titulo": 90, "o_que_muda": 900, "quem_e_afetado": 400}
# Muda quando a instrução muda, para refazer os resumos com a regra nova.
VERSAO_INSTRUCOES = 2

INSTRUCOES = """\
Você escreve resumos de proposições legislativas brasileiras para um site público \
e apartidário que reproduz informações oficiais da Câmara e do Senado, sem avaliação \
ou opinião. Os leitores são cidadãos sem formação jurídica.

Com base no texto oficial anexado e na ementa, produza:
- titulo: um título curto (até 80 caracteres) que diga do que trata a proposição, \
em linguagem simples. Sem o número da proposição.
- o_que_muda: de 2 a 4 frases curtas sobre o que a proposição muda ou cria, com os \
números e prazos concretos que estiverem no texto (valores, limites, datas), em no \
máximo 600 caracteres. A primeira frase deve resumir sozinha a mudança principal, em \
até 200 caracteres, porque ela aparece sozinha na página inicial do site.
- quem_e_afetado: 1 ou 2 frases sobre quem é diretamente afetado, em no máximo 300 \
caracteres.

Regras:
- Descreva o que o texto diz; não avalie se é bom ou ruim, não atribua intenções \
e não use adjetivos valorativos.
- Use só informações do texto e da ementa. Se o anexo não contiver o texto da \
proposição (por exemplo, só um ofício), baseie-se na ementa e não invente detalhes.
- Fale da proposição, não do documento: não comente o anexo, a ementa ou diferenças \
entre eles. Se faltar informação, escreva só o que se sabe.
- Escreva em português do Brasil, frases diretas, sem jargão; explique termos \
técnicos inevitáveis.
"""

ESQUEMA = {
    "type": "object",
    "properties": {
        "titulo": {"type": "string"},
        "o_que_muda": {"type": "string"},
        "quem_e_afetado": {"type": "string"},
    },
    "required": ["titulo", "o_que_muda", "quem_e_afetado"],
    "additionalProperties": False,
}


class ResumoInvalido(RuntimeError):
    pass


def _frases_que_cabem(texto: str, limite: int) -> str:
    escolhido = ""
    for frase in re.split(r"(?<=[.!?])\s+", texto):
        if len(escolhido) + len(frase) + 1 > limite:
            break
        escolhido = f"{escolhido} {frase}".strip()
    return escolhido


def impressao_digital(prop: dict[str, Any]) -> str:
    """Muda quando a ementa ou o documento de origem mudam, o que pede um novo resumo."""
    fonte = json.dumps([prop.get("ementa"), prop.get("url_inteiro_teor"), VERSAO_INSTRUCOES], ensure_ascii=False)
    return hashlib.sha256(fonte.encode("utf-8")).hexdigest()[:16]


def baixar_pdf(url: Optional[str], http: httpx.Client, tentativas: int = 3) -> Optional[bytes]:
    """O PDF do inteiro teor, ou None se não houver, não for PDF ou passar do limite."""
    if not url:
        return None
    for tentativa in range(tentativas):
        try:
            resp = http.get(url, follow_redirects=True, timeout=60)
            if resp.status_code >= 500 and tentativa < tentativas - 1:
                time.sleep(2**tentativa)
                continue
            resp.raise_for_status()
        except httpx.TransportError:
            if tentativa == tentativas - 1:
                return None
            time.sleep(2**tentativa)
            continue
        except httpx.HTTPStatusError:
            return None
        if "pdf" not in resp.headers.get("content-type", "") or len(resp.content) > MAX_PDF_BYTES:
            return None
        return resp.content
    return None


def texto_do_pdf(pdf: Optional[bytes]) -> Optional[str]:
    """Texto do PDF, ou None se ele for digitalizado (pouco ou nenhum texto) ou não abrir."""
    if not pdf:
        return None
    try:
        from pypdf import PdfReader

        leitor = PdfReader(io.BytesIO(pdf))
        texto = "\n".join(pagina.extract_text() or "" for pagina in leitor.pages).strip()
    except Exception:  # um PDF que a biblioteca não lê volta a ir inteiro
        return None
    if len(texto) < MIN_CARACTERES_POR_PAGINA * max(len(leitor.pages), 1):
        return None
    return texto


def _mensagem(prop: dict[str, Any], pdf: Optional[bytes], texto: Optional[str] = None) -> list[dict[str, Any]]:
    dados = "\n".join(
        f"{rotulo}: {valor}"
        for rotulo, valor in (
            ("Proposição", f"{prop['chave']} ({prop.get('tipo') or 'tipo não informado'})"),
            ("Autoria", ", ".join(prop.get("autores") or []) or None),
            ("Ementa oficial", prop.get("ementa")),
        )
        if valor
    )
    conteudo: list[dict[str, Any]] = []
    if texto:
        conteudo.append({"type": "text", "text": f"<texto_oficial>\n{texto}\n</texto_oficial>"})
    elif pdf:
        conteudo.append({
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": base64.standard_b64encode(pdf).decode()},
            "title": f"Texto oficial de {prop['chave']}",
        })
    else:
        dados += "\n\nO texto integral não está disponível; resuma a partir da ementa, sem acrescentar detalhes."
    conteudo.append({"type": "text", "text": dados})
    return [{"role": "user", "content": conteudo}]


def gerar(
    cliente: Any, prop: dict[str, Any], pdf: Optional[bytes], texto: Optional[str] = None,
    modelo: str = MODELO, esforco: str = ESFORCO,
) -> dict[str, Any]:
    pedido: dict[str, Any] = {
        "model": modelo,
        "max_tokens": 16000,
        "output_config": {"effort": esforco, "format": {"type": "json_schema", "schema": ESQUEMA}},
        "system": INSTRUCOES,
        "messages": _mensagem(prop, pdf, texto),
    }
    if modelo in COM_RESERVA:
        # Se o modelo recusar, a API refaz o pedido no modelo de reserva.
        pedido.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    resposta = cliente.beta.messages.create(**pedido)
    if resposta.stop_reason != "end_turn":
        raise ResumoInvalido(f"resposta interrompida ({resposta.stop_reason})")
    texto = next((b.text for b in resposta.content if b.type == "text"), None)
    if not texto:
        raise ResumoInvalido("resposta sem texto")
    dados = json.loads(texto)
    resumo = {}
    for campo, limite in LIMITES.items():
        valor = " ".join(str(dados.get(campo) or "").split())
        if not valor:
            raise ResumoInvalido(f"campo vazio: {campo}")
        if len(valor) > limite:
            # Um texto longo demais perde as últimas frases, e não o resumo inteiro. O título não se corta.
            cortado = _frases_que_cabem(valor, limite) if campo != "titulo" else ""
            if not cortado:
                raise ResumoInvalido(f"{campo} longo demais ({len(valor)} caracteres)")
            valor = cortado
        resumo[campo] = valor
    uso = getattr(resposta, "usage", None)
    resumo["uso"] = {
        "modelo": getattr(resposta, "model", None) or modelo,
        "entrada": getattr(uso, "input_tokens", 0) or 0,
        "saida": getattr(uso, "output_tokens", 0) or 0,
    }
    return resumo


def custo(uso: dict[str, Any]) -> float:
    entrada, saida = PRECOS.get(uso["modelo"], PRECOS["claude-opus-5-5"])
    return (uso["entrada"] * entrada + uso["saida"] * saida) / 1_000_000


def atualizar(
    doc_congresso: dict[str, Any],
    saida: Path,
    cliente: Any,
    http: httpx.Client,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
    maximo: int = MAX_POR_EXECUCAO,
) -> dict[str, Any]:
    existentes = json.loads(saida.read_text(encoding="utf-8"))["resumos"] if saida.exists() else {}
    pendentes = [
        p for p in doc_congresso["proposicoes"].values()
        if existentes.get(p["chave"], {}).get("fonte_hash") != impressao_digital(p)
    ]
    # Primeiro as que estão na lista de votadas ou na pauta mais recentes (ordem do JSON é por chave).
    pendentes.sort(key=lambda p: max((v["data_hora"] for v in p["votacoes"]), default=""), reverse=True)
    if len(pendentes) > maximo:
        avisar(f"{len(pendentes) - maximo} proposições ficam para a próxima execução (limite de {maximo})")

    gerados, gasto = 0, 0.0
    for prop in pendentes[:maximo]:
        pdf = baixar_pdf(prop.get("url_inteiro_teor"), http)
        texto = texto_do_pdf(pdf)
        try:
            resumo = gerar(cliente, prop, pdf, texto)
        except Exception as erro:  # uma proposição não pode derrubar as outras
            avisar(f"{prop['chave']}: resumo não gerado ({type(erro).__name__}: {erro})")
            continue
        existentes[prop["chave"]] = {
            **resumo,
            "fonte": "texto integral" if pdf else "ementa",
            "entrada": "texto" if texto else "pdf" if pdf else "ementa",
            "fonte_hash": impressao_digital(prop),
            "modelo": resumo["uso"]["modelo"],
            "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        gasto += custo(resumo["uso"])
        gerados += 1

    doc = {"resumos": dict(sorted(existentes.items()))}
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{gerados} resumos gerados, {len(pendentes[:maximo]) - gerados} falharam; {len(existentes)} no total")
    print(f"Custo estimado desta execução: US$ {gasto:.2f}")
    return doc


# Teste de modelos: as mesmas proposições em cada configuração, sem mexer em data/resumos.json.
AMOSTRA = ("PEC 18/2025", "PEC 221/2019", "PLP 186/2026", "PLP 281/2019", "PL 6461/2019", "PDL 934/2025", "PL 5608/2023", "MPV 1370/2026")
CONFIGURACOES = (("claude-opus-5-5", "low"), ("claude-sonnet-5-5", "low"), ("claude-haiku-5-5", "low"))


def comparar(doc_congresso: dict[str, Any], cliente: Any, http: httpx.Client, chaves: tuple[str, ...] = AMOSTRA) -> list[dict[str, Any]]:
    linhas = []
    for chave in chaves:
        prop = doc_congresso["proposicoes"].get(chave)
        if prop is None:
            continue
        pdf = baixar_pdf(prop.get("url_inteiro_teor"), http)
        texto = texto_do_pdf(pdf)
        for modelo, esforco in CONFIGURACOES:
            try:
                resumo = gerar(cliente, prop, pdf, texto, modelo=modelo, esforco=esforco)
                linhas.append({"chave": chave, "modelo": modelo, "esforco": esforco, **resumo, "custo": round(custo(resumo["uso"]), 4)})
            except Exception as erro:
                linhas.append({"chave": chave, "modelo": modelo, "esforco": esforco, "erro": f"{type(erro).__name__}: {erro}"})
            print(f"{chave} · {modelo}: {linhas[-1].get('custo', linhas[-1].get('erro'))}", flush=True)
    return linhas


if __name__ == "__main__":
    import anthropic  # só aqui: o build do site não precisa do SDK

    with httpx.Client(headers={"User-Agent": "monitor-politico"}) as http:
        if sys.argv[1:2] == ["comparar"]:
            destino = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("comparacao-resumos.json")
            resultado = comparar(json.loads(CONGRESSO_PADRAO.read_text(encoding="utf-8")), anthropic.Anthropic(), http)
            destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else CONGRESSO_PADRAO
            destino = Path(sys.argv[2]) if len(sys.argv) > 2 else SAIDA_PADRAO
            atualizar(json.loads(entrada.read_text(encoding="utf-8")), destino, anthropic.Anthropic(), http)

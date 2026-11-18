"""Votações por área: cada proposição votada no Plenário ganha de 1 a 3 assuntos de uma lista
fechada, agrupados em nove áreas, mais a "Rotina do Congresso".

A classificação é feita pelo Claude a partir da ementa e do nome popular (sem o PDF, por isso custa
centavos) e fica guardada em data/areas.json. Só é refeita quando a ementa muda ou quando a lista de
assuntos muda (VERSAO). Uma correção manual se faz pondo "manual": true na entrada: ela nunca é
sobrescrita.

Uso: python -m monitor_politico.areas    requer ANTHROPIC_API_KEY e o extra `ia`.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from monitor_politico.resumos_ia import COM_RESERVA, CONGRESSO_PADRAO, HISTORICO_PADRAO, custo

SAIDA_PADRAO = Path("data/areas.json")
MODELO = os.environ.get("AREAS_MODELO") or "claude-sonnet-5-5"
ESFORCO = "low"
POR_PEDIDO = 40  # proposições por chamada
MAX_POR_EXECUCAO = 1200  # cabe o histórico inteiro: só ementas, cerca de US$ 1
# Muda quando a lista de assuntos ou a instrução mudam, para refazer as classificações.
VERSAO = 1

AREAS: list[dict[str, Any]] = [
    {"slug": "economia", "nome": "Economia e impostos", "descricao": "Impostos, contas públicas, empresas, crédito e consumo.",
     "assuntos": ["Reforma tributária", "Impostos e contribuições", "Orçamento e regras fiscais", "Empresas, crédito e dívidas", "Consumidor", "Apostas e jogos"]},
    {"slug": "trabalho", "nome": "Trabalho, previdência e programas sociais", "descricao": "Emprego, salário, aposentadoria e assistência social.",
     "assuntos": ["Trabalho e emprego", "Salário mínimo", "Previdência e aposentadoria", "Programas sociais"]},
    {"slug": "saude", "nome": "Saúde", "descricao": "SUS, atendimento, medicamentos e vacinas.",
     "assuntos": ["SUS e atendimento", "Medicamentos e vacinas"]},
    {"slug": "educacao", "nome": "Educação, cultura e esporte", "descricao": "Escolas, universidades, pesquisa, cultura e esporte.",
     "assuntos": ["Escolas e educação básica", "Universidades e pesquisa", "Cultura", "Esporte"]},
    {"slug": "seguranca", "nome": "Segurança e justiça", "descricao": "Crimes e penas, polícias, armas, drogas e defesa nacional.",
     "assuntos": ["Crimes e penas", "Polícias e segurança pública", "Armas de fogo", "Drogas", "Forças Armadas e defesa"]},
    {"slug": "direitos", "nome": "Direitos e grupos", "descricao": "Mulheres, crianças, pessoas com deficiência, pessoas idosas e povos indígenas.",
     "assuntos": ["Mulheres", "Crianças e adolescentes", "Pessoas com deficiência", "Pessoas idosas", "Povos indígenas e quilombolas"]},
    {"slug": "ambiente", "nome": "Meio ambiente e campo", "descricao": "Clima, florestas, agricultura, pesca e desastres.",
     "assuntos": ["Meio ambiente e clima", "Agricultura e pesca", "Desastres e calamidades"]},
    {"slug": "infraestrutura", "nome": "Infraestrutura e cidades", "descricao": "Transporte, energia, moradia, saneamento e telecomunicações.",
     "assuntos": ["Transporte e trânsito", "Energia e mineração", "Moradia e saneamento", "Internet e telecomunicações"]},
    {"slug": "estado", "nome": "Estado e política", "descricao": "Servidores, órgãos públicos, Justiça, eleições e o funcionamento do Congresso.",
     "assuntos": ["Servidores e órgãos públicos", "Justiça e tribunais", "Eleições e partidos", "Emendas parlamentares", "Funcionamento do Congresso"]},
]
OUTROS = "Outros assuntos"
ROTINA: dict[str, Any] = {
    "slug": "rotina", "nome": "Rotina do Congresso",
    "descricao": "Acordos internacionais, homenagens, créditos do orçamento e outros projetos de rotina.",
    "assuntos": ["Acordos internacionais", "Homenagens e datas", "Créditos orçamentários", OUTROS],
}
ASSUNTOS = [a for area in AREAS + [ROTINA] for a in area["assuntos"]]

INSTRUCOES = f"""\
Você classifica proposições legislativas brasileiras votadas no Plenário da Câmara ou do Senado \
para um site público e apartidário. Para cada proposição, escolha de 1 a 3 assuntos da lista, \
o mais central primeiro. Use só assuntos da lista, escritos exatamente como nela.

Lista de assuntos, por área:
{chr(10).join(f"- {area['nome']}: {'; '.join(area['assuntos'])}" for area in AREAS + [ROTINA])}

Regras:
- Classifique pelo efeito prático da proposição, não pela lei que ela altera.
- "Créditos orçamentários": abertura de crédito extraordinário, especial ou suplementar.
- "Acordos internacionais": aprovação de tratados, acordos, convenções e adesões a organismos.
- "Homenagens e datas": nomes de obras, datas comemorativas, títulos, inscrições no Livro dos Heróis.
- Estas três só valem para esses casos de rotina; se a proposição tem um efeito substantivo, \
use também o assunto desse efeito.
- "{OUTROS}": só quando nenhum outro assunto da lista serve.
- Não avalie a proposição; apenas classifique.
"""

ESQUEMA = {
    "type": "object",
    "properties": {
        "classificacoes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chave": {"type": "string"},
                    "assuntos": {"type": "array", "items": {"type": "string", "enum": ASSUNTOS}},
                },
                "required": ["chave", "assuntos"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["classificacoes"],
    "additionalProperties": False,
}


def impressao_digital(prop: dict[str, Any]) -> str:
    fonte = json.dumps([prop.get("ementa"), prop.get("apelido"), VERSAO], ensure_ascii=False)
    return hashlib.sha256(fonte.encode("utf-8")).hexdigest()[:16]


def _linha(prop: dict[str, Any]) -> str:
    partes = [f"[{prop['chave']}] {prop.get('tipo') or ''}".strip()]
    if prop.get("apelido") and prop["apelido"] != prop.get("ementa"):
        partes.append(f"Nome: {prop['apelido']}")
    partes.append(f"Ementa: {prop.get('ementa') or ''}")
    return "\n".join(partes)


def classificar(cliente: Any, props: list[dict[str, Any]], modelo: str = MODELO) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Os assuntos de cada proposição do lote, já validados, e o consumo da chamada."""
    pedido: dict[str, Any] = {
        "model": modelo,
        "max_tokens": 16000,
        "output_config": {"effort": ESFORCO, "format": {"type": "json_schema", "schema": ESQUEMA}},
        "system": INSTRUCOES,
        "messages": [{"role": "user", "content": "\n\n".join(_linha(p) for p in props)}],
    }
    if modelo in COM_RESERVA:
        pedido.update(betas=["server-side-fallback-2026-07-01"], fallbacks="default")
    resposta = cliente.beta.messages.create(**pedido)
    if resposta.stop_reason != "end_turn":
        raise RuntimeError(f"resposta interrompida ({resposta.stop_reason})")
    texto = next((b.text for b in resposta.content if b.type == "text"), None)
    if not texto:
        raise RuntimeError("resposta sem texto")
    pedidas = {p["chave"] for p in props}
    resultado: dict[str, list[str]] = {}
    for item in json.loads(texto)["classificacoes"]:
        assuntos = list(dict.fromkeys(a for a in item["assuntos"] if a in ASSUNTOS))[:3]
        if item["chave"] in pedidas and assuntos:
            resultado[item["chave"]] = assuntos
    uso = getattr(resposta, "usage", None)
    return resultado, {
        "modelo": getattr(resposta, "model", None) or modelo,
        "entrada": getattr(uso, "input_tokens", 0) or 0,
        "saida": getattr(uso, "output_tokens", 0) or 0,
    }


def votadas(*docs: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    """As proposições com alguma votação, das coletas diária e semanal (a diária prevalece)."""
    todas: dict[str, dict[str, Any]] = {}
    for doc in docs:
        todas.update((doc or {}).get("proposicoes") or {})
    return [p for p in todas.values() if p.get("votacoes")]


def ler(caminho: Path = SAIDA_PADRAO) -> dict[str, Any]:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {"classificacoes": {}}


def atualizar(
    props: Iterable[dict[str, Any]],
    saida: Path,
    cliente: Any,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
    maximo: int = MAX_POR_EXECUCAO,
    por_pedido: int = POR_PEDIDO,
) -> dict[str, Any]:
    existentes = ler(saida)["classificacoes"]
    pendentes = [
        p for p in props
        if not existentes.get(p["chave"], {}).get("manual") and existentes.get(p["chave"], {}).get("fonte_hash") != impressao_digital(p)
    ]
    if len(pendentes) > maximo:
        avisar(f"{len(pendentes) - maximo} proposições ficam para a próxima execução (limite de {maximo})")
    pendentes = pendentes[:maximo]
    feitas, gasto = 0, 0.0
    for inicio in range(0, len(pendentes), por_pedido):
        lote = pendentes[inicio:inicio + por_pedido]
        try:
            resultado, uso = classificar(cliente, lote)
        except Exception as erro:  # um lote com problema não derruba os outros
            avisar(f"lote {inicio // por_pedido + 1}: não classificado ({type(erro).__name__}: {erro})")
            continue
        gasto += custo(uso)
        agora = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for prop in lote:
            if prop["chave"] in resultado:
                existentes[prop["chave"]] = {
                    "assuntos": resultado[prop["chave"]], "fonte_hash": impressao_digital(prop), "modelo": uso["modelo"], "gerado_em": agora,
                }
                feitas += 1
            else:
                avisar(f"{prop['chave']}: sem classificação na resposta")
    doc = {"versao": VERSAO, "classificacoes": dict(sorted(existentes.items()))}
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{feitas} proposições classificadas, {len(pendentes) - feitas} sem classificação; {len(existentes)} no total")
    print(f"Custo estimado desta execução: US$ {gasto:.2f}")
    return doc


# --- Páginas -----------------------------------------------------------------------------------------

def _area_de(assunto: str) -> dict[str, Any]:
    return next(area for area in AREAS + [ROTINA] if assunto in area["assuntos"])


def paginas(linhas: list[dict[str, Any]], classificacoes: dict[str, dict[str, Any]], exemplos: int = 3) -> dict[str, Any]:
    """As nove áreas e a rotina, cada uma com as linhas da lista de votações que caem nela.

    Uma proposição entra em todas as áreas dos seus assuntos. Vai para a rotina só quando todos os
    seus assuntos são de rotina, ou quando ainda não foi classificada.
    """
    rotina_set = set(ROTINA["assuntos"])
    por_area: dict[str, list[dict[str, Any]]] = {a["slug"]: [] for a in AREAS + [ROTINA]}
    for linha in linhas:
        assuntos = [a for a in (classificacoes.get(linha["sigla"]) or {}).get("assuntos", []) if a in ASSUNTOS]
        substantivos = [a for a in assuntos if a not in rotina_set]
        if not substantivos:
            por_area["rotina"].append({**linha, "assuntos": assuntos or [OUTROS]})
            continue
        for slug in dict.fromkeys(_area_de(a)["slug"] for a in substantivos):
            por_area[slug].append({**linha, "assuntos": assuntos})

    resultado = []
    for area in AREAS + [ROTINA]:
        itens = por_area[area["slug"]]
        contagem = Counter(a for i in itens for a in i["assuntos"] if a in area["assuntos"])
        resultado.append({
            **area,
            "itens": itens,
            "total": len(itens),
            "leis": sum(1 for i in itens if i.get("virou_lei")),
            "filtros": [(a, contagem[a]) for a in area["assuntos"] if contagem[a]],
            "exemplos": [i["titulo"] for i in itens if len(i["titulo"]) <= 70][:exemplos],
        })
    return {"areas": resultado[:-1], "rotina": resultado[-1], "classificadas": sum(1 for l in linhas if l["sigla"] in classificacoes)}


if __name__ == "__main__":
    import anthropic  # só aqui: o build do site não precisa do SDK

    def _abrir(caminho: Path) -> Optional[dict[str, Any]]:
        return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None

    atualizar(votadas(_abrir(HISTORICO_PADRAO), _abrir(CONGRESSO_PADRAO)), SAIDA_PADRAO, anthropic.Anthropic())

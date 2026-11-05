"""Projetos e PECs assinados por um deputado no mandato, e quais viraram norma jurídica.

A lista vem dos arquivos anuais de Dados Abertos da Câmara. O número da norma só existe na tramitação
de cada proposta. Os totais por ano de todos os tipos de proposta e de relatorias vêm da página oficial.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any, Iterable, Optional

from monitor_politico.plenario import ementa_atual, limpar_texto

TIPOS = ("PL", "PLP", "PEC")
ROTULOS_PARTICIPACAO = {"primeira": "Primeira assinatura", "coautoria": "Coautoria", "apoio": "Apoio"}
ROTULOS_SITUACAO = {
    "norma": "Virou norma",
    "tramitacao": "Em tramitação",
    "encerrada": "Arquivada ou retirada",
    "sem_situacao": "Sem situação informada",
}
SITUACOES_ENCERRADAS = re.compile(r"arquivad|retirad|devolvid|rejeitad|prejudicad", re.IGNORECASE)
NORMA_NO_DESPACHO = re.compile(r"Transformad[oa] n[ao] (.+?)\.(\s|$)")


def participacao(linha_autor: dict[str, str]) -> str:
    """Em PEC, quem assina para atingir o mínimo de apoios não é proponente."""
    if linha_autor["proponente"] != "1":
        return "apoio"
    return "primeira" if linha_autor["ordemAssinatura"] == "1" else "coautoria"


def grupo_da_situacao(situacao: str) -> str:
    if not situacao:
        return "sem_situacao"
    if "norma" in situacao.lower():
        return "norma"
    return "encerrada" if SITUACOES_ENCERRADAS.search(situacao) else "tramitacao"


def norma_da_tramitacao(tramitacoes: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Nome da norma, data e se houve veto parcial. A mais recente vale se houver retificação."""
    achada = None
    for item in sorted(tramitacoes, key=lambda t: t.get("dataHora") or ""):
        despacho = item.get("despacho") or ""
        encontrado = NORMA_NO_DESPACHO.match(despacho)
        if encontrado:
            achada = {"nome": encontrado[1], "data": item["dataHora"][:10], "veto_parcial": "vetado parcialmente" in despacho.lower()}
    return achada


def propostas_do_mandato(fonte: Any, camara: Any, id_: int, inicio: str, anos: Iterable[int]) -> dict[str, Any]:
    anos = list(anos)
    assinaturas: dict[str, dict[str, str]] = {}
    for ano in anos:
        for linha in fonte.linhas("proposicoesAutores", ano):
            if linha["idDeputadoAutor"] == str(id_):
                assinaturas[linha["idProposicao"]] = linha

    lista = []
    for ano in anos:
        for proposta in fonte.linhas("proposicoes", ano):
            assinatura = assinaturas.get(proposta["id"])
            if assinatura is None or proposta["siglaTipo"] not in TIPOS or proposta["dataApresentacao"][:10] < inicio:
                continue
            lista.append({
                "id": proposta["id"],
                "sigla": f"{proposta['siglaTipo']} {proposta['numero']}/{proposta['ano']}",
                "tipo": proposta["siglaTipo"],
                "data": proposta["dataApresentacao"][:10],
                "ementa": limpar_texto(proposta["ementa"]),
                "situacao": limpar_texto(proposta["ultimoStatus_descricaoSituacao"]),
                "data_situacao": proposta["ultimoStatus_dataHora"][:10],
                "participacao": participacao(assinatura),
                "temas": [],
            })

    por_id = {p["id"]: p for p in lista}
    for ano in anos:
        for linha in fonte.linhas("proposicoesTemas", ano):
            proposta = por_id.get(linha["uriProposicao"].rsplit("/", 1)[-1])
            if proposta and linha["tema"] not in proposta["temas"]:
                proposta["temas"].append(linha["tema"])
    for proposta in lista:
        proposta["temas"].sort()
        proposta["norma"] = None
        if grupo_da_situacao(proposta["situacao"]) == "norma":
            proposta["norma"] = norma_da_tramitacao(camara._get(f"/proposicoes/{proposta['id']}/tramitacoes")["dados"])
    lista.sort(key=lambda p: (p["data"], p["id"]), reverse=True)
    return {
        "inicio": inicio,
        "por_ano": [{"ano": ano, **fonte.atuacao_oficial(id_, ano)} for ano in anos],
        "propostas": lista,
    }


def coletar(fonte: Any, camara: Any, id_: int, inicio: str, hoje: date) -> dict[str, Any]:
    return propostas_do_mandato(fonte, camara, id_, inicio, range(int(inicio[:4]), hoje.year + 1))


# --- O que a página mostra


def visao(doc: dict[str, Any], slugs: Optional[dict[str, str]] = None) -> dict[str, Any]:
    slugs = slugs or {}
    propostas = []
    for proposta in doc["propostas"]:
        grupo = grupo_da_situacao(proposta["situacao"])
        propostas.append({
            **proposta,
            "ementa": ementa_atual(proposta["ementa"]),
            "grupo": grupo,
            "rotulo_participacao": ROTULOS_PARTICIPACAO[proposta["participacao"]],
            "slug": slugs.get(proposta["sigla"]),
        })
    assuntos = Counter(t for p in propostas for t in p["temas"])
    maior = max(assuntos.values(), default=1)
    participacoes = Counter(p["participacao"] for p in propostas)
    situacoes = Counter(p["grupo"] for p in propostas)
    return {
        "inicio": doc["inicio"],
        "propostas": propostas,
        "total": len(propostas),
        "normas": [p for p in propostas if p["grupo"] == "norma"],
        "tipos": [(t, sum(p["tipo"] == t for p in propostas)) for t in TIPOS if any(p["tipo"] == t for p in propostas)],
        "participacoes": [(ROTULOS_PARTICIPACAO[c], participacoes[c], c) for c in ROTULOS_PARTICIPACAO if participacoes[c]],
        "situacoes": [(ROTULOS_SITUACAO[c], situacoes[c], c) for c in ROTULOS_SITUACAO if situacoes[c]],
        "temas": [{"nome": t, "valor": n, "largura": round(n / maior * 100, 1)} for t, n in assuntos.most_common(6)],
        "opcoes_temas": sorted(assuntos),
        "por_ano": doc["por_ano"],
        "total_autoria": sum(a["autoria"] for a in doc["por_ano"]),
        "total_relatadas": sum(a["relatadas"] for a in doc["por_ano"]),
    }

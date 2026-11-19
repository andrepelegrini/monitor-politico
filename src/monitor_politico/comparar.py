"""Comparar parlamentares da mesma Casa, lado a lado.

O build gera, para cada Casa, um arquivo com os números de todos (static/comparar/<casa>.json) e um
arquivo pequeno com os votos de cada pessoa (static/comparar/<casa>/<id>.json), que a página só baixa
para quem está sendo comparado. Só entram números objetivos, já publicados nos perfis.
"""

from __future__ import annotations

from typing import Any, Optional

# Subsídio mensal de deputados e senadores, igual para todos (Decreto Legislativo 172/2022).
SUBSIDIO = 46366.19
SUBSIDIO_DESDE = "2025-02-01"
MAX_PESSOAS = 3


def _eleicao(doc: dict[str, Any], ano_limite: int) -> Optional[list[int]]:
    """A eleição que deu o mandato atual: a mais recente até o ano anterior ao início dele."""
    validas = [e for e in doc.get("eleicoes", []) if e.get("votos") and e["ano"] <= ano_limite]
    recente = max(validas, key=lambda e: e["ano"], default=None)
    return [recente["ano"], recente["votos"]] if recente else None


def _cota(cota: dict[str, Any]) -> Optional[dict[str, Any]]:
    anos = [a for a in cota.get("por_ano", []) if a.get("total")]
    if not anos:
        return None
    total = sum(a["total"] for a in anos)
    # O limite só sai quando a Câmara publica o percentual de todos os anos (o Senado não publica).
    limite = sum(a["total"] * 100 / a["percentual"] for a in anos) if all(a.get("percentual") for a in anos) else None
    maior = (cota.get("categorias") or [None])[0]
    return {"total": round(total, 2), "limite": round(limite, 2) if limite else None, "maior": maior}


def _gabinete(gabinete: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    anos = [a for a in (gabinete or {}).get("por_ano", []) if a.get("total")]
    if not anos:
        return None
    total = sum(a["total"] for a in anos)
    disponivel = total + sum(a.get("nao_utilizado") or 0 for a in anos)
    return {"total": round(total, 2), "disponivel": round(disponivel, 2)}


def resumo(parlamentar: Any, doc: dict[str, Any], numeros: Optional[dict[str, Any]], ano_limite: int) -> dict[str, Any]:
    dinheiro = doc.get("dinheiro") or {}
    return {
        "id": parlamentar.id,
        "nome": parlamentar.nome,
        "partido": parlamentar.partido,
        "uf": parlamentar.uf,
        "foto": getattr(parlamentar, "url_foto", None),
        "eleicao": _eleicao(doc, ano_limite),
        "m": numeros,
        "cota": _cota(dinheiro["cota"]) if dinheiro.get("cota") else None,
        "gabinete": _gabinete(dinheiro.get("gabinete")),
    }


def votos(doc: dict[str, Any]) -> dict[str, list[str]]:
    """Ids das votações nominais em que a pessoa votou Sim ou Não."""
    lista = ((doc.get("plenario") or {}).get("votos") or {}).get("votos", [])
    return {
        "s": [v["id"] for v in lista if v["voto"] == "Sim"],
        "n": [v["id"] for v in lista if v["voto"] == "Não"],
    }


def concordancia(a: dict[str, list[str]], b: dict[str, list[str]]) -> tuple[int, int]:
    """(votos iguais, votações em que as duas pessoas votaram Sim ou Não). A página faz a mesma conta em JS."""
    sim_a, nao_a, sim_b, nao_b = set(a["s"]), set(a["n"]), set(b["s"]), set(b["n"])
    comuns = (sim_a | nao_a) & (sim_b | nao_b)
    return len(sim_a & sim_b) + len(nao_a & nao_b), len(comuns)

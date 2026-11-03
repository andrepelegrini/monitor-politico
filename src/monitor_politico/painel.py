"""Prepara os dados de `data/congresso.json` para a página principal e as
páginas de proposição: o que mostrar, em que ordem e com que texto."""

from __future__ import annotations

import re
from collections import Counter
from datetime import date
from typing import Any, Iterable, Optional

DIAS_SEMANA = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
MAX_TEMAS = 8


def data_br(iso: Optional[str]) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m/%Y") if iso else ""


def dia_mes(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%d/%m")


def rotulo_sessao(data_hora: str) -> str:
    """"2026-11-03T14:00" -> "Terça, 03/11 · 14h"."""
    dia = date.fromisoformat(data_hora[:10])
    rotulo = f"{DIAS_SEMANA[dia.weekday()]}, {dia:%d/%m}"
    hora = data_hora[11:16]
    if hora and hora != "00:00":
        h, m = hora.split(":")
        rotulo += f" · {int(h)}h" + (m if m != "00" else "")
    return rotulo


def titulo(prop: dict[str, Any]) -> str:
    return prop.get("apelido") or prop.get("ementa") or prop["chave"]


def texto_placar(votacao: dict[str, Any]) -> str:
    placar = votacao.get("placar")
    if not votacao.get("nominal") or not placar:
        return "Votação simbólica"
    texto = f"{placar['sim']} sim · {placar['nao']} não"
    if placar.get("abstencao"):
        texto += f" · {placar['abstencao']} abstenções" if placar["abstencao"] > 1 else " · 1 abstenção"
    return texto


def texto_situacao(prop: dict[str, Any]) -> str:
    sit = prop.get("situacao")
    if not sit:
        return ""
    if sit.get("norma"):
        return f"virou {sit['norma']}"
    return f"{sit['descricao']} ({sit['casa']}, desde {dia_mes(sit['data'])})"


def principais(prop: dict[str, Any]) -> list[dict[str, Any]]:
    return [v for v in prop["votacoes"] if not v["procedimento"]]


def ultima_por_casa(votacoes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """A votação de mérito mais recente de cada casa, da mais recente para a mais antiga."""
    por_casa: dict[str, dict[str, Any]] = {}
    for v in votacoes:
        por_casa[v["casa"]] = v  # as votações já vêm em ordem cronológica
    return sorted(por_casa.values(), key=lambda v: v["data_hora"], reverse=True)


# Página principal


def _item_pauta(item: dict[str, Any], proposicoes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prop = proposicoes.get(item["chave"])
    return {
        "chave": item["chave"],
        "slug": prop["slug"] if prop else None,
        "titulo": titulo(prop) if prop else (item.get("ementa") or item["chave"]),
        "fase": item.get("fase"),
    }


def pauta_por_casa(doc: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    casas: dict[str, list[dict[str, Any]]] = {"Senado": [], "Câmara": []}
    for sessao in doc["pauta"]:
        casas[sessao["casa"]].append({
            "rotulo": rotulo_sessao(sessao["data_hora"]),
            "sessao": sessao["sessao"],
            "itens": [_item_pauta(i, doc["proposicoes"]) for i in sessao["itens"]],
        })
    return casas


def votadas(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Proposições com votação de mérito no período, da votação mais recente para a mais antiga."""
    desde = doc["periodo"]["votacoes_desde"]
    linhas = []
    for prop in doc["proposicoes"].values():
        recentes = [v for v in principais(prop) if v["data_hora"][:10] >= desde]
        if not recentes:
            continue
        ultimas = ultima_por_casa(recentes)
        linhas.append({
            "slug": prop["slug"],
            "sigla": prop["chave"],
            "titulo": titulo(prop),
            "temas": prop["temas"],
            "situacao": texto_situacao(prop),
            "casas": sorted({v["casa"] for v in recentes}),
            "resultados": sorted({v["resultado"] for v in recentes if v["resultado"]}),
            "nominal": any(v["nominal"] for v in prop["votacoes"]),
            "votos": [
                {"casa": v["casa"], "data": dia_mes(v["data_hora"]), "resultado": v["resultado"], "placar": texto_placar(v)}
                for v in ultimas
            ],
            "_ordem": ultimas[0]["data_hora"][:10],
        })
    linhas.sort(key=lambda l: l["_ordem"], reverse=True)  # estável: empates mantêm a ordem por chave
    return linhas


def temas_em_destaque(doc: dict[str, Any], linhas: list[dict[str, Any]]) -> list[tuple[str, int]]:
    chaves = {l["sigla"] for l in linhas} | {i["chave"] for s in doc["pauta"] for i in s["itens"]}
    contagem = Counter(t for k in chaves if k in doc["proposicoes"] for t in doc["proposicoes"][k]["temas"])
    return sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_TEMAS]


def inicio(doc: dict[str, Any]) -> dict[str, Any]:
    linhas = votadas(doc)
    return {
        "pauta": pauta_por_casa(doc),
        "votadas": linhas,
        "temas": temas_em_destaque(doc, linhas),
        "todos_temas": sorted({t for l in linhas for t in l["temas"]}),
    }


# Página da proposição


def etapas(prop: dict[str, Any], pauta: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Linha do tempo resumida: apresentação, votações de mérito, situação atual e
    a próxima sessão em que está na pauta."""
    lista = []
    if prop.get("data_apresentacao"):
        detalhe = f"Por {', '.join(prop['autores'][:2])}" + (" e outros" if len(prop["autores"]) > 2 else "") if prop["autores"] else ""
        lista.append({"data": prop["data_apresentacao"], "casa": prop.get("casa_inicial") or "", "titulo": "Apresentada", "detalhe": detalhe, "futuro": False})
    for v in principais(prop):
        acao = {"aprovada": "Aprovada", "rejeitada": "Rejeitada"}.get(v["resultado"] or "", "Votada")
        lista.append({"data": v["data_hora"][:10], "casa": v["casa"], "titulo": f"{acao} no Plenário", "detalhe": texto_placar(v), "futuro": False})
    sit = prop.get("situacao")
    if sit and (not lista or sit["data"] >= lista[-1]["data"]):
        lista.append({
            "data": sit["data"],
            "casa": sit["casa"],
            "titulo": f"Virou {sit['norma']}" if sit.get("norma") else sit["descricao"],
            "detalhe": "Situação atual",
            "futuro": False,
        })
    for sessao in pauta:
        if any(i["chave"] == prop["chave"] for i in sessao["itens"]):
            lista.append({"data": sessao["data_hora"][:10], "casa": sessao["casa"], "titulo": "Na pauta do Plenário", "detalhe": rotulo_sessao(sessao["data_hora"]), "futuro": True})
            break
    return lista


def _orientacao_do_partido(partido: str, orientacoes: Optional[list[list[Any]]]) -> Optional[str]:
    """Orientação do próprio partido ou da federação que o inclui ("Fdr PT-PCdoB-PV").
    Partidos que orientam só via bloco ("Bl UniPpPsd...") ficam sem: a API abrevia o nome do bloco."""
    if not orientacoes:
        return None
    for sigla, orientacao in orientacoes:
        partes = re.split(r"[\s\-]+", sigla.upper())
        if sigla.upper() == partido.upper() or (partes[0] == "FDR" and partido.upper() in partes[1:]):
            return orientacao or "Não orientou"
    return None


def votacoes_da_pagina(prop: dict[str, Any], deputados: set[int], senadores: set[int]) -> dict[str, Any]:
    cards, nominais = [], []
    for v in prop["votacoes"]:
        placar = v.get("placar") or {}
        total = sum([placar.get("sim", 0), placar.get("nao", 0), placar.get("abstencao", 0)] + [n for _r, n in placar.get("outros", [])])
        card = {
            **v,
            "data": data_br(v["data_hora"]),
            "texto_placar": texto_placar(v),
            "p_sim": f"{100 * placar.get('sim', 0) / total:.1f}%" if total else "0%",
            "p_nao": f"{100 * placar.get('nao', 0) / total:.1f}%" if total else "0%",
            "outros_texto": " · ".join(f"{r}: {n}" for r, n in placar.get("outros", [])),
            "orientacao_sim": [s for s, o in v.get("orientacoes") or [] if o == "Sim"],
            "orientacao_nao": [s for s, o in v.get("orientacoes") or [] if o == "Não"],
            "orientacao_outras": [f"{s} ({o})" for s, o in v.get("orientacoes") or [] if o not in ("Sim", "Não", None)],
            "sem_orientacao": [s for s, o in v.get("orientacoes") or [] if o is None],
        }
        cards.append(card)
        if v["nominal"]:
            perfis, pasta = (deputados, "deputados") if v["casa"] == "Câmara" else (senadores, "senadores")
            nominais.append({
                "id": re.sub(r"[^A-Za-z0-9_-]", "-", v["id"]),
                "rotulo": f"{v['casa']} · {dia_mes(v['data_hora'])}" + (" · rito" if v["procedimento"] else ""),
                "rito": v["procedimento"],
                "descricao": v["descricao"],
                "total": len(v["votos"]),
                "tem_orientacao": bool(v.get("orientacoes")),
                "partidos": sorted({p["partido"] for p in v["votos"]}),
                "ufs": sorted({p["uf"] for p in v["votos"]}),
                "votos": [
                    {
                        **p,
                        "url": f"../{pasta}/{p['id']}.html" if p["id"] in perfis else None,
                        "grupo": p["voto"] if p["voto"] in ("Sim", "Não") else "Outros",
                        "orientacao": _orientacao_do_partido(p["partido"], v.get("orientacoes")),
                    }
                    for p in v["votos"]
                ],
            })
    return {
        "principais": [c for c in cards if not c["procedimento"]],
        "rito": [c for c in cards if c["procedimento"]],
        "nominais": sorted(nominais, key=lambda n: n["rito"]),  # mérito primeiro; sort estável mantém a ordem cronológica
        "tem_simbolica": any(not c["nominal"] for c in cards),
    }

"""Feeds RSS: para acompanhar votações, áreas, parlamentares e proposições num leitor de RSS, sem e-mail.

Cada feed é um arquivo estático gerado no build, em feeds/. Os itens só usam dados já publicados nas
páginas, com o mesmo texto neutro: o que foi votado, o resultado e o placar.
"""

from __future__ import annotations

from datetime import datetime, time
from email.utils import format_datetime
from typing import Any, Iterable, Optional
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from monitor_politico import painel

SITE_PADRAO = "https://www.nagaleria.com.br"
MAX_ITENS = 50
FUSO = ZoneInfo("America/Sao_Paulo")


def _data(texto: str) -> datetime:
    """"2026-11-03" (vira meio-dia) ou "2026-10-27T21:34:40", no horário de Brasília."""
    if len(texto) == 10:
        return datetime.combine(datetime.fromisoformat(texto).date(), time(12, 0), tzinfo=FUSO)
    return datetime.fromisoformat(texto[:19]).replace(tzinfo=FUSO)


def documento(titulo: str, pagina: str, endereco: str, descricao: str, itens: Iterable[dict[str, Any]]) -> str:
    """RSS 2.0. `pagina` e `endereco` são absolutos; cada item tem titulo, link, guid, data e texto."""
    lista = sorted(itens, key=lambda i: i["data"], reverse=True)[:MAX_ITENS]
    partes = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "<channel>",
        f"<title>{escape(titulo)}</title>",
        f"<link>{escape(pagina)}</link>",
        f'<atom:link href="{escape(endereco)}" rel="self" type="application/rss+xml"/>',
        f"<description>{escape(descricao)}</description>",
        "<language>pt-BR</language>",
    ]
    if lista:
        partes.append(f"<lastBuildDate>{format_datetime(_data(lista[0]['data']))}</lastBuildDate>")
    for item in lista:
        partes += [
            "<item>",
            f"<title>{escape(item['titulo'])}</title>",
            f"<link>{escape(item['link'])}</link>",
            f'<guid isPermaLink="false">{escape(item["guid"])}</guid>',
            f"<pubDate>{format_datetime(_data(item['data']))}</pubDate>",
            f"<description>{escape(item['texto'])}</description>",
            "</item>",
        ]
    partes += ["</channel>", "</rss>", ""]
    return "\n".join(partes)


def _resultado(casa: str, data: str, resultado: Optional[str], placar: Optional[str]) -> str:
    """"Senado, 03/11: aprovada, 75 sim · 0 não" ou "Câmara, 11/11: aprovada, em votação simbólica"."""
    if placar == "Votação simbólica":
        placar = "em votação simbólica"
    detalhes = ", ".join(x for x in (resultado, placar) if x)
    return f"{casa}, {data}" + (f": {detalhes}" if detalhes else "")


def de_votadas(linhas: Iterable[dict[str, Any]], site: str) -> list[dict[str, Any]]:
    """Uma linha da lista de votações vira um item; o guid muda quando há votação nova do mesmo projeto."""
    itens = []
    for linha in linhas:
        texto = " ".join(f"{_resultado(v['casa'], v['data'], v.get('resultado'), v.get('placar'))}." for v in linha["votos"])
        if linha.get("situacao"):
            texto += f" Situação: {linha['situacao']}."
        itens.append({
            "titulo": f"{linha['sigla']}: {linha['titulo']}",
            "link": f"{site}/proposicoes/{linha['slug']}.html",
            "guid": f"{linha['sigla']} {linha['_ordem']}",
            "data": linha["_ordem"],
            "texto": texto,
        })
    return itens


def do_parlamentar(votos: Iterable[dict[str, Any]], site: str) -> list[dict[str, Any]]:
    """Votos nominais no plenário, como na lista do perfil."""
    itens = []
    for v in votos:
        if v.get("slug"):
            link = f"{site}/proposicoes/{v['slug']}.html"
        elif v.get("url"):
            link = v["url"]
        else:
            link = f"https://www.camara.leg.br/propostas-legislativas/{v['proposicao_id']}"
        voto = f"Votou {v['voto']}" if v["voto"] in ("Sim", "Não") else v["voto"]
        demais = f"Demais votos: {v['sim']} Sim, {v['nao']} Não" + (f", {v['outros']} {'outro' if v['outros'] == 1 else 'outros'}" if v["outros"] else "")
        itens.append({
            "titulo": f"{voto} · {v.get('sigla') or 'Votação'}",
            "link": link,
            "guid": f"voto {v['id']}",
            "data": v["data"],
            "texto": f"{v.get('ementa') or ''} O que foi votado: {v['descricao']} {demais}.".strip(),
        })
    return itens


def da_proposicao(prop: dict[str, Any], site: str) -> list[dict[str, Any]]:
    """Votações no plenário (sem as de procedimento) e a situação mais recente."""
    link = f"{site}/proposicoes/{prop['slug']}.html"
    itens = []
    for v in prop.get("votacoes", []):
        if v.get("procedimento"):
            continue
        resultado = _resultado(v["casa"], painel.data_br(v["data_hora"]), v.get("resultado"), painel.texto_placar(v))
        itens.append({
            "titulo": f"{prop['chave']} · {resultado}",
            "link": link,
            "guid": f"votacao {v['id']}",
            "data": v["data_hora"],
            "texto": v.get("descricao") or "",
        })
    situacao = prop.get("situacao") or {}
    if situacao.get("descricao") and situacao.get("data"):
        texto = painel.texto_situacao(prop) or situacao["descricao"]
        itens.append({
            "titulo": f"{prop['chave']} · Situação: {texto}",
            "link": link,
            "guid": f"situacao {prop['chave']} {situacao['data']} {situacao['descricao']}",
            "data": situacao["data"],
            "texto": f"Situação em {painel.data_br(situacao['data'][:10])}: {texto}.",
        })
    return itens


def endereco_do_site(site_url: Optional[str]) -> str:
    return (site_url or SITE_PADRAO).rstrip("/")

"""Página de cada estado: quem o representa no Congresso hoje e quem chega em 2027.

Junta o que já existe em outras páginas (senadores, deputados, números do mandato e o resultado da
eleição de 2026), filtrado pela UF. Não há coleta própria.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from typing import Any, Optional, Sequence

from monitor_politico import mapa, metricas as modulo_metricas
from monitor_politico.models import Deputado, Senador

DEPUTADOS_NA_PAGINA = 12  # o restante aparece com "Mostrar todos"


def _alfabetica(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().casefold()


def _barras(contagem: Counter[str]) -> list[dict[str, Any]]:
    maior = max(contagem.values(), default=1)
    return [{"rotulo": r, "n": n, "largura": round(n / maior * 100, 1)} for r, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))]


def nomes_das_ufs() -> dict[str, str]:
    return {uf: forma["nome"] for uf, forma in mapa._malha()["estados"].items()}


def por_estado(
    deputados: Sequence[Deputado],
    senadores: Sequence[Senador],
    metricas_dep: Optional[dict[str, Any]] = None,
    legislatura: Optional[dict[str, Any]] = None,
    metricas_sen: Optional[dict[str, Any]] = None,
    legislatura_sen: Optional[dict[str, Any]] = None,
) -> dict[str, dict[str, Any]]:
    situacoes = (legislatura or {}).get("situacoes", {})
    situacoes_sen = (legislatura_sen or {}).get("situacoes", {})
    resultado = {}
    for uf, nome in nomes_das_ufs().items():
        deps = sorted((d for d in deputados if d.uf == uf), key=lambda d: _alfabetica(d.nome))
        sens = sorted((s for s in senadores if s.uf == uf), key=lambda s: _alfabetica(s.nome))
        partidos = Counter(d.partido for d in deps)
        eleicao = Counter(situacoes[str(d.id)]["rotulo"] for d in deps if str(d.id) in situacoes)
        novos_dep = sorted((e for e in (legislatura or {}).get("eleitos_novos", []) if e["uf"] == uf), key=lambda e: _alfabetica(e["nome"]))
        novos_sen = sorted((e for e in (legislatura_sen or {}).get("eleitos_novos", []) if e["uf"] == uf), key=lambda e: _alfabetica(e["nome"]))
        maior = partidos.most_common(1)[0] if partidos else None
        resultado[uf] = {
            "uf": uf,
            "slug": uf.lower(),
            "nome": nome,
            "deputados": deps,
            "senadores": sens,
            "numeros_dep": {d.id: modulo_metricas.do_deputado(metricas_dep, d.id) for d in deps} if metricas_dep else None,
            "numeros_sen": {s.id: modulo_metricas.do_deputado(metricas_sen, s.id) for s in sens} if metricas_sen else None,
            "situacoes": situacoes,
            "situacoes_sen": situacoes_sen,
            "partidos": _barras(partidos)[:10],
            "outros_partidos": sum(n for _, n in partidos.most_common()[10:]),
            "n_partidos": len(partidos),
            "maior_partido": {"sigla": maior[0], "n": maior[1], "empate": sum(1 for n in partidos.values() if n == maior[1]) > 1} if maior else None,
            "eleicao": _barras(eleicao),
            "reeleitos": eleicao.get("Reeleição", 0),
            "novos_dep": novos_dep,
            "novos_sen": novos_sen,
            "na_pagina": DEPUTADOS_NA_PAGINA,
        }
    return resultado

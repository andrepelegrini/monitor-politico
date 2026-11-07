"""Mapa do Brasil com o tamanho da bancada de cada estado na Câmara.

O contorno dos estados vem da malha oficial do IBGE e está em mapa_brasil.json, já convertido para
coordenadas da página. As faixas de cor são fixas: o mínimo de 8 deputados por estado é constitucional,
então a faixa mais clara reúne quem está no piso.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

ARQUIVO = Path(__file__).parent / "mapa_brasil.json"
# Limite inferior de cada faixa. A última vai até a maior bancada.
FAIXAS = (8, 9, 13, 21, 40)
# A partir desta faixa a cor é escura e o rótulo fica claro.
FAIXA_ESCURA = 3


@lru_cache(maxsize=1)
def _malha() -> dict[str, Any]:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


def faixa(n: int) -> int:
    return max(i for i, minimo in enumerate(FAIXAS) if n >= minimo) if n >= FAIXAS[0] else 0


def visao(bancadas: Sequence[dict[str, Any]]) -> dict[str, Any]:
    malha = _malha()
    por_uf = {b["uf"]: b for b in bancadas}
    maior = max((b["n"] for b in bancadas), default=0)
    estados = []
    for uf, forma in malha["estados"].items():
        b = por_uf.get(uf)
        if b is None:
            continue
        f = faixa(b["n"])
        estados.append({**forma, "uf": uf, "n": b["n"], "maior": b["maior"], "faixa": f, "claro": f >= FAIXA_ESCURA})
    # Os estados maiores primeiro, para o contorno dos menores ficar por cima.
    estados.sort(key=lambda e: -len(e["d"]))
    faixas = []
    for i, minimo in enumerate(FAIXAS):
        limite = FAIXAS[i + 1] - 1 if i + 1 < len(FAIXAS) else maior
        quantos = sum(1 for e in estados if e["faixa"] == i)
        if i == 0:
            rotulo = f"{minimo}, o mínimo"
        else:
            rotulo = f"{minimo} a {limite}" if limite > minimo else str(minimo)
        faixas.append({"indice": i, "rotulo": rotulo, "estados": quantos})
    return {"largura": malha["largura"], "altura": malha["altura"], "estados": estados, "faixas": faixas}

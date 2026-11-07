"""A métrica comparável da lista de deputados: leis sancionadas no mandato atual, por tipo de autoria.

O critério é o mesmo para todos: conta a data em que a norma saiu, e não a data do projeto, para não
favorecer quem está há mais tempo na Câmara nem esquecer projetos apresentados em mandatos anteriores.
O arquivo é gerado junto com os perfis, em lote.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

SAIDA_PADRAO = Path("data/metricas_deputados.json")
DEPUTADOS_PADRAO = Path("data/deputados.json")
INICIO_MANDATO = "2023-02-01"  # Trocar na posse da nova legislatura, em 01/02/2027.
ANO_MAIS_ANTIGO = 1995  # Primeiro ano conferido nos arquivos da Câmara.


def ler(caminho: Path) -> Optional[dict[str, Any]]:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def do_deputado(metricas: Optional[dict[str, Any]], id_: int) -> dict[str, int]:
    return (metricas or {}).get("por_deputado", {}).get(str(id_), {"principal": 0, "coautoria": 0})

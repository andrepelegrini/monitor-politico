"""Coleta de senadores em exercício na API Dados Abertos do Senado.

Uso: python -m monitor_politico.senado [saida.json]
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from monitor_politico.api import ClienteJSON
from monitor_politico.models import Senador, como_lista

API_BASE = "https://legis.senado.leg.br/dadosabertos"
SAIDA_PADRAO = Path("data/senadores.json")
MINIMO_ESPERADO = 70  # são 81 cadeiras; menos que isso indica resposta incompleta


class ColetaIncompleta(RuntimeError):
    pass


class ClienteSenado(ClienteJSON):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(API_BASE, **kwargs)

    def senadores(self) -> list[Senador]:
        """Uma única chamada traz todos os senadores em exercício."""
        corpo = self._get("/senador/lista/atual")
        itens = como_lista(corpo["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])
        return [Senador.da_api(p) for p in itens]


def coletar(cliente: ClienteSenado, saida: Path = SAIDA_PADRAO, minimo: int = MINIMO_ESPERADO) -> dict[str, Any]:
    senadores = cliente.senadores()
    if len(senadores) < minimo:
        raise ColetaIncompleta(f"só {len(senadores)} senadores na resposta (esperado ao menos {minimo})")
    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": API_BASE,
        "senadores": [s.para_dict() for s in senadores],
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    doc = coletar(ClienteSenado(), destino)
    print(f"{len(doc['senadores'])} senadores salvos em {destino}")

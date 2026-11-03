"""Coleta de senadores em exercício na API Dados Abertos do Senado.

Uso: python -m monitor_politico.senado [saida.json]
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import httpx

from monitor_politico import composicao
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

    def lista_atual(self) -> list[dict[str, Any]]:
        """Uma única chamada traz todos os senadores em exercício."""
        corpo = self._get("/senador/lista/atual")
        return como_lista(corpo["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"])

    def senadores(self) -> list[Senador]:
        return [Senador.da_api(p) for p in self.lista_atual()]

    # Composição: lideranças (das duas Casas) e Mesa do Senado

    def liderancas(self) -> list[dict[str, Any]]:
        return self._get("/composicao/lideranca")

    def mesa(self) -> dict[str, Any]:
        return self._get("/composicao/mesaSF")

    # Plenário: votações, pauta e proposições

    def votacoes(self, inicio: date, fim: date) -> list[dict[str, Any]]:
        """Só votações nominais; cada uma já traz os votos."""
        return self._get("/votacao", {"dataInicio": inicio.isoformat(), "dataFim": fim.isoformat()})

    def agenda_do_mes(self, a_partir_de: date) -> list[dict[str, Any]]:
        """Sessões do plenário de `a_partir_de` até o fim do mês."""
        corpo = self._get(f"/plenario/agenda/mes/{a_partir_de:%Y%m%d}")
        return como_lista(((corpo.get("AgendaPlenario") or {}).get("Sessoes") or {}).get("Sessao"))

    def processo(self, sigla: str, numero: int, ano: int) -> Optional[dict[str, Any]]:
        encontrados = self._get("/processo", {"sigla": sigla, "numero": numero, "ano": ano})
        return encontrados[0] if encontrados else None

    def processo_detalhe(self, id_: int) -> dict[str, Any]:
        return self._get(f"/processo/{id_}")


def lideres_do_senado(cliente: ClienteSenado, avisar: Callable[[str], None]) -> Optional[list[dict[str, Any]]]:
    """Presidente e líderes; sem eles o resumo só omite o bloco, então uma falha não aborta."""
    try:
        presidente = composicao.presidente_do_senado(cliente.mesa())
        return ([presidente] if presidente else []) + composicao.lideres(cliente.liderancas(), "SF")
    except httpx.HTTPError as erro:
        avisar(f"lideranças do Senado falharam ({erro})")
        return None


def coletar(
    cliente: ClienteSenado,
    saida: Path = SAIDA_PADRAO,
    minimo: int = MINIMO_ESPERADO,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
) -> dict[str, Any]:
    brutos = cliente.lista_atual()
    if len(brutos) < minimo:
        raise ColetaIncompleta(f"só {len(brutos)} senadores na resposta (esperado ao menos {minimo})")
    senadores = [Senador.da_api(p) for p in brutos]
    sexo = composicao.contar_sexo(
        (s.partido, p["IdentificacaoParlamentar"].get("SexoParlamentar") == "Feminino") for s, p in zip(senadores, brutos)
    )
    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": API_BASE,
        "resumo": {"sexo": sexo, "lideres": lideres_do_senado(cliente, avisar)},
        "senadores": [s.para_dict() for s in senadores],
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    doc = coletar(ClienteSenado(), destino)
    print(f"{len(doc['senadores'])} senadores salvos em {destino}")

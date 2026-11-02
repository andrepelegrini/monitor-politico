"""Coleta de deputados em exercício na API Dados Abertos da Câmara (v2).

Uso: python -m monitor_politico.camara [saida.json]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import httpx

from monitor_politico.models import Deputado

API_BASE = "https://dadosabertos.camara.leg.br/api/v2"
SAIDA_PADRAO = Path("data/deputados.json")
TENTATIVAS = 6  # espera até 1+2+4+8+16 = 31s; a API dá 504 esporádicos
ATRASO_ENTRE_CHAMADAS = 0.1  # segundos; cortesia com a API pública
LIMITE_FALHAS = 0.1  # fração de perfis que pode falhar antes de abortar a coleta


class ColetaIncompleta(RuntimeError):
    pass


class ClienteCamara:
    def __init__(
        self,
        http: Optional[httpx.Client] = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http or httpx.Client(
            base_url=API_BASE,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        self.dormir = dormir

    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        for tentativa in range(TENTATIVAS):
            try:
                resp = self.http.get(url, params=params)
                if resp.status_code != 429 and resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TransportError:
                if tentativa == TENTATIVAS - 1:
                    raise
            if tentativa < TENTATIVAS - 1:
                self.dormir(2**tentativa)
        resp.raise_for_status()
        raise RuntimeError("inalcançável")

    def ids_em_exercicio(self) -> Iterator[int]:
        """Sem `idLegislatura`, a API lista só quem está em exercício."""
        url: Optional[str] = "/deputados"
        params: Optional[dict[str, Any]] = {"itens": 100, "pagina": 1, "ordem": "ASC", "ordenarPor": "nome"}
        while url:
            corpo = self._get(url, params)
            for d in corpo["dados"]:
                yield d["id"]
            url = next((l["href"] for l in corpo["links"] if l["rel"] == "next"), None)
            params = None  # o link "next" já carrega os parâmetros

    def deputado(self, id_: int) -> Deputado:
        return Deputado.da_api(self._get(f"/deputados/{id_}")["dados"])

    def deputados(self, anteriores: Optional[dict[int, Deputado]] = None) -> list[Deputado]:
        """Se um perfil falhar mesmo após as tentativas, reaproveita o da coleta
        anterior (ou o omite, se não houver). Aborta se falharem demais."""
        anteriores = anteriores or {}
        ids = list(self.ids_em_exercicio())
        resultado, falhas = [], []
        for id_ in ids:
            try:
                resultado.append(self.deputado(id_))
            except httpx.HTTPError as erro:
                falhas.append(id_)
                print(f"aviso: deputado {id_} falhou ({erro})", file=sys.stderr)
                if id_ in anteriores:
                    resultado.append(anteriores[id_])
            self.dormir(ATRASO_ENTRE_CHAMADAS)
        if len(falhas) > LIMITE_FALHAS * len(ids):
            raise ColetaIncompleta(f"{len(falhas)} de {len(ids)} perfis falharam")
        return resultado


def ler_anteriores(caminho: Path) -> dict[int, Deputado]:
    if not caminho.exists():
        return {}
    doc = json.loads(caminho.read_text(encoding="utf-8"))
    return {d["id"]: Deputado.de_dict(d) for d in doc["deputados"]}


def coletar(cliente: ClienteCamara, saida: Path = SAIDA_PADRAO) -> dict[str, Any]:
    deputados = cliente.deputados(ler_anteriores(saida))
    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": API_BASE,
        "deputados": [d.para_dict() for d in deputados],
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    doc = coletar(ClienteCamara(), destino)
    print(f"{len(doc['deputados'])} deputados salvos em {destino}")

"""Coleta de deputados em exercício na API Dados Abertos da Câmara (v2).

Uso: python -m monitor_politico.camara [saida.json]
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

import httpx

from monitor_politico import composicao
from monitor_politico.api import ClienteJSON
from monitor_politico.models import Deputado
from monitor_politico.senado import ClienteSenado

API_BASE = "https://dadosabertos.camara.leg.br/api/v2"
SAIDA_PADRAO = Path("data/deputados.json")
ID_PLENARIO = 180
ATRASO_ENTRE_CHAMADAS = 0.1  # segundos; cortesia com a API pública
LIMITE_FALHAS = 0.1  # fração de perfis que pode falhar antes de abortar a coleta


class ColetaIncompleta(RuntimeError):
    pass


class ClienteCamara(ClienteJSON):
    def __init__(self, http: Optional[httpx.Client] = None, dormir: Callable[[float], None] = time.sleep) -> None:
        super().__init__(API_BASE, http, dormir)

    def _paginar(self, url: str, params: Optional[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        proxima: Optional[str] = url
        while proxima:
            corpo = self._get(proxima, params)
            yield from corpo["dados"]
            proxima = next((l["href"] for l in corpo["links"] if l["rel"] == "next"), None)
            params = None  # o link "next" já carrega os parâmetros

    def ids_em_exercicio(self) -> Iterator[int]:
        """Sem `idLegislatura`, a API lista só quem está em exercício."""
        params = {"itens": 100, "pagina": 1, "ordem": "ASC", "ordenarPor": "nome"}
        for d in self._paginar("/deputados", params):
            yield d["id"]

    def ids_mulheres(self) -> set[int]:
        """Só para a contagem do resumo: o gênero não é guardado por deputado."""
        return {d["id"] for d in self._paginar("/deputados", {"siglaSexo": "F", "itens": 100, "pagina": 1})}

    def mesa_atual(self) -> list[dict[str, Any]]:
        legislaturas = self._get("/legislaturas", {"itens": 1, "ordem": "DESC", "ordenarPor": "id"})["dados"]
        return self._get(f"/legislaturas/{legislaturas[0]['id']}/mesa")["dados"]

    # Plenário: votações, pauta e proposições

    def votacoes_plenario(self, inicio: date, fim: date) -> list[dict[str, Any]]:
        params = {"idOrgao": ID_PLENARIO, "dataInicio": inicio.isoformat(), "dataFim": fim.isoformat(),
                  "itens": 200, "ordem": "ASC", "ordenarPor": "dataHoraRegistro"}
        return list(self._paginar("/votacoes", params))

    def votos(self, id_votacao: str) -> list[dict[str, Any]]:
        return self._get(f"/votacoes/{id_votacao}/votos")["dados"]

    def orientacoes(self, id_votacao: str) -> list[dict[str, Any]]:
        return self._get(f"/votacoes/{id_votacao}/orientacoes")["dados"]

    def proposicao(self, id_: int) -> dict[str, Any]:
        return self._get(f"/proposicoes/{id_}")["dados"]

    def temas(self, id_: int) -> list[str]:
        return [t["tema"] for t in self._get(f"/proposicoes/{id_}/temas")["dados"]]

    def autores(self, id_: int) -> list[str]:
        return [a["nome"] for a in self._get(f"/proposicoes/{id_}/autores")["dados"]]

    def buscar_proposicao(self, sigla: str, numero: int, ano: int) -> Optional[int]:
        dados = self._get("/proposicoes", {"siglaTipo": sigla, "numero": numero, "ano": ano})["dados"]
        return dados[0]["id"] if dados else None

    def sessoes_deliberativas(self, inicio: date, fim: date) -> list[dict[str, Any]]:
        params = {"idOrgao": ID_PLENARIO, "dataInicio": inicio.isoformat(), "dataFim": fim.isoformat(), "itens": 100}
        eventos = self._paginar("/eventos", params)
        return [e for e in eventos if "Deliberativa" in e["descricaoTipo"] and "Não Deliberativa" not in e["descricaoTipo"]]

    def pauta(self, id_evento: int) -> list[dict[str, Any]]:
        return self._get(f"/eventos/{id_evento}/pauta")["dados"]

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


def coletar(
    cliente: ClienteCamara,
    saida: Path = SAIDA_PADRAO,
    senado: Optional[ClienteSenado] = None,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
) -> dict[str, Any]:
    deputados = cliente.deputados(ler_anteriores(saida))
    # O resumo é complementar: se uma dessas consultas falhar, o bloco correspondente some da página.
    sexo = presidente = None
    lideres: Optional[list[dict[str, Any]]] = None
    try:
        presidente = composicao.presidente_da_camara(cliente.mesa_atual())
    except httpx.HTTPError as erro:
        avisar(f"Mesa da Câmara falhou ({erro})")
    try:
        mulheres = cliente.ids_mulheres()
        sexo = composicao.contar_sexo((d.partido, d.id in mulheres) for d in deputados)
    except httpx.HTTPError as erro:
        avisar(f"contagem de mulheres falhou ({erro})")
    if senado is not None:
        try:
            lideres = composicao.lideres(senado.liderancas(), "CD")
        except httpx.HTTPError as erro:
            avisar(f"lideranças da Câmara falharam ({erro})")
    if presidente:
        lideres = [presidente] + (lideres or [])
    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "fonte": API_BASE,
        "resumo": {"sexo": sexo, "lideres": lideres},
        "deputados": [d.para_dict() for d in deputados],
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    doc = coletar(ClienteCamara(), destino, senado=ClienteSenado())
    print(f"{len(doc['deputados'])} deputados salvos em {destino}")

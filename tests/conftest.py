import json
from pathlib import Path

import httpx
import pytest

from monitor_politico.camara import API_BASE, ClienteCamara
from monitor_politico.senado import API_BASE as SENADO_API_BASE, ClienteSenado

FIXTURES = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> dict:
    return json.loads((FIXTURES / nome).read_text(encoding="utf-8"))


def responder_com_fixtures(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path.removeprefix("/api/v2")
    if caminho == "/deputados" and request.url.params.get("siglaSexo") == "F":
        # Nenhum dos 4 deputados da fixture é mulher; o ID abaixo não está na lista.
        return httpx.Response(200, json={"dados": [{"id": 999999}], "links": []})
    if caminho == "/legislaturas":
        return httpx.Response(200, json={"dados": [{"id": 57}], "links": []})
    if caminho == "/legislaturas/57/mesa":
        return httpx.Response(200, json=carregar("camara_mesa.json"))
    if caminho == "/deputados":
        pagina = request.url.params.get("pagina", "1")
        return httpx.Response(200, json=carregar(f"lista_p{pagina}.json"))
    id_ = caminho.rsplit("/", 1)[-1]
    return httpx.Response(200, json=carregar(f"deputado_{id_}.json"))


def cliente_falso(handler=responder_com_fixtures) -> ClienteCamara:
    http = httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(handler))
    return ClienteCamara(http=http, dormir=lambda _s: None)


@pytest.fixture
def cliente() -> ClienteCamara:
    return cliente_falso()


ROTAS_SENADO = {
    "/dadosabertos/senador/lista/atual": "senado_lista.json",
    "/dadosabertos/composicao/lideranca": "senado_liderancas.json",
    "/dadosabertos/composicao/mesaSF": "senado_mesa.json",
}


def senado_falso(handler=None) -> ClienteSenado:
    def padrao(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=carregar(ROTAS_SENADO[request.url.path]))

    http = httpx.Client(base_url=SENADO_API_BASE, transport=httpx.MockTransport(handler or padrao))
    return ClienteSenado(http=http, dormir=lambda _s: None)


@pytest.fixture
def senado() -> ClienteSenado:
    return senado_falso()


def congresso_falso(falhar=()):
    """Clientes da Câmara e do Senado servidos por respostas reais gravadas
    (tests/fixtures/congresso_api.json) para um cenário com hoje = 2026-11-02.
    URLs que contêm algum trecho de `falhar` respondem 504."""
    respostas = carregar("congresso_api.json")

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if any(trecho in url for trecho in falhar):
            return httpx.Response(504)
        if url not in respostas:
            pytest.fail(f"URL fora da fixture: {url}")
        return httpx.Response(200, json=respostas[url])

    transporte = httpx.MockTransport(handler)
    camara = ClienteCamara(http=httpx.Client(base_url=API_BASE, transport=transporte), dormir=lambda _s: None)
    senado = ClienteSenado(http=httpx.Client(base_url=SENADO_API_BASE, transport=transporte), dormir=lambda _s: None)
    return camara, senado

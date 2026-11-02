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


def senado_falso(handler=None) -> ClienteSenado:
    def padrao(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=carregar("senado_lista.json"))

    http = httpx.Client(base_url=SENADO_API_BASE, transport=httpx.MockTransport(handler or padrao))
    return ClienteSenado(http=http, dormir=lambda _s: None)


@pytest.fixture
def senado() -> ClienteSenado:
    return senado_falso()

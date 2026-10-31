import json
from dataclasses import fields

import httpx

from conftest import carregar, cliente_falso, responder_com_fixtures
from monitor_politico.camara import coletar
from monitor_politico.models import Deputado, Gabinete

CAMPOS_PROIBIDOS = {"cpf", "dataNascimento", "nomeCivil", "redeSocial", "sexo", "municipioNascimento", "escolaridade"}


def test_percorre_todas_as_paginas(cliente):
    assert list(cliente.ids_em_exercicio()) == [204379, 220714, 221328, 204560]


def test_parse_perfil(cliente):
    d = cliente.deputado(204379)
    assert d.nome == "Acácio Favacho"
    assert (d.partido, d.uf, d.situacao) == ("MDB", "AP", "Exercício")
    assert d.gabinete.email == "dep.acaciofavacho@camara.leg.br"
    assert d.gabinete.telefone == "3215-5414"
    assert d.url_site == "https://www.camara.leg.br/deputados/204379"
    assert d.uri_api == "https://dadosabertos.camara.leg.br/api/v2/deputados/204379"


def test_whitelist_descarta_dados_pessoais(tmp_path, cliente):
    # A fixture real contém esses campos; garante que o teste é significativo.
    assert CAMPOS_PROIBIDOS <= carregar("deputado_204379.json")["dados"].keys()

    saida = tmp_path / "deputados.json"
    coletar(cliente, saida)
    texto = saida.read_text(encoding="utf-8")
    doc = json.loads(texto)

    campos_permitidos = {f.name for f in fields(Deputado)}
    for d in doc["deputados"]:
        assert set(d) == campos_permitidos
        assert set(d["gabinete"]) == {f.name for f in fields(Gabinete)}
    assert "74287028287" not in texto  # CPF presente na fixture
    assert "1983-09-28" not in texto  # data de nascimento


def test_coletar_registra_data(tmp_path, cliente):
    doc = coletar(cliente, tmp_path / "d.json")
    assert doc["coletado_em"].endswith("+00:00")
    assert len(doc["deputados"]) == 4


def test_retry_em_erro_do_servidor():
    falhas = {"restantes": 2}

    def instavel(request: httpx.Request) -> httpx.Response:
        if falhas["restantes"]:
            falhas["restantes"] -= 1
            return httpx.Response(503)
        return responder_com_fixtures(request)

    assert cliente_falso(instavel).deputado(204379).id == 204379


def test_ida_e_volta_dict():
    d = Deputado.da_api(carregar("deputado_204379.json")["dados"])
    assert Deputado.de_dict(d.para_dict()) == d

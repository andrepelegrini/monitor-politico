import json
from dataclasses import fields

import httpx
import pytest

from conftest import carregar, senado_falso
from monitor_politico.models import Senador
from monitor_politico.senado import ColetaIncompleta, coletar

CAMPOS_PROIBIDOS = {"SexoParlamentar", "NomeCompletoParlamentar"}


def _por_id(cliente):
    return {s.id: s for s in cliente.senadores()}


def test_parse_titular(senado):
    s = _por_id(senado)[5672]
    assert (s.nome, s.partido, s.uf) == ("Alan Rick", "REPUBLICANOS", "AC")
    assert s.condicao == "Titular"
    assert s.bloco == "Bloco Parlamentar Aliança"
    assert s.fim_mandato == "2031-01-31"
    assert s.email == "sen.alanrick@senado.leg.br"
    assert s.telefones == ("3303-6333",)
    assert s.url_foto.startswith("https://")
    assert s.url_site == "https://www25.senado.leg.br/web/senadores/senador/-/perfil/5672"


def test_campos_ausentes_e_varios_telefones(senado):
    senadores = _por_id(senado)
    assert senadores[5257].email is None
    assert senadores[5257].condicao == "1º Suplente"
    assert senadores[5322].bloco is None
    assert senadores[739].telefones == ("3303-6187", "3303-6188", "3303-6183")


def test_um_unico_parlamentar_vem_sem_lista():
    # O JSON do Senado é convertido de XML: com um item só, não vem lista.
    corpo = carregar("senado_lista.json")
    parlamentares = corpo["ListaParlamentarEmExercicio"]["Parlamentares"]
    unico = parlamentares["Parlamentar"][0]
    telefones = unico["IdentificacaoParlamentar"]["Telefones"]
    telefones["Telefone"] = telefones["Telefone"][0]
    parlamentares["Parlamentar"] = unico

    cliente = senado_falso(lambda _r: httpx.Response(200, json=corpo))
    [s] = cliente.senadores()
    assert s.telefones == ("3303-6333",)


def test_whitelist_descarta_dados_pessoais(tmp_path, senado):
    assert CAMPOS_PROIBIDOS <= carregar("senado_lista.json")["ListaParlamentarEmExercicio"]["Parlamentares"]["Parlamentar"][0]["IdentificacaoParlamentar"].keys()

    saida = tmp_path / "senadores.json"
    coletar(senado, saida, minimo=1)
    texto = saida.read_text(encoding="utf-8")
    for s in json.loads(texto)["senadores"]:
        assert set(s) == {f.name for f in fields(Senador)}
    assert "Masculino" not in texto
    assert "Alan Rick Miranda" not in texto  # nome civil completo


def test_resposta_incompleta_aborta_sem_sobrescrever(tmp_path, senado):
    saida = tmp_path / "senadores.json"
    coletar(senado, saida, minimo=1)
    antes = saida.read_text(encoding="utf-8")

    with pytest.raises(ColetaIncompleta):
        coletar(senado, saida)  # mínimo padrão (70) > 5 da fixture
    assert saida.read_text(encoding="utf-8") == antes


def test_ida_e_volta_dict(senado):
    for s in senado.senadores():
        assert Senador.de_dict(json.loads(json.dumps(s.para_dict()))) == s

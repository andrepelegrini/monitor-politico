import pytest

from monitor_politico import compartilhar
from monitor_politico.models import Deputado, Gabinete

DEPUTADO = Deputado(
    id=1, nome="Fulana & Cia", partido="PSB", uf="SP", url_foto=None, situacao="Exercício", condicao_eleitoral="Titular",
    gabinete=Gabinete(None, None, None, None, None), uri_api="", url_site="",
)
VISAO = {
    "coleta_local": "2026-11-05",
    "plenario": {"votos_registrados": 957, "votacoes_nominais": 1126, "presenca": {"total": {"presencas": 377, "dias": 399}}},
    "dinheiro": {"cota": {"total": 1964701.47}},
    "propostas": {"normas": [1] * 17, "normas_principais": [1] * 6, "palavra_norma": "lei", "ano_inicial": "2019"},
}


def test_numeros_iguais_aos_do_topo_da_pagina():
    numeros = compartilhar.numeros_do_perfil(VISAO)
    assert [valor for valor, _ in numeros] == ["957", "377", "R$ 1,96 milhão", "17"]
    assert numeros[3][1] == "propostas viraram lei desde 2019, 6 de autoria principal"


def test_perfil_sem_todas_as_secoes():
    assert compartilhar.numeros_do_perfil({"coleta_local": "2026-11-05"}) == []
    uma = {**VISAO, "propostas": {"normas": [1], "normas_principais": [], "palavra_norma": "norma", "ano_inicial": "2023"}}
    assert compartilhar.numeros_do_perfil(uma)[3][1] == "proposta virou norma desde 2023, 0 de autoria principal"


def test_svg_escapa_texto_e_traz_a_data():
    svg = compartilhar.svg_do_perfil(DEPUTADO, VISAO)
    assert "Fulana &amp; Cia" in svg and "Fulana & Cia" not in svg
    assert "05/11/2026" in svg and "Na Galeria" in svg
    assert "<image" not in svg


def test_svg_com_foto():
    assert 'href="data:image/jpeg;base64,QUJD"' in compartilhar.svg_do_perfil(DEPUTADO, VISAO, "QUJD")


@pytest.mark.parametrize("nome, tamanho", [("Tabata Amaral", 76), ("Nome Muito Longo de Parlamentar Eleito", 58)])
def test_nome_longo_usa_fonte_menor(nome, tamanho):
    assert compartilhar._tamanho_do_nome(nome) == tamanho

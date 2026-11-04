from datetime import date

import pytest

from conftest import congresso_falso
from monitor_politico import painel
from monitor_politico.congresso import coletar


@pytest.fixture(scope="module")
def doc(tmp_path_factory):
    return coletar(*congresso_falso(), tmp_path_factory.mktemp("c") / "c.json", hoje=date(2026, 11, 2))


@pytest.mark.parametrize("data_hora, esperado", [
    ("2026-11-03T14:00", "Terça, 03/11 · 14h"),
    ("2026-11-03T13:55", "Terça, 03/11 · 13h55"),
    ("2026-11-06", "Sexta, 06/11"),
])
def test_rotulo_sessao(data_hora, esperado):
    assert painel.rotulo_sessao(data_hora) == esperado


def test_texto_placar():
    assert painel.texto_placar({"nominal": False, "placar": None}) == "Votação simbólica"
    nominal = {"nominal": True, "placar": {"sim": 461, "nao": 4, "abstencao": 0, "outros": []}}
    assert painel.texto_placar(nominal) == "461 sim · 4 não"
    nominal["placar"]["abstencao"] = 2
    assert painel.texto_placar(nominal) == "461 sim · 4 não · 2 abstenções"


def test_orientacao_do_partido_inclui_federacao():
    orientacoes = [["PL", "Sim"], ["Fdr PT-PCdoB-PV", "Não"], ["Bl UniPpPsd...", "Sim"], ["PSB", None]]
    assert painel._orientacao_do_partido("PL", orientacoes) == "Sim"
    assert painel._orientacao_do_partido("PCdoB", orientacoes) == "Não"
    assert painel._orientacao_do_partido("PSB", orientacoes) == "Não orientou"
    assert painel._orientacao_do_partido("PP", orientacoes) is None  # bloco abreviado pela API
    assert painel._orientacao_do_partido("PL", None) is None


def test_votadas_so_tem_merito_no_periodo(doc):
    linhas = painel.votadas(doc)
    assert [l["sigla"] for l in linhas] == ["PDL 274/2026", "PLP 186/2026", "PEC 221/2019"]
    plp = linhas[1]
    assert [v["casa"] for v in plp["votos"]] == ["Senado", "Câmara"]  # mais recente primeiro
    assert plp["situacao"] == "virou Lei Complementar 238/2026"
    assert plp["nominal"] and plp["resultados"] == ["aprovada"]


def test_temas_em_destaque_contam_votadas_e_pauta(doc):
    temas = dict(painel.temas_em_destaque(doc, painel.votadas(doc)))
    assert temas["Trabalho e Emprego"] == 2  # PLP 186/2026 e PEC 221/2019
    assert "Homenagens e Datas Comemorativas" in temas  # PL 3099/2019, só na pauta


def test_etapas_terminam_na_pauta_futura(doc):
    etapas = painel.etapas(doc["proposicoes"]["PDL 274/2026"], doc["pauta"])
    assert etapas[0]["titulo"] == "Apresentada"
    assert etapas[-1] == {"data": "2026-11-03", "casa": "Câmara", "titulo": "Na pauta do Plenário", "detalhe": "Terça, 03/11 · 13h55", "futuro": True}


def test_barra_da_votacao_soma_todas_as_categorias():
    votacao = {
        "id": "v1", "casa": "Câmara", "data_hora": "2026-10-14T18:00", "descricao": "", "nominal": True, "procedimento": False,
        "resultado": "aprovada", "votos": [], "orientacoes": None,
        "placar": {"sim": 6, "nao": 2, "abstencao": 1, "outros": [["Obstrução", 1]]},
    }
    card = painel.votacoes_da_pagina({"votacoes": [votacao]}, set(), set())["principais"][0]
    assert card["total_votos"] == 10
    assert (card["p_sim"], card["p_nao"], card["p_abstencao"], card["p_outros"]) == ("60.0%", "20.0%", "10.0%", "10.0%")

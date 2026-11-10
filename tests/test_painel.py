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


def test_destaques_seguem_a_regra_fixa_e_explicam_o_quorum():
    def votacao(casa, data, sim, nao, resultado, nominal=True):
        return {"casa": casa, "data_hora": data + "T18:00:00", "procedimento": False, "nominal": nominal, "resultado": resultado,
                "placar": {"sim": sim, "nao": nao} if nominal else None}
    def prop(chave, votacoes, norma=None):
        return {"chave": chave, "slug": chave.lower().replace(" ", "-").replace("/", "-"), "sigla": chave.split()[0], "ementa": "Ementa de " + chave,
                "temas": ["Economia"], "situacao": {"norma": norma} if norma else None, "votacoes": votacoes}
    doc = {"periodo": {"votacoes_desde": "2026-10-01"}, "proposicoes": {
        "PL 1/2026": prop("PL 1/2026", [votacao("Câmara", "2026-11-05", 300, 10, "aprovada")]),
        "PLP 2/2026": prop("PLP 2/2026", [votacao("Câmara", "2026-10-14", 252, 176, "rejeitada")]),
        "PEC 3/2026": prop("PEC 3/2026", [votacao("Senado", "2026-10-10", 70, 1, "aprovada")], norma="Emenda Constitucional 1/2026"),
        "PL 4/2026": prop("PL 4/2026", [votacao("Câmara", "2026-11-06", 0, 0, "aprovada", nominal=False)]),
        "PL 5/2026": prop("PL 5/2026", [votacao("Câmara", "2026-09-01", 300, 10, "aprovada")]),
    }}
    lista = painel.destaques(doc)
    assert [d["sigla"] for d in lista] == ["PEC 3/2026", "PLP 2/2026", "PL 1/2026"]
    assert lista[0]["resultado"] == "Virou a Emenda Constitucional 1/2026" and lista[0]["estado"] == "norma"
    assert lista[1]["nota"] == "Teve mais votos Sim, mas um projeto de lei complementar precisa de pelo menos 257 votos na Câmara."
    assert lista[2]["resultado"] == "Aprovada na Câmara em 05/11" and lista[2]["nota"] is None
    # Sem resumo nem apelido, o título já é a ementa: ela não aparece duas vezes.
    assert lista[2]["titulo"] == "Ementa de PL 1/2026" and lista[2]["muda"] == "" and not lista[2]["de_resumo"]


def test_primeira_frase_corta_no_fim_da_frase():
    assert painel.primeira_frase("Curta.") == "Curta."
    assert painel.primeira_frase("Uma frase. " + "palavra " * 60, 40) == "Uma frase."

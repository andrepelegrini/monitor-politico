import json
from types import SimpleNamespace

from test_perfis import DINHEIRO, PLENARIO, doc, docs  # noqa: F401  (fixtures)
from monitor_politico import comparar
from monitor_politico.build import construir


def pessoa(id_=1):
    return SimpleNamespace(id=id_, nome="Pessoa Um", partido="PSB", uf="SP", url_foto=None)


def test_resumo_com_limite_da_cota_e_verba_de_gabinete():
    doc_ = {
        "eleicoes": [{"ano": 2018, "votos": 10}, {"ano": 2022, "votos": 20}, {"ano": 2026, "votos": 30}, {"ano": 2021, "votos": 0}],
        "dinheiro": {
            "cota": {"por_ano": [{"total": 90.0, "percentual": 90.0}, {"total": 50.0, "percentual": 50.0}, {"total": 0.0, "percentual": 0.0}],
                     "categorias": [["Passagens aéreas", 100.0], ["Telefonia", 40.0]]},
            "gabinete": {"por_ano": [{"total": 900.0, "nao_utilizado": 100.0}, {"total": 300.0, "nao_utilizado": 700.0}]},
        },
    }
    r = comparar.resumo(pessoa(), doc_, {"votos": 3}, 2022)
    assert r["eleicao"] == [2022, 20]  # a eleição do mandato atual, não a de 2026
    assert r["cota"] == {"total": 140.0, "limite": 200.0, "maior": ["Passagens aéreas", 100.0]}
    assert r["gabinete"] == {"total": 1200.0, "disponivel": 2000.0}
    assert r["m"] == {"votos": 3}


def test_senado_sem_percentual_nao_tem_limite_nem_gabinete():
    doc_ = {"eleicoes": [], "dinheiro": {"cota": {"por_ano": [{"total": 10.0, "percentual": None}], "categorias": []}}}
    r = comparar.resumo(pessoa(), doc_, None, 2022)
    assert r["cota"] == {"total": 10.0, "limite": None, "maior": None} and r["gabinete"] is None and r["eleicao"] is None


def test_concordancia_so_conta_sim_e_nao_em_comum():
    a = comparar.votos({"plenario": {"votos": {"votos": [{"id": "1", "voto": "Sim"}, {"id": "2", "voto": "Não"}, {"id": "3", "voto": "Sim"}, {"id": "4", "voto": "Abstenção"}]}}})
    b = comparar.votos({"plenario": {"votos": {"votos": [{"id": "1", "voto": "Sim"}, {"id": "2", "voto": "Sim"}, {"id": "4", "voto": "Sim"}, {"id": "5", "voto": "Não"}]}}})
    assert a == {"s": ["1", "3"], "n": ["2"]}
    assert comparar.concordancia(a, b) == (1, 2)
    assert comparar.votos({}) == {"s": [], "n": []}


def test_site_gera_comparacao_e_entradas(tmp_path, docs, doc):  # noqa: F811
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "plenario": PLENARIO, "dinheiro": {**DINHEIRO, "gabinete": {"por_ano": [{"ano": 2023, "total": 10.0, "percentual": 50.0, "nao_utilizado": 10.0}]}}}})
    site = tmp_path / "site"
    dados = json.loads((site / "static" / "comparar" / "deputados.json").read_text(encoding="utf-8"))
    assert [p["id"] for p in dados["pessoas"]] == [alvo]  # só quem tem perfil completo
    assert dados["pessoas"][0]["gabinete"] == {"total": 10.0, "disponivel": 20.0}
    assert json.loads((site / "static" / "comparar" / "deputados" / f"{alvo}.json").read_text()) == {"s": [], "n": ["10-1"]}
    pagina = (site / "deputados" / "comparar.html").read_text(encoding="utf-8")
    assert 'data-dados="../static/comparar/deputados.json"' in pagina and "static/comparar.js" in pagina
    assert "R$ 46.366,19 por mês" in pagina and "ainda não é coletada para o Senado" not in pagina
    for genero in ("eleita", "eleito", "outro deputado"):
        assert genero not in pagina
    perfil = (site / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert f'href="comparar.html#{alvo}"' in perfil and "Comparar lado a lado" in perfil
    lista = (site / "deputados" / "index.html").read_text(encoding="utf-8")
    assert 'href="comparar.html"' in lista and lista.count('class="cmp-marca"') == len(docs[0]["deputados"]) and "lista-comparar.js" in lista
    assert 'id="comparar"' in (site / "entenda.html").read_text(encoding="utf-8")
    # Sem perfis completos, nada de comparar.
    construir(*docs, tmp_path / "sem")
    assert not (tmp_path / "sem" / "deputados" / "comparar.html").exists()
    assert "cmp-marca" not in (tmp_path / "sem" / "deputados" / "index.html").read_text(encoding="utf-8")

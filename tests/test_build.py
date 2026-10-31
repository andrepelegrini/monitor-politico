from monitor_politico.build import chave_alfabetica, construir
from monitor_politico.camara import coletar


def test_ordem_alfabetica_ignora_acentos_e_maiusculas():
    nomes = ["AJ Albuquerque", "Ácio", "Acácio Favacho", "Érika", "Eduardo"]
    assert sorted(nomes, key=chave_alfabetica) == ["Acácio Favacho", "Ácio", "AJ Albuquerque", "Eduardo", "Érika"]


def test_gera_lista_e_um_perfil_por_deputado(tmp_path, cliente):
    doc = coletar(cliente, tmp_path / "d.json")
    site = tmp_path / "site"
    construir(doc, site)

    perfis = sorted(p.stem for p in (site / "deputados").glob("*.html"))
    assert perfis == sorted(str(d["id"]) for d in doc["deputados"])
    assert (site / "static" / "filtro.js").exists()

    index = (site / "index.html").read_text(encoding="utf-8")
    assert '<span id="contagem">4</span> de 4 deputados' in index
    assert '<option>MDB</option>' in index
    assert 'href="./deputados/204379.html"' in index
    assert "Dados atualizados em" in index


def test_perfil_mostra_fonte_e_contato(tmp_path, cliente):
    construir(coletar(cliente, tmp_path / "d.json"), tmp_path / "site")
    perfil = (tmp_path / "site" / "deputados" / "204379.html").read_text(encoding="utf-8")

    assert "Acácio Favacho" in perfil
    assert "https://www.camara.leg.br/deputados/204379" in perfil
    assert "https://dadosabertos.camara.leg.br/api/v2/deputados/204379" in perfil
    assert "dep.acaciofavacho@camara.leg.br" in perfil
    assert 'href="../static/estilo.css"' in perfil
    assert "horário de Brasília" in perfil

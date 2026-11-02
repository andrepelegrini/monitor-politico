import pytest

from monitor_politico.build import chave_alfabetica, construir
from monitor_politico.camara import coletar as coletar_camara
from monitor_politico.senado import coletar as coletar_senado


def test_ordem_alfabetica_ignora_acentos_e_maiusculas():
    nomes = ["AJ Albuquerque", "Ácio", "Acácio Favacho", "Érika", "Eduardo"]
    assert sorted(nomes, key=chave_alfabetica) == ["Acácio Favacho", "Ácio", "AJ Albuquerque", "Eduardo", "Érika"]


@pytest.fixture
def site(tmp_path, cliente, senado):
    docs = (
        coletar_camara(cliente, tmp_path / "d.json"),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
    )
    construir(*docs, tmp_path / "site")
    return tmp_path / "site", docs


def test_inicio_aponta_para_as_duas_casas(site):
    pasta, _ = site
    inicio = (pasta / "index.html").read_text(encoding="utf-8")
    assert 'href="./deputados/index.html"' in inicio
    assert 'href="./senadores/index.html"' in inicio
    assert "4 deputados" in inicio
    assert "5 senadores" in inicio
    assert (pasta / "static" / "filtro.js").exists()


def test_gera_lista_e_um_perfil_por_parlamentar(site):
    pasta, (doc_dep, doc_sen) = site
    for casa, doc in (("deputados", doc_dep), ("senadores", doc_sen)):
        perfis = sorted(p.stem for p in (pasta / casa).glob("*.html") if p.stem != "index")
        assert perfis == sorted(str(p["id"]) for p in doc[casa])

    deputados = (pasta / "deputados" / "index.html").read_text(encoding="utf-8")
    assert '<span id="contagem">4</span> de 4 deputados' in deputados
    assert '<option>MDB</option>' in deputados
    assert 'href="204379.html"' in deputados
    assert 'href="../senadores/index.html"' in deputados
    assert "Dados Abertos da Câmara" in deputados

    senadores = (pasta / "senadores" / "index.html").read_text(encoding="utf-8")
    assert '<span id="contagem">5</span> de 5 senadores' in senadores
    assert '<option>PP</option>' in senadores
    assert 'aria-current="page">Senadores' in senadores
    assert "Dados Abertos do Senado" in senadores


def test_perfil_deputado_mostra_fonte_e_contato(site):
    pasta, _ = site
    perfil = (pasta / "deputados" / "204379.html").read_text(encoding="utf-8")
    assert "Acácio Favacho" in perfil
    assert "https://www.camara.leg.br/deputados/204379" in perfil
    assert "https://dadosabertos.camara.leg.br/api/v2/deputados/204379" in perfil
    assert "dep.acaciofavacho@camara.leg.br" in perfil
    assert 'href="../static/estilo.css"' in perfil
    assert "horário de Brasília" in perfil


def test_perfil_senador_mostra_mandato_e_telefones(site):
    pasta, _ = site
    perfil = (pasta / "senadores" / "739.html").read_text(encoding="utf-8")
    assert "Ciro Nogueira" in perfil
    assert "(61) 3303-6187<br>(61) 3303-6188" in perfil
    assert "Mandato até</dt><dd>31/01/" in perfil
    assert "https://www25.senado.leg.br/web/senadores/senador/-/perfil/739" in perfil
    assert 'href="../static/estilo.css"' in perfil

from datetime import date

import pytest

from conftest import congresso_falso
from monitor_politico.build import chave_alfabetica, construir
from monitor_politico.camara import coletar as coletar_camara
from monitor_politico.congresso import coletar as coletar_congresso
from monitor_politico.senado import coletar as coletar_senado


def test_ordem_alfabetica_ignora_acentos_e_maiusculas():
    nomes = ["AJ Albuquerque", "Ácio", "Acácio Favacho", "Érika", "Eduardo"]
    assert sorted(nomes, key=chave_alfabetica) == ["Acácio Favacho", "Ácio", "AJ Albuquerque", "Eduardo", "Érika"]


@pytest.fixture
def site(tmp_path, cliente, senado):
    docs = (
        coletar_camara(cliente, tmp_path / "d.json", senado=senado),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )
    construir(*docs, tmp_path / "site")
    return tmp_path / "site", docs


def test_inicio_mostra_pauta_votadas_e_temas(site):
    pasta, _ = site
    inicio = (pasta / "index.html").read_text(encoding="utf-8")
    assert 'href="./deputados/index.html"' in inicio
    assert 'href="./senadores/index.html"' in inicio
    assert 'aria-current="page">Início' in inicio
    # Pauta das duas casas, com link para a página de cada proposição.
    assert "PEC da Segurança Pública" in inicio
    assert 'href="proposicoes/pl-3099-2019.html"' in inicio
    # Votadas: a de mérito mais recente por casa, com placar ou "simbólica".
    assert '<span id="contagem">3</span> de 3 proposições' in inicio
    assert "Fim da escala 6x1" in inicio
    assert "Votação simbólica" in inicio
    assert 'data-tema="Trabalho e Emprego"' in inicio
    for estatico in ("filtro.js", "painel.js", "estilo.css"):
        assert (pasta / "static" / estatico).exists()


def test_gera_lista_e_um_perfil_por_parlamentar(site):
    pasta, (doc_dep, doc_sen, _doc_con) = site
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


def test_pagina_da_proposicao(site):
    pasta, (_dep, _sen, doc_con) = site
    assert sorted(p.stem for p in (pasta / "proposicoes").glob("*.html")) == sorted(p["slug"] for p in doc_con["proposicoes"].values())

    plp = (pasta / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert "Virou Lei Complementar 238/2026" in plp
    assert "Ementa oficial" in plp
    assert "Aprovada no Plenário" in plp
    # Abas: votações de mérito antes da de rito.
    abas = plp.index("Câmara · 14/10 ("), plp.index("Senado · 15/10 ("), plp.index("Câmara · 14/10 · rito (")
    assert abas == tuple(sorted(abas))
    assert "Orientação dos partidos e blocos" in plp
    assert "O Senado não publica a orientação dos partidos" in plp
    assert 'href="../senadores/5672.html"' in plp  # senador com perfil no site

    pdl = (pasta / "proposicoes" / "pdl-274-2026.html").read_text(encoding="utf-8")
    assert "Votação simbólica" in pdl
    assert "Nenhuma votação desta proposição no período foi nominal" in pdl
    assert "Na pauta do Plenário" in pdl  # volta à pauta da Câmara em 03/11


def test_resumo_nas_paginas_das_casas(site):
    pasta, _ = site
    deputados = (pasta / "deputados" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Câmara dos Deputados</h1>" in deputados
    assert "Deputados por partido" in deputados
    assert 'data-filtro-partido="MDB"' in deputados
    assert 'data-filtro-uf="SP"' in deputados
    assert "Quem conduz a Câmara" in deputados and "Hugo Motta" in deputados
    assert "Titulares e suplentes" in deputados
    assert deputados.index("Deputados por partido") < deputados.index('id="lista"')  # resumo antes dos nomes

    senadores = (pasta / "senadores" / "index.html").read_text(encoding="utf-8")
    assert "Blocos parlamentares" in senadores and "Mandatos" in senadores
    assert "Mulheres e homens" in senadores
    assert 'href="739.html">Ciro Nogueira</a>' in senadores  # líder com perfil no site
    assert "Bancadas por estado" not in senadores

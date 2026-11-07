import json
import re
from datetime import date
from pathlib import Path

import pytest

from conftest import congresso_falso
from monitor_politico.build import chave_alfabetica, construir, url_do_site
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


def test_resumo_por_ia_quando_existe(tmp_path, cliente, senado):
    docs = (
        coletar_camara(cliente, tmp_path / "d.json"),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )
    resumos = {"resumos": {"PLP 186/2026": {
        "titulo": "Novo limite de faturamento do MEI", "o_que_muda": "Aumenta o limite.",
        "quem_e_afetado": "Microempreendedores.", "fonte": "texto integral",
    }}}
    construir(*docs, tmp_path / "com", resumos)
    construir(*docs, tmp_path / "sem")

    inicio = (tmp_path / "com" / "index.html").read_text(encoding="utf-8")
    assert "Novo limite de faturamento do MEI" in inicio
    assert "gerados automaticamente por IA" in inicio
    plp = (tmp_path / "com" / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert "<h1>Novo limite de faturamento do MEI</h1>" in plp
    assert "Gerado automaticamente por IA a partir do texto oficial" in plp
    assert "Ementa oficial" in plp

    sem = (tmp_path / "sem" / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert "Gerado automaticamente" not in sem and "<h1>PLP 186/2026</h1>" in sem
    assert "gerados automaticamente por IA" not in (tmp_path / "sem" / "index.html").read_text(encoding="utf-8")


def test_busca_unica_no_topo_e_indice(site):
    pasta, (doc_dep, doc_sen, doc_con) = site
    for pagina in ("index.html", "deputados/index.html", "deputados/204379.html", "entenda.html"):
        html = (pasta / pagina).read_text(encoding="utf-8")
        assert 'id="busca-q"' in html
        assert "/static/busca.js" in html
    perfil = (pasta / "deputados" / "204379.html").read_text(encoding="utf-8")
    assert 'data-raiz=".."' in perfil

    indice = json.loads((pasta / "static" / "busca.json").read_text(encoding="utf-8"))
    assert len(indice["parlamentares"]) == len(doc_dep["deputados"]) + len(doc_sen["senadores"])
    assert ["Acácio Favacho", "D", "MDB", "AP", "deputados/204379.html"] in indice["parlamentares"]
    assert any(p[1] == "S" and p[4] == "senadores/739.html" for p in indice["parlamentares"])
    nomes = [p[0] for p in indice["parlamentares"]]
    assert nomes == sorted(nomes, key=chave_alfabetica)  # Câmara e Senado misturados em ordem alfabética
    assert sorted(p[2] for p in indice["proposicoes"]) == sorted(f"proposicoes/{p['slug']}.html" for p in doc_con["proposicoes"].values())
    assert all(p[1] for p in indice["proposicoes"])  # sempre há um texto para mostrar


def test_pagina_entenda_os_dados(site):
    pasta, _ = site
    entenda = (pasta / "entenda.html").read_text(encoding="utf-8")
    assert "<h1>Entenda os dados</h1>" in entenda
    assert 'id="simbolica"' in entenda and 'id="rito"' in entenda
    assert "Não é publicada" in entenda  # orientação dos partidos no Senado
    assert "votações registradas" in entenda and "com o voto de cada parlamentar" in entenda
    assert entenda.count('href="./entenda.html"') == 0  # sem link para si mesma no rodapé
    inicio = (pasta / "index.html").read_text(encoding="utf-8")
    assert 'href="./entenda.html"' in inicio
    assert 'href="entenda.html#rito"' in inicio


def test_sem_endereco_do_site_nao_gera_tags_absolutas(site):
    pasta, _ = site
    perfil = (pasta / "deputados" / "204379.html").read_text(encoding="utf-8")
    assert '<meta property="og:title" content="Acácio Favacho (MDB-AP) · Câmara dos Deputados">' in perfil
    assert "og:image" not in perfil and "og:url" not in perfil


def test_tags_de_compartilhamento_com_endereco(tmp_path, site):
    _, docs = site
    construir(*docs, tmp_path / "site2", site_url="https://monitor.exemplo.br/")
    pasta = tmp_path / "site2"
    plp = (pasta / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert '<meta property="og:url" content="https://monitor.exemplo.br/proposicoes/plp-186-2026.html">' in plp
    assert '<meta property="og:image" content="https://monitor.exemplo.br/static/brand/social/open-graph-1200x630.png">' in plp
    assert '<meta property="og:description" content="Virou Lei Complementar 238/2026.' in plp
    inicio = (pasta / "index.html").read_text(encoding="utf-8")
    assert '<meta property="og:url" content="https://monitor.exemplo.br/index.html">' in inicio
    assert '<meta property="og:title" content="O que está em discussão no Congresso">' in inicio
    assert (pasta / "static" / "brand" / "social" / "open-graph-1200x630.png").exists()
    assert (pasta / "static" / "brand" / "favicon" / "site.webmanifest").exists()
    assert '<meta name="twitter:image" content="https://monitor.exemplo.br/static/brand/social/twitter-card-1200x600.png">' in plp


def test_url_do_site():
    assert url_do_site({}) == ""
    assert url_do_site({"VERCEL_PROJECT_PRODUCTION_URL": "monitor-politico.vercel.app"}) == "https://monitor-politico.vercel.app"
    assert url_do_site({"SITE_URL": "https://meu.dominio.br/", "VERCEL_PROJECT_PRODUCTION_URL": "x.vercel.app"}) == "https://meu.dominio.br"


def test_design_system_aplicado_em_todas_as_paginas(site):
    pasta, _ = site
    for pagina in pasta.rglob("*.html"):
        html = pagina.read_text(encoding="utf-8")
        assert '<body class="ce-app">' in html, pagina
        assert 'href="#conteudo"' in html and 'id="conteudo"' in html, pagina
        # Tokens, base e componentes antes da camada da aplicação.
        ordem = [html.index(f"/static/{css}") for css in ("ce-tokens.css", "ce-base.css", "ce-components.css", "estilo.css")]
        assert ordem == sorted(ordem), pagina
    for css in ("ce-tokens.css", "ce-base.css", "ce-components.css"):
        assert (pasta / "static" / css).exists()


def test_css_do_design_system_e_copia_exata_do_pacote():
    raiz = Path(__file__).parent.parent
    estaticos = raiz / "src" / "monitor_politico" / "static"
    for copia, original in (
        ("ce-tokens.css", "tokens/design-tokens.css"),
        ("ce-base.css", "tokens/base.css"),
        ("ce-components.css", "components/components.css"),
    ):
        assert (estaticos / copia).read_bytes() == (raiz / "design-system" / original).read_bytes(), copia


def test_paginas_sem_dados_de_demonstracao(site):
    pasta, _ = site
    for pagina in pasta.rglob("*.html"):
        html = pagina.read_text(encoding="utf-8")
        for demo in ("fictíci", "Observatório", "Parlamentar A<", "PL 1234/2026", "PEC 99/2026"):
            assert demo not in html, (pagina, demo)


def test_resultado_e_voto_sem_julgamento_por_cor(site):
    pasta, _ = site
    plp = (pasta / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert '<span class="ce-badge resultado-aprovada">Aprovada</span>' in plp
    assert 'class="ce-vote-yes"' in plp and 'class="ce-vote-no"' in plp
    assert "registros nominais nesta votação" in plp  # denominador explícito
    assert "<caption" in plp and '<th scope="col">Voto</th>' in plp
    estilo = (pasta / "static" / "estilo.css").read_text(encoding="utf-8")
    assert "prefers-color-scheme" not in estilo
    # Aprovada e rejeitada têm cor própria, mas nos tons do voto, sem verde e vermelho de certo e errado.
    regra = {r: re.search(rf"\.resultado-{r} \{{ background: #(\w+); color: #(\w+)", estilo).groups() for r in ("aprovada", "rejeitada")}
    for fundo, texto in regra.values():
        for cor in (fundo, texto):
            vermelho, verde, azul = (int(cor[i:i + 2], 16) for i in (0, 2, 4))
            assert not (verde > vermelho + 20 and verde > azul + 20), f"#{cor} é verde"
            assert not (vermelho > verde + 60 and vermelho > azul + 60 and verde < 90), f"#{cor} é vermelho"


def test_estados_previsto_e_vazio(site):
    pasta, _ = site
    pdl = (pasta / "proposicoes" / "pdl-274-2026.html").read_text(encoding="utf-8")
    assert "Previsto" in pdl and "Evento programado. A agenda pode mudar." in pdl
    for pagina in ("index.html", "deputados/index.html", "senadores/index.html"):
        assert "data-limpar-filtros" in (pasta / pagina).read_text(encoding="utf-8"), pagina

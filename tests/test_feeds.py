import xml.etree.ElementTree as ET

from test_legislatura import docs  # noqa: F401  (fixture)
from monitor_politico import feeds
from monitor_politico.build import construir


def itens(xml):
    return ET.fromstring(xml).find("channel").findall("item")


def test_documento_valido_ordenado_e_limitado():
    lista = [{"titulo": f"PL {i} & <b>", "link": "https://x/a?b=1&c=2", "guid": str(i), "data": f"2026-01-{i:02d}", "texto": "Texto"} for i in range(1, 29)]
    lista += [{"titulo": "Hora", "link": "https://x", "guid": "h", "data": "2026-02-01T21:34:40", "texto": ""}]
    lista *= 2
    xml = feeds.documento("Título", "https://x/p.html", "https://x/f.xml", "Descrição", lista)
    raiz = ET.fromstring(xml)
    assert raiz.get("version") == "2.0" and raiz.find("channel/language").text == "pt-BR"
    achados = itens(xml)
    assert len(achados) == feeds.MAX_ITENS
    assert achados[0].find("title").text == "Hora" and achados[0].find("pubDate").text == "Sun, 01 Feb 2026 21:34:40 -0300"
    assert achados[2].find("title").text == "PL 28 & <b>" and achados[2].find("pubDate").text.endswith("12:00:00 -0300")
    assert raiz.find("channel/lastBuildDate").text == "Sun, 01 Feb 2026 21:34:40 -0300"


def test_proposicao_sem_procedimento_e_com_situacao():
    prop = {
        "chave": "PEC 1/2025", "slug": "pec-1-2025", "situacao": {"descricao": "Aprovada", "data": "2026-11-03", "casa": "Senado", "norma": None},
        "votacoes": [
            {"id": "a", "casa": "Senado", "data_hora": "2026-11-03", "descricao": "Requerimento", "resultado": "aprovado", "procedimento": True, "nominal": False, "placar": None},
            {"id": "b", "casa": "Senado", "data_hora": "2026-11-03", "descricao": "1º turno", "resultado": "aprovada", "procedimento": False, "nominal": True,
             "placar": {"sim": 75, "nao": 0, "abstencao": 0, "outros": []}},
            {"id": "c", "casa": "Câmara", "data_hora": "2026-10-01T20:00:00", "descricao": "Texto", "resultado": "aprovada", "procedimento": False, "nominal": False, "placar": None},
        ],
    }
    lista = feeds.da_proposicao(prop, "https://s")
    assert [i["titulo"] for i in lista] == [
        "PEC 1/2025 · Senado, 03/11/2026: aprovada, 75 sim · 0 não",
        "PEC 1/2025 · Câmara, 01/10/2026: aprovada, em votação simbólica",
        "PEC 1/2025 · Situação: Aprovada (Senado, desde 03/11)",
    ]
    assert all(i["link"] == "https://s/proposicoes/pec-1-2025.html" for i in lista)


def test_votos_do_parlamentar_com_link_certo():
    base = {"data": "2026-10-14", "sim": 400, "nao": 4, "outros": 1, "descricao": "Aprovado o texto.", "ementa": "Altera a lei."}
    lista = feeds.do_parlamentar([
        {**base, "id": "1", "voto": "Sim", "sigla": "PL 1/2026", "slug": "pl-1-2026", "proposicao_id": "9"},
        {**base, "id": "2", "voto": "Abstenção", "sigla": "PL 2/2026", "proposicao_id": "9", "url": "https://senado/m/2"},
        {**base, "id": "3", "voto": "Não", "sigla": None, "proposicao_id": "77"},
    ], "https://s")
    assert [i["titulo"] for i in lista] == ["Votou Sim · PL 1/2026", "Abstenção · PL 2/2026", "Votou Não · Votação"]
    assert [i["link"] for i in lista] == ["https://s/proposicoes/pl-1-2026.html", "https://senado/m/2", "https://www.camara.leg.br/propostas-legislativas/77"]
    assert lista[0]["texto"].endswith("Demais votos: 400 Sim, 4 Não, 1 outro.")


def test_site_gera_feeds_e_links(tmp_path, docs):  # noqa: F811
    construir(*docs, tmp_path / "site", site_url="https://exemplo.org")
    site = tmp_path / "site"
    geral = (site / "feeds" / "votacoes.xml").read_text(encoding="utf-8")
    assert itens(geral) and "https://exemplo.org/proposicoes/" in geral
    votacoes = (site / "votacoes.html").read_text(encoding="utf-8")
    assert 'href="./feeds/votacoes.xml"' in votacoes and votacoes.count('type="application/rss+xml"') == 2  # cabeçalho e link visível
    inicio = (site / "index.html").read_text(encoding="utf-8")
    assert '<link rel="alternate" type="application/rss+xml" title="Votações no Plenário · Na Galeria" href="./feeds/votacoes.xml">' in inicio
    pagina = (site / "proposicoes" / "plp-186-2026.html").read_text(encoding="utf-8")
    assert 'href="../feeds/proposicoes/plp-186-2026.xml"' in pagina and "Acompanhar esta proposição por RSS" in pagina
    ET.fromstring((site / "feeds" / "proposicoes" / "plp-186-2026.xml").read_bytes())
    assert 'id="rss"' in (site / "entenda.html").read_text(encoding="utf-8")

from datetime import date

import pytest

from monitor_politico import plenario, propostas

ID = 204534
INICIO = "2023-02-01"


def proposta(id_, tipo="PL", numero="1", ano="2023", data="2023-03-01T10:00", situacao="Aguardando Parecer"):
    return {
        "id": id_, "siglaTipo": tipo, "numero": numero, "ano": ano, "dataApresentacao": data, "ementa": f"Ementa\n de {id_}",
        "ultimoStatus_descricaoSituacao": situacao, "ultimoStatus_dataHora": "2024-05-06T11:00",
    }


def autor(id_, ordem="1", proponente="1", deputado=ID):
    return {"idProposicao": id_, "idDeputadoAutor": str(deputado), "ordemAssinatura": ordem, "proponente": proponente}


class FonteFalsa:
    def linhas(self, tipo, ano):
        return getattr(self, tipo)() if ano == 2023 else []

    def proposicoesAutores(self):
        return [
            autor("1"), autor("2", ordem="5"), autor("3", ordem="90", proponente="0"), autor("4"), autor("5"), autor("6"),
            autor("1", ordem="2", deputado=99), autor("7", deputado=99),
        ]

    def proposicoes(self):
        return [
            proposta("1", situacao="Transformado em Norma Jurídica"),
            proposta("2", numero="2", data="2023-04-01T10:00", situacao="Arquivada"),
            proposta("3", tipo="PEC", numero="3", data="2023-05-01T10:00", situacao=""),
            proposta("4", tipo="REQ", numero="4"),  # requerimento fica de fora
            proposta("5", numero="5", data="2023-01-20T10:00"),  # antes do mandato
            proposta("7", numero="7"),  # de outra pessoa
        ]

    def proposicoesTemas(self):
        return [
            {"uriProposicao": "https://x/proposicoes/1", "tema": "Saúde"},
            {"uriProposicao": "https://x/proposicoes/1", "tema": "Educação"},
            {"uriProposicao": "https://x/proposicoes/1", "tema": "Saúde"},
            {"uriProposicao": "https://x/proposicoes/2", "tema": "Saúde"},
        ]

    def atuacao_oficial(self, _id, ano):
        return {"autoria": 10, "relatadas": 2}


class CamaraFalsa:
    def _get(self, url):
        assert url == "/proposicoes/1/tramitacoes"
        return {"dados": [
            {"dataHora": "2023-12-28T10:00", "despacho": "Transformado na Lei Ordinária 14786/2023. DOU 29/12/23 PÁG 01. Vetado parcialmente.(MSC)"},
            {"dataHora": "2024-02-09T10:00", "despacho": "Remessa de ofício ao Senado."},
        ]}


@pytest.fixture
def doc():
    return propostas.coletar(FonteFalsa(), CamaraFalsa(), ID, INICIO, date(2023, 12, 1))


def test_lista_so_projetos_e_pecs_do_mandato_e_da_pessoa(doc):
    assert [p["sigla"] for p in doc["propostas"]] == ["PEC 3/2023", "PL 2/2023", "PL 1/2023"]


@pytest.mark.parametrize("linha, esperado", [
    (autor("1"), "primeira"), (autor("1", ordem="5"), "coautoria"), (autor("1", ordem="90", proponente="0"), "apoio"),
])
def test_participacao_separa_apoio_em_pec_de_autoria(linha, esperado):
    assert propostas.participacao(linha) == esperado


@pytest.mark.parametrize("situacao, esperado", [
    ("Transformado em Norma Jurídica", "norma"), ("Arquivada", "encerrada"), ("Retirado pelo(a) Autor(a)", "encerrada"),
    ("Aguardando Parecer", "tramitacao"), ("Pronta para Pauta", "tramitacao"), ("", "sem_situacao"),
])
def test_grupo_da_situacao(situacao, esperado):
    assert propostas.grupo_da_situacao(situacao) == esperado


def test_numero_da_norma_vem_da_tramitacao(doc):
    norma = doc["propostas"][2]["norma"]
    assert norma == {"nome": "Lei Ordinária 14786/2023", "data": "2023-12-28", "veto_parcial": True}
    assert doc["propostas"][0]["norma"] is None


def test_norma_sem_despacho_reconhecido():
    assert propostas.norma_da_tramitacao([{"dataHora": "2023-01-01T10:00", "despacho": "Remessa"}]) is None


def test_temas_sem_repeticao_e_texto_limpo(doc):
    assert doc["propostas"][2]["temas"] == ["Educação", "Saúde"]
    assert doc["propostas"][2]["ementa"] == "Ementa de 1"


def test_visao(doc):
    v = propostas.visao(doc, slugs={"PL 1/2023": "pl-1-2023"})
    assert v["total"] == 3
    assert [p["sigla"] for p in v["normas"]] == ["PL 1/2023"]
    assert v["normas"][0]["slug"] == "pl-1-2023"
    assert v["tipos"] == [("PL", 2), ("PEC", 1)]
    assert [(r, n) for r, n, _ in v["participacoes"]] == [("Primeira assinatura", 1), ("Coautoria", 1), ("Apoio", 1)]
    assert {c: n for _, n, c in v["situacoes"]} == {"norma": 1, "encerrada": 1, "sem_situacao": 1}
    assert v["temas"][0] == {"nome": "Saúde", "valor": 2, "largura": 100.0}
    assert v["total_autoria"] == 10 and v["total_relatadas"] == 2


def test_visao_mostra_so_a_ementa_atual(doc):
    doc["propostas"][0]["ementa"] = "Texto antigo. NOVA EMENTA: Texto atual."
    assert propostas.visao(doc)["propostas"][0]["ementa"] == "Texto atual."
    assert plenario.ementa_atual("Sem mudança.") == "Sem mudança."


def test_le_atuacao_da_pagina_oficial():
    pagina = "<h3>Atuação</h3><div>Propostas legislativas de sua autoria</div> <a>103</a> <div>relatadas</div> <a>15</a><script>x</script>"
    assert plenario.ler_atuacao_da_pagina(pagina) == {"autoria": 103, "relatadas": 15}
    with pytest.raises(plenario.RelatorioInvalido):
        plenario.ler_atuacao_da_pagina("<p>outra</p>")

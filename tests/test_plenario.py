from datetime import date

import pytest

from monitor_politico import plenario

ID = 204534
INICIO = "2023-02-01"


@pytest.mark.parametrize("descricao, esperado", [
    ("Aprovado o Projeto de Lei nº 1, de 2024. Sim: 300; Não: 100.", "texto"),
    ("Aprovado o Substitutivo ao Projeto de Lei nº 2, ressalvados os destaques.", "texto"),
    ("Aprovada, em segundo turno, a Proposta de Emenda à Constituição nº 45.", "texto"),
    ("Aprovada a Subemenda Substitutiva Global ao Projeto de Lei nº 3.", "texto"),
    ("Aprovada a Emenda Aglutinativa nº 1. Sim: 300.", "texto"),
    ("Rejeitada a Emenda de Plenário nº 14. Sim: 108; Não: 241.", "ajuste"),
    ("Rejeitada a Emenda de Plenário nº 2 em primeiro turno.", "ajuste"),
    ("Aprovada a Emenda do Senado Federal nº 1.", "ajuste"),
    ("Suprimido o texto. Sim: 62; não: 370.", "ajuste"),
    ("Rejeitado o Recurso nº 2, de 2026.", "ajuste"),
    ("Rejeitada a preferência. Sim: 107; Não: 298.", "procedimento"),
    ("Aprovado o Requerimento de urgência.", "procedimento"),
])
def test_classe_da_votacao(descricao, esperado):
    assert plenario.classe_da_votacao(descricao) == esperado


def test_orientacao_do_partido_e_da_federacao_mas_nao_de_bloco():
    assert plenario.orientacao_do_partido({"PSB": "Sim", "PL": "Não"}, "PSB") == "Sim"
    assert plenario.orientacao_do_partido({"Fdr PT-PCdoB-PV": "Não"}, "PV") == "Não"
    assert plenario.orientacao_do_partido({"Bl MdbPsdRepPode": "Sim"}, "PSB") is None
    assert plenario.orientacao_do_partido({"Fdr PSOL-REDE": "Sim"}, "PL") is None


def _pagina(dias=115, presencas=103, justificadas=10, nao=2):
    linhas = [
        ("Total de dias com sessões deliberativas realizadas no período", dias),
        ("Total de dias com presença nas sessões deliberativas", presencas),
        ("Total de dias com ausências justificadas em sessões deliberativas", justificadas),
        ("Total de dias com ausências não justificadas em sessões deliberativas", nao),
    ]
    return "<table>" + "".join(
        f"<tr>\n<td>\n<b>{rotulo}</b>\n</td>\n<td>\n{valor}\n</td>\n<td>10,00%</td></tr>" for rotulo, valor in linhas
    ) + "</table>"


def test_le_relatorio_oficial_de_presenca():
    assert plenario.ler_relatorio_de_presenca(_pagina()) == {"dias": 115, "presencas": 103, "justificadas": 10, "nao_justificadas": 2}


def test_relatorio_que_mudou_de_formato_ou_nao_fecha_interrompe_a_coleta():
    with pytest.raises(plenario.RelatorioInvalido):
        plenario.ler_relatorio_de_presenca("<p>outra página</p>")
    with pytest.raises(plenario.RelatorioInvalido):
        plenario.ler_relatorio_de_presenca(_pagina(dias=114))


def votacao(id_, data, descricao, orgao="PLEN"):
    return {"id": id_, "data": data, "descricao": descricao, "siglaOrgao": orgao}


class FonteFalsa:
    def linhas(self, tipo, ano):
        return getattr(self, tipo)(ano) if ano == 2023 else []

    def votacoes(self, _ano):
        return [
            votacao("10-1", "2023-03-01", "Aprovado o Projeto de Lei nº 1.\n Sim: 2; Não: 1."),
            votacao("10-2", "2023-03-02", "Rejeitada a Emenda de Plenário nº 1."),
            votacao("10-3", "2023-03-03", "Aprovado o Requerimento de urgência."),
            votacao("20-1", "2023-03-04", "Aprovado o Projeto de Lei nº 2."),
            votacao("30-1", "2023-01-20", "Aprovado o Projeto de Lei nº 3."),  # legislatura anterior
            votacao("40-1", "2023-03-05", "Aprovado o Projeto de Lei nº 4.", orgao="CCJC"),  # comissão
            votacao("50-1", "2023-03-06", "Aprovado o Projeto de Decreto Legislativo nº 5."),
        ]

    def votacoesVotos(self, _ano):
        def voto(id_votacao, deputado, valor):
            return {"idVotacao": id_votacao, "deputado_id": str(deputado), "voto": valor, "deputado_siglaPartido": "PSB"}
        return [
            voto("10-1", ID, "Não"), voto("10-1", 1, "Sim"), voto("10-1", 2, "Sim"), voto("10-1", 3, "Não"), voto("10-1", 4, "Obstrução"),
            voto("10-2", ID, "Sim"), voto("10-2", 1, "Sim"),
            voto("10-3", ID, "Sim"), voto("10-3", 1, "Não"),
            voto("20-1", 1, "Sim"),  # sem voto do parlamentar
            voto("50-1", ID, ""), voto("50-1", 1, ""),  # a fonte não informa as posições individuais
            voto("30-1", ID, "Sim"), voto("40-1", ID, "Sim"),
        ]

    def votacoesProposicoes(self, _ano):
        def objeto(id_votacao, id_proposicao, numero):
            return {
                "idVotacao": id_votacao, "proposicao_id": id_proposicao, "proposicao_siglaTipo": "PL", "proposicao_numero": numero,
                "proposicao_ano": "2023", "proposicao_ementa": f"Ementa {numero}",
            }
        # A primeira linha é só relacionada: o id da votação aponta para a proposição 10.
        return [objeto("10-1", "99", "99"), objeto("10-1", "10", "1"), objeto("10-2", "10", "1"), objeto("10-3", "10", "1")]

    def votacoesOrientacoes(self, _ano):
        return [
            {"idVotacao": "10-1", "siglaBancada": "PSB", "orientacao": "Sim"},
            {"idVotacao": "10-1", "siglaBancada": "PL", "orientacao": "Não"},
        ]

    def proposicoesTemas(self, _ano):
        return [{"uriProposicao": "https://x/proposicoes/10", "tema": "Educação"}, {"uriProposicao": "https://x/proposicoes/10", "tema": "Educação"}]

    def eventos(self, _ano):
        return [
            {"id": "1", "situacao": "Encerrada (Final)", "descricaoTipo": "Sessão Deliberativa", "dataHoraInicio": "2023-03-01T10:00"},
            {"id": "2", "situacao": "Encerrada", "descricaoTipo": "Audiência Pública", "dataHoraInicio": "2023-03-02T10:00"},
            {"id": "3", "situacao": "Cancelada", "descricaoTipo": "Audiência Pública", "dataHoraInicio": "2023-03-03T10:00"},
            {"id": "4", "situacao": "Encerrada", "descricaoTipo": "Reunião Deliberativa", "dataHoraInicio": "2023-01-10T10:00"},
        ]

    def eventosPresencaDeputados(self, _ano):
        return [{"idEvento": e, "idDeputado": str(ID)} for e in "1234"] + [{"idEvento": "2", "idDeputado": "1"}]

    def relatorio_de_presenca(self, _id, ano):
        return {"dias": 10, "presencas": 7, "justificadas": 2, "nao_justificadas": 1}


@pytest.fixture
def doc():
    return plenario.coletar(FonteFalsa(), ID, INICIO, date(2023, 12, 1))


def test_guarda_so_votos_do_mandato_no_plenario(doc):
    v = doc["votos"]
    assert v["votacoes_nominais"] == 4  # 10-1, 10-2, 10-3 e 20-1
    assert v["votos_registrados"] == 3
    assert v["procedimento"] == {"Sim": 1}
    assert [x["id"] for x in v["votos"]] == ["10-2", "10-1"]


def test_voto_traz_placar_dos_demais_e_proposicao_certa(doc):
    voto = doc["votos"]["votos"][1]
    assert (voto["voto"], voto["sim"], voto["nao"], voto["outros"]) == ("Não", 2, 1, 1)
    assert voto["sigla"] == "PL 1/2023"
    assert voto["ementa"] == "Ementa 1"
    assert voto["descricao"] == "Aprovado o Projeto de Lei nº 1. Sim: 2; Não: 1."
    assert voto["orientacao"] == "Sim"
    assert voto["temas"] == ["Educação"]


def test_tira_cpf_citado_em_texto_oficial():
    assert plenario._limpar("Prisão de Fulano (CPF no 750.100.207-00), por decisão") == "Prisão de Fulano (CPF no [CPF omitido]), por decisão"
    assert plenario._limpar("Lei nº 14.786, de 2023; Sim: 123.456") == "Lei nº 14.786, de 2023; Sim: 123.456"


def test_nao_guarda_voto_individual_de_outros_parlamentares(doc):
    assert "deputado_id" not in str(doc)


def test_presenca_conta_outros_eventos_encerrados_do_mandato(doc):
    assert doc["presenca"]["por_ano"] == [{"ano": 2023, "dias": 10, "presencas": 7, "justificadas": 2, "nao_justificadas": 1, "outros_eventos": 1}]


def test_visao_da_pagina(doc):
    v = plenario.visao(doc, slugs={"PL 1/2023": "pl-1-2023"})
    assert v["total_texto"] == 1 and v["total_ajuste"] == 1 and v["total_procedimento"] == 1
    assert v["todos"]["sim"] == 2 and v["todos"]["nao"] == 1
    assert v["sem_registro"] == 1
    assert v["contra_texto"] == 1 and v["difere_texto"] == 1 and v["com_orientacao"] == 1
    assert v["votos"][1]["slug"] == "pl-1-2023"
    assert v["temas"][0]["tema"] == "Educação"
    assert v["presenca"]["total"]["presencas"] == 7


@pytest.mark.parametrize("voto, sim, nao, esperado", [
    ("Sim", 10, 20, True), ("Não", 10, 20, False), ("Sim", 20, 10, False), ("Não", 20, 10, True),
    ("Sim", 10, 10, False), ("Obstrução", 10, 20, False),
])
def test_lado_menos_votado(voto, sim, nao, esperado):
    assert plenario.lado_menos_votado({"voto": voto, "sim": sim, "nao": nao}) is esperado


@pytest.mark.parametrize("voto, orientacao, esperado", [
    ("Sim", "Não", True), ("Sim", "Sim", False), ("Sim", "Liberado", False), ("Sim", None, False), ("Obstrução", "Sim", False),
])
def test_difere_da_orientacao(voto, orientacao, esperado):
    assert plenario.difere_da_orientacao({"voto": voto, "orientacao": orientacao}) is esperado

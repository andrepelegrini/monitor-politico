from monitor_politico import historico


class ArquivosFalsos:
    def __init__(self, tabelas):
        self.tabelas = tabelas

    def linhas(self, tipo, ano):
        return iter(self.tabelas.get((tipo, ano), []))


def votacao(id_, descricao, sim="0", nao="0", outros="0", aprovacao="1", orgao="PLEN", data="2024-05-10"):
    return {"id": id_, "siglaOrgao": orgao, "data": data, "dataHoraRegistro": data + "T18:00:00", "descricao": descricao,
            "aprovacao": aprovacao, "votosSim": sim, "votosNao": nao, "votosOutros": outros}


def ligacao(id_votacao, sigla, numero, ano, id_prop):
    return {"idVotacao": id_votacao, "proposicao_siglaTipo": sigla, "proposicao_numero": numero, "proposicao_ano": ano, "proposicao_id": id_prop}


def test_votacoes_da_camara_guarda_placar_e_marca_o_texto_principal():
    arquivos = ArquivosFalsos({
        ("votacoes", 2024): [
            votacao("1-1", "Aprovado o Requerimento de urgência."),
            votacao("1-2", "Aprovado o Projeto de Lei nº 10, de 2024.", sim="300", nao="100", outros="2"),
            votacao("2-1", "Aprovado o Requerimento.", orgao="CCJC"),
            votacao("3-1", "Aprovado o Requerimento de urgência."),
            votacao("4-1", "Aprovado o Projeto de Decreto Legislativo nº 5, de 2024."),
        ],
        ("votacoesProposicoes", 2024): [
            ligacao("1-1", "PL", "10", "2024", "100"), ligacao("1-2", "PL", "10", "2024", "100"),
            ligacao("2-1", "PL", "11", "2024", "101"), ligacao("3-1", "PL", "12", "2024", "102"),
            ligacao("4-1", "PDL", "5", "2024", "103"), ligacao("1-2", "REQ", "1", "2024", "999"),
        ],
    })
    dados = historico.votacoes_da_camara(arquivos, [2024])
    assert set(dados) == {"PL 10/2024", "PL 12/2024", "PDL 5/2024"}  # comissão e REQ ficam de fora
    assert dados["PL 10/2024"]["texto"] and not dados["PL 12/2024"]["texto"]  # só urgência não conta
    principal = next(v for v in dados["PL 10/2024"]["votacoes"] if v["id"] == "1-2")
    assert principal["nominal"] and principal["placar"]["sim"] == 300 and principal["placar"]["outros"] == [["Outros registros", 2]]
    assert principal["votos"] == [] and principal["resultado"] == "aprovada"
    simbolica = dados["PDL 5/2024"]["votacoes"][0]
    assert not simbolica["nominal"] and simbolica["placar"] is None


def test_votacoes_do_senado_so_placar_e_tipos_do_historico():
    def bruta(ident, descricao, codigo):
        return {"dataSessao": "2025-03-01", "identificacao": ident, "descricaoVotacao": descricao, "codigoSessaoVotacao": codigo,
                "resultadoVotacao": "A", "votacaoSecreta": "N",
                "votos": [{"codigoParlamentar": 1, "nomeParlamentar": "A", "siglaPartidoParlamentar": "X", "siglaUFParlamentar": "SP", "siglaVotoParlamentar": "Sim"}]}
    dados = historico.votacoes_do_senado([
        bruta("PEC 45/2019", "Votação nominal da Proposta de Emenda à Constituição nº 45, em primeiro turno.", 1),
        bruta("PL 2/2025 (Complementar)", "Votação nominal do Projeto de Lei Complementar nº 2.", 2),
        bruta("MSF 10/2025", "Votação nominal da Mensagem nº 10.", 3),
    ])
    assert set(dados) == {"PEC 45/2019", "PL 2/2025"}
    v = dados["PEC 45/2019"]["votacoes"][0]
    assert v["placar"]["sim"] == 1 and v["votos"] == [] and dados["PEC 45/2019"]["texto"]

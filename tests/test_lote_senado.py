from monitor_politico import lote_senado as ls, pacote


def _voto(id_, sigla, partido="PT"):
    return {"codigoParlamentar": id_, "siglaVotoParlamentar": sigla, "siglaPartidoParlamentar": partido}


def _votacao(votos, secreta="N", data="2024-05-10", descricao="Votação nominal do Projeto de Lei", codigo=1):
    return {
        "dataSessao": data + "T10:00:00", "votacaoSecreta": secreta, "votos": votos, "descricaoVotacao": descricao, "ementa": "Altera a lei.",
        "codigoSessaoVotacao": codigo, "idProcesso": 9, "codigoMateria": 77, "identificacao": "PL 12/2024",
    }


def test_participacao_conta_secreta_e_separa_afastamentos():
    votacoes = [
        _votacao([_voto(1, "Votou"), _voto(2, "NCom")], secreta="S"),
        _votacao([_voto(1, "Sim"), _voto(2, "LS")]),
        _votacao([_voto(1, "P-NRV"), _voto(2, "Presidente (art. 51 RISF)")]),
        _votacao([_voto(1, "NA"), _voto(2, "AP")]),
        _votacao([_voto(1, "Sim")], data="2022-01-01"),
    ]
    resultado = ls.participacao_nas_votacoes(votacoes, [1, 2], "2023-02-01")
    assert resultado[1]["por_ano"] == [{"ano": 2024, "votacoes": 3, "votou": 2, "presente_sem_voto": 1, "afastamento": 0, "nao_compareceu": 0}]
    assert resultado[2]["por_ano"] == [{"ano": 2024, "votacoes": 4, "votou": 1, "presente_sem_voto": 0, "afastamento": 2, "nao_compareceu": 1}]


def test_voto_secreto_nao_entra_na_lista_e_placar_exclui_a_pessoa():
    votacoes = [
        _votacao([_voto(1, "Votou"), _voto(2, "Votou")], secreta="S", codigo=1),
        _votacao([_voto(1, "Sim"), _voto(2, "Sim"), _voto(3, "Não")], codigo=2),
    ]
    resultado = ls.votos_em_aberto(votacoes, [1], "2023-02-01", lambda _: ["Saúde"])[1]
    assert resultado["votacoes_nominais"] == 1
    assert resultado["votos_registrados"] == 1
    voto = resultado["votos"][0]
    assert (voto["voto"], voto["sim"], voto["nao"], voto["orientacao"]) == ("Sim", 1, 1, None)
    assert voto["sigla"] == "PL 12/2024" and voto["temas"] == ["Saúde"] and voto["url"].endswith("/77")
    assert "codigoParlamentar" not in voto


def test_ler_norma_e_grupo():
    norma = ls.ler_norma("Lei nº 15.364 de 26/03/2026", "TRANSFORMADA EM NORMA JURÍDICA COM VETO PARCIAL")
    assert norma == {"nome": "Lei nº 15.364", "data": "2026-03-26", "veto_parcial": True}
    assert ls.ler_norma(None, "") is None
    assert ls.grupo_da_situacao_senado("TRANSFORMADA EM NORMA JURÍDICA", None) == "norma"
    assert ls.grupo_da_situacao_senado("REMETIDA À CÂMARA DOS DEPUTADOS", None) == "senado"
    assert ls.grupo_da_situacao_senado("RETIRADA PELO AUTOR", None) == "encerrada"
    assert ls.grupo_da_situacao_senado("TRAMITAÇÃO ENCERRADA", None) == "encerrada"
    assert ls.grupo_da_situacao_senado("AGUARDANDO DESIGNAÇÃO DO RELATOR", None) == "tramitacao"
    assert ls.grupo_da_situacao_senado("", None) == "sem_situacao"


def test_primeira_assinatura_compara_com_o_primeiro_nome_da_autoria():
    autoria = "Senadora Beltrana Lima (PT/RJ), Senador Fulano Silva (PL/SP)"
    assert ls.primeira_assinatura(autoria, "Beltrana Lima")
    assert not ls.primeira_assinatura(autoria, "Fulano Silva")


def test_propostas_ignora_outros_tipos_e_marca_norma_sem_numero():
    processos = [
        {"id": 1, "identificacao": "PL 1/2024", "autoria": "Senador Fulano Silva (PL/SP)", "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA", "dataSituacaoAtual": "2025-03-01", "dataApresentacao": "2024-01-01", "ementa": "A", "codigoMateria": 5},
        {"id": 2, "identificacao": "REQ 3/2024", "autoria": "Senador Fulano Silva (PL/SP)", "situacaoAtual": "", "dataApresentacao": "2024-01-01", "ementa": "B"},
    ]
    lista = ls.propostas_do_senador(processos, "Fulano Silva", lambda _: [])
    assert [p["sigla"] for p in lista] == ["PL 1/2024"]
    assert lista[0]["participacao"] == "primeira" and lista[0]["grupo"] == "norma"
    assert lista[0]["norma"]["data"] == "2025-03-01"


def test_relatorias_em_andamento_e_tipos_comparaveis():
    relatorias = [
        {"idProcesso": 1, "identificacaoProcesso": "PL 1/2024", "dataDesignacao": "2024-01-01"},
        {"idProcesso": 2, "identificacaoProcesso": "PEC 2/2024", "dataDesignacao": "2024-01-01", "dataDestituicao": "2024-06-01"},
        {"idProcesso": 3, "identificacaoProcesso": "PL 3/2019", "dataDesignacao": "2019-01-01"},
        {"idProcesso": 4, "identificacaoProcesso": "REQ 4/2024", "dataDesignacao": "2024-01-01"},
    ]
    assert ls.relatorias_no_mandato(relatorias, "2023-02-01") == {"total": 2, "em_andamento": 2}


def test_cota_nao_guarda_cpf_nem_detalhamento():
    linhas = {2024: [
        {"SENADOR": "FULANO SILVA", "MES": "3", "TIPO_DESPESA": "Passagens aéreas", "FORNECEDOR": "Aérea SA", "CNPJ_CPF": "11.222.333/0001-81", "VALOR_REEMBOLSADO": "1.000,50", "DETALHAMENTO": "Trecho X"},
        {"SENADOR": "FULANO SILVA", "MES": "4", "TIPO_DESPESA": "Aluguel de imóveis", "FORNECEDOR": "Maria 123.456.789-09", "CNPJ_CPF": "123.456.789-09", "VALOR_REEMBOLSADO": "200,00", "DETALHAMENTO": "Sala"},
    ]}
    resultado = ls.cota_de_todos(linhas, {1: "Fulano Silva"}, "2023-02-01")[1]
    assert resultado["por_ano"][0]["total"] == 1200.5
    assert resultado["por_ano"][0]["percentual"] is None
    assert pacote.dados_pessoais_no_documento(resultado) == []
    texto = str(resultado)
    assert "123.456.789" not in texto and "Trecho X" not in texto and "Maria" not in texto


def test_situacao_sem_cpf_so_afirma_quando_as_buscas_concordam():
    senador = {"DS_CARGO": "SENADOR", "DS_SIT_TOT_TURNO": "ELEITO"}
    assert ls.situacao_do_senador(senador, "2027-01-31", False)["chave"] == "reeleicao"
    assert ls.situacao_do_senador({**senador, "DS_SIT_TOT_TURNO": "NÃO ELEITO"}, "2027-01-31", False)["chave"] == "nao_reeleito"
    assert ls.situacao_do_senador(None, "2031-01-31", False) == {"chave": "continua", "rotulo": "Mandato até 2031"}
    assert ls.situacao_do_senador(None, "2027-01-31", True) is None
    assert ls.situacao_do_senador(None, "2027-01-31", False)["chave"] == "sem_candidatura"


def test_candidatura_exige_nascimento_e_nome():
    linhas = [
        {"DT_NASCIMENTO": "01/02/1970", "NM_CANDIDATO": "OUTRA PESSOA", "NR_TURNO": "1"},
        {"DT_NASCIMENTO": "01/02/1970", "NM_CANDIDATO": "FULANO DE TAL SILVA", "NR_TURNO": "1"},
    ]
    assert ls.candidatura_por_nascimento(linhas, "Fulano Silva", "1970-02-01") is linhas[1]
    assert ls.candidatura_por_nascimento(linhas, "Fulano Silva", "1971-02-01") is None


def test_eleitos_que_chegam():
    base = {"DS_CARGO": "SENADOR", "DS_SIT_TOT_TURNO": "ELEITO", "SG_PARTIDO": "PT", "SG_UF": "SP"}
    candidaturas = [
        {**base, "SQ_CANDIDATO": "1", "NM_URNA_CANDIDATO": "ATUAL", "NM_CANDIDATO": "ATUAL SILVA"},
        {**base, "SQ_CANDIDATO": "2", "NM_URNA_CANDIDATO": "VOLTA", "NM_CANDIDATO": "VOLTA PEREIRA SOUZA"},
        {**base, "SQ_CANDIDATO": "3", "NM_URNA_CANDIDATO": "DEPUTADA", "NM_CANDIDATO": "DEPUTADA COSTA"},
        {**base, "SQ_CANDIDATO": "4", "NM_URNA_CANDIDATO": "NOVA", "NM_CANDIDATO": "NOVA LIMA"},
        {**base, "SQ_CANDIDATO": "5", "NM_URNA_CANDIDATO": "PERDEU", "NM_CANDIDATO": "PERDEU X", "DS_SIT_TOT_TURNO": "NÃO ELEITO"},
    ]
    eleitos = ls.eleitos_que_chegam(candidaturas, {"1": 10}, [{"nome_completo": "Volta Pereira Souza", "uf": "SP"}], [{"id": 99, "nome": "Deputada Costa", "uf": "SP"}])
    assert {e["sq"]: e["chave"] for e in eleitos} == {"2": "retorno", "3": "camara", "4": "primeiro"}
    assert next(e for e in eleitos if e["sq"] == "3")["id_deputado"] == 99


def test_ligar_nomes_nao_liga_quando_ha_ambiguidade():
    pessoas = {1: "Jorge Kajuru", 2: "Maria Souza", 3: "Maria Lima"}
    ligados = ls.ligar_nomes(pessoas, ["KAJURU", "MARIA", "MARIA SOUZA"])
    assert ligados == {"KAJURU": 1, "MARIA SOUZA": 2}


def test_privacidade_do_pacote_olha_a_pasta_do_senado(tmp_path):
    import json, pytest
    (tmp_path / "senado").mkdir()
    (tmp_path / "senado" / "1.json").write_text(json.dumps({"fornecedor": "Maria 123.456.789-09"}), encoding="utf-8")
    with pytest.raises(pacote.PacoteInvalido):
        pacote.verificar_privacidade(tmp_path)


def test_um_nome_em_comum_nao_basta_para_ligar_ao_tse():
    assert not ls.mesma_pessoa("Humberto Sérgio Costa Lima", "JOSE COSTA PEREIRA")
    assert ls.mesma_pessoa("Humberto Sérgio Costa Lima", "HUMBERTO SERGIO COSTA LIMA")
    assert ls.mesma_pessoa("Maria Souza Lima Reis", "ANA MARIA SOUZA LIMA")
    assert not ls.mesma_pessoa("Maria Souza", "JOANA SOUZA MARIA")


def test_mandatos_de_suplente_comecam_no_exercicio_e_sem_repeticao():
    base = {"NumeroLegislatura": "57", "DataInicio": "2023-02-01", "DataFim": "2027-01-31"}
    mandatos = [
        {"UfParlamentar": "MA", "PrimeiraLegislaturaDoMandato": base, "SegundaLegislaturaDoMandato": base},
        {"CodigoMandato": "1", "DescricaoParticipacao": "1º Suplente", "PrimeiraLegislaturaDoMandato": base,
         "SegundaLegislaturaDoMandato": {"NumeroLegislatura": "58", "DataInicio": "2027-02-01", "DataFim": "2031-01-31"},
         "Exercicios": {"Exercicio": [{"DataInicio": "2026-10-06"}, {"DataInicio": "2024-02-21", "DataFim": "2026-07-30"}]}},
        {"CodigoMandato": "2", "DescricaoParticipacao": "2º Suplente", "PrimeiraLegislaturaDoMandato": {"NumeroLegislatura": "55", "DataInicio": "2015-02-01", "DataFim": "2019-01-31"}},
    ]
    assert ls.mandatos_do_senador(mandatos) == [{"inicio": "2024-02-21", "rotulo": "2023–2031"}]


def test_fases_do_mesmo_projeto_contam_uma_vez():
    base = {"autoria": "Senador Fulano Silva (PL/SP)", "dataApresentacao": "2023-01-01", "ementa": "A", "codigoMateria": 5}
    processos = [
        {**base, "id": 1, "identificacao": "PEC 66/2023", "situacaoAtual": "TRAMITAÇÃO ENCERRADA", "dataSituacaoAtual": "2025-01-01"},
        {**base, "id": 2, "identificacao": "PEC 66/2023 (fase 2)", "situacaoAtual": "TRANSFORMADA EM NORMA JURÍDICA", "dataSituacaoAtual": "2025-09-09", "normaGerada": "Emenda Constitucional nº 136 de 09/09/2025"},
    ]
    lista = ls.propostas_do_senador(processos, "Fulano Silva", lambda _: [])
    assert len(lista) == 1
    assert lista[0]["sigla"] == "PEC 66/2023" and lista[0]["norma"]["nome"] == "Emenda Constitucional nº 136"

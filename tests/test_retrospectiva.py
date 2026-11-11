from monitor_politico import retrospectiva


def metricas(**por_id):
    return {"inicio": "2023-02-01", "por_deputado": {str(i): n for i, n in por_id.items()}}


def numeros(principal=0, votos=0, presencas=0, dias=400, relatorias=0):
    return {"principal": principal, "coautoria": 0, "votos": votos, "presencas": presencas, "dias": dias, "relatorias": relatorias}


def test_referencias_so_com_quem_exerceu_tres_quartos_do_periodo():
    m = metricas(**{"1": numeros(2, 900, 380), "2": numeros(0, 800, 360), "3": numeros(6, 1000, 390), "4": numeros(9, 50, 20, dias=40)})
    ref = retrospectiva.referencias(m, [1, 2, 3, 4])
    assert ref["total"] == 4 and len(ref["completos"]) == 3  # o 4 exerceu 40 de 400 dias
    assert ref["mediana_votos"] == 900 and ref["mediana_presenca"] == 95.0
    assert ref["sem_lei"] == 1


def perfil(casa=None):
    return {
        "casa": casa, "coleta_local": "2026-11-09", "legislatura_atual": {"inicio": "2023-02-01"},
        "plenario": {"votacoes_nominais": 1000, "texto": {"sim": 10, "nao": 2, "outros": 0}, "total_texto": 12, "contra_texto": 3, "difere_texto": 1, "com_orientacao": 8},
        "propostas": {"propostas": [
            {"data": "2024-01-01", "participacao": "primeira"}, {"data": "2025-01-01", "participacao": "coautoria"},
            {"data": "2022-01-01", "participacao": "primeira"}, {"data": "2024-05-01", "participacao": "apoio"},
        ], "normas": [
            {"sigla": "PL 1/2023", "participacao": "primeira", "ementa": "Cria um programa.", "norma": {"nome": "Lei 1/2024", "data": "2024-03-01"}},
            {"sigla": "PL 2/2019", "participacao": "primeira", "ementa": "Antiga.", "norma": {"nome": "Lei 2/2020", "data": "2020-03-01"}},
            {"sigla": "PL 3/2023", "participacao": "coautoria", "ementa": "Em coautoria.", "norma": {"nome": "Lei 3/2025", "data": "2025-03-01"}},
        ], "temas": []},
        "dinheiro": {"cota": {"total": 100.0, "por_ano": [{"ano": 2023, "percentual": 90.0}, {"ano": 2026, "percentual": 50.0}]},
                     "emendas": {"pago_total": 10.0, "funcoes": [{"nome": "Saúde", "valor": 7.0}]}},
    }


def test_visao_conta_so_a_legislatura_e_compara_quem_exerceu_o_periodo():
    m = metricas(**{"1": numeros(1, 900, 380), "2": numeros(3, 800, 360, relatorias=40), "3": numeros(0, 950, 390, relatorias=5)})
    ref = retrospectiva.referencias(m, [1, 2, 3])
    from monitor_politico import metricas as modulo_metricas
    v = retrospectiva.visao(perfil(), modulo_metricas.do_deputado(m, 1), ref)
    assert v["completo"] and v["leis_mais"] == 1 and v["relatorias_mais"] == 2
    assert (v["propostas_principal"], v["propostas_coautoria"]) == (1, 1)  # sem 2022 e sem apoio
    assert [l["sigla"] for l in v["leis"]] == ["PL 1/2023"]
    assert v["cota_percentuais"] == [90.0]  # 2026 ainda não terminou
    assert [c["valor"] for c in v["cartao"]] == ["1", "95,0%", "900", "2"]
    assert "mediana 900" in v["cartao"][2]["detalhe"]


def test_quem_assumiu_depois_fica_sem_as_contagens_de_comparacao():
    m = metricas(**{"1": numeros(1, 900, 380), "2": numeros(3, 800, 360), "9": numeros(0, 40, 18, dias=20)})
    ref = retrospectiva.referencias(m, [1, 2, 9])
    from monitor_politico import metricas as modulo_metricas
    v = retrospectiva.visao(perfil(), modulo_metricas.do_deputado(m, 9), ref)
    assert not v["completo"] and v["leis_mais"] is None and v["relatorias_mais"] is None
    assert "mediana" not in v["cartao"][2]["detalhe"]

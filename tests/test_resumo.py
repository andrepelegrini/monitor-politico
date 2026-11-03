from monitor_politico import resumo
from monitor_politico.models import Deputado, Gabinete, Senador

GAB = Gabinete(None, None, None, None, None)


def dep(id_, partido, uf, condicao="Titular"):
    return Deputado(id_, f"D{id_}", partido, uf, None, "Exercício", condicao, GAB, "", "")


def sen(id_, partido, bloco, fim, condicao="Titular"):
    return Senador(id_, f"S{id_}", partido, "SP", None, condicao, bloco, fim, None, (), "", "")


def test_pct_no_formato_brasileiro():
    assert resumo.pct(15, 81) == "18,5%"
    assert resumo.pct(0, 0) == "0%"


def test_por_partido_ordena_por_tamanho_e_nome():
    linhas = resumo.por_partido([dep(1, "PT", "SP"), dep(2, "PL", "SP"), dep(3, "PL", "RJ"), dep(4, "MDB", "RJ")])
    assert [(l["sigla"], l["n"], l["pct"], l["largura"]) for l in linhas] == [
        ("PL", 2, "50,0%", "100.0%"), ("MDB", 1, "25,0%", "50.0%"), ("PT", 1, "25,0%", "50.0%"),
    ]


def test_bancadas_por_uf_mostram_empate():
    bancadas = resumo.bancadas_por_uf([dep(1, "PT", "AP"), dep(2, "PDT", "AP"), dep(3, "PL", "SP"), dep(4, "PL", "SP"), dep(5, "PT", "SP")])
    assert bancadas == [
        {"uf": "SP", "n": 3, "maior": "PL 2", "empate": False},
        {"uf": "AP", "n": 2, "maior": "PDT, PT · 1 cada", "empate": True},
    ]


def test_blocos_e_mandatos_do_senado():
    senadores = [
        sen(1, "PSD", "Bloco Parlamentar da Resistência Democrática", "2027-01-31"),
        sen(2, "PSB", "Bloco Parlamentar da Resistência Democrática", "2031-01-31"),
        sen(3, "S/Partido", None, "2027-01-31", condicao="1º Suplente"),
    ]
    blocos = resumo.blocos(senadores)
    assert [(b["nome"], b["n"], b["partidos"]) for b in blocos] == [
        ("Resistência Democrática", 2, "PSB 1 · PSD 1"), ("Sem bloco", 1, "S/Partido 1"),
    ]
    assert [(m["fim"], m["n"]) for m in resumo.mandatos(senadores)] == [("31/01/2027", 2), ("31/01/2031", 1)]
    pagina = resumo.do_senado(senadores, {})
    assert pagina["suplentes"] == 1
    assert pagina["sexo"] is None  # sem contagem, o bloco some
    assert [c["rotulo"] for c in pagina["cartoes"]] == ["senadores", "partidos", "suplentes em exercício"]


def test_resumo_da_camara_marca_lideres_com_perfil():
    deputados = [dep(1, "PL", "SP"), dep(2, "PT", "RJ", condicao="Efetivado"), dep(3, "PT", "RJ", condicao="Suplente")]
    dados = {
        "sexo": {"mulheres": 1, "homens": 2, "mulheres_por_partido": {"PT": 1}},
        "lideres": [{"cargo": "Presidente", "id": 1, "nome": "D1", "partido": "PL", "uf": "SP"},
                    {"cargo": "Líder do Governo", "id": 99, "nome": "Fora", "partido": "PT", "uf": "RJ"}],
    }
    pagina = resumo.da_camara(deputados, dados)
    assert [l["tem_perfil"] for l in pagina["lideres"]] == [True, False]
    assert (pagina["titulares"], pagina["efetivados"], pagina["suplentes"]) == (1, 1, 1)
    assert pagina["sexo"]["pct_mulheres"] == "33,3%"
    assert pagina["cartoes"][2] == {"valor": "33,3%", "rotulo": "são mulheres", "detalhe": "1 deputada"}

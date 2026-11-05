import json

import pytest

from monitor_politico import dinheiro
from monitor_politico.plenario import RelatorioInvalido

ID = 204534


def linha_cota(valor, legislatura="57", ide=ID, categoria="TELEFONIA", fornecedor="ACME LTDA", doc="11222333000144", mes="3", url="https://www.camara.leg.br/doc.pdf"):
    return {
        "ideCadastro": str(ide), "codLegislatura": legislatura, "vlrLiquido": valor, "txtDescricao": categoria, "txtFornecedor": fornecedor,
        "txtCNPJCPF": doc, "numAno": "2023", "numMes": mes, "urlDocumento": url, "cpf": "11122233344", "txtPassageiro": "FULANA DE TAL", "txtTrecho": "BSB/CGH",
    }


def linha_emenda(ano="2023", autor="TABATA AMARAL", pago="10,00", restos="5,00", localidade="MÚLTIPLO", uf="SÃO PAULO", funcao="Saúde"):
    return {
        "Ano da Emenda": ano, "Nome do Autor da Emenda": autor, "Valor Empenhado": "100,00", "Valor Liquidado": "20,00", "Valor Pago": pago,
        "Valor Restos A Pagar Pagos": restos, "Nome Função": funcao, "Tipo de Emenda": "Emenda Individual - Transferências Especiais",
        "Localidade de aplicação do recurso": localidade, "UF": uf,
    }


def favorecido(codigo="1", nome="FUNDO MUNICIPAL", valor="1.000,50", tipo="Pessoa Jurídica", autor="TABATA AMARAL", emenda="202341320001"):
    return {
        "Nome do Autor da Emenda": autor, "Código da Emenda": emenda, "Tipo Favorecido": tipo, "Código do Favorecido": codigo, "Favorecido": nome,
        "Município Favorecido": "CAJAMAR", "UF Favorecido": "SP", "Valor Recebido": valor,
    }


class FonteFalsa:
    def cota(self, ano):
        if ano != 2023:
            return []
        return [
            linha_cota("100.50"),
            linha_cota("-20.25", categoria="PASSAGEM AÉREA - SIGEPA", url=""),
            linha_cota("50.00", categoria="PASSAGEM AÉREA - RPA", fornecedor="CIA AEREA", doc="99888777000166"),
            linha_cota("70.00", fornecedor="FULANO PESSOA FISICA", doc="123.456.789-00"),
            linha_cota("999.00", legislatura="56", mes="1"),  # mandato anterior
            linha_cota("999.00", ide=1),  # outro parlamentar
        ]

    def cota_oficial(self, _id, ano):
        return {"total": 250.25, "percentual": 99.5, "nao_utilizado": 3.0} if ano == 2023 else {"total": 0.0, "percentual": 0.0, "nao_utilizado": 0.0}

    def emendas(self):
        return [linha_emenda(), linha_emenda(localidade="Nacional", funcao="Educação", pago="1,00", restos="0,00"), linha_emenda(ano="2022"), linha_emenda(autor="OUTRA PESSOA")]

    def favorecidos(self):
        return [
            favorecido(), favorecido(valor="499,50"), favorecido(codigo="2", nome="MARIA DA SILVA", valor="50,00", tipo="Pessoa Fisica"),
            favorecido(codigo="3", emenda="202241320001"), favorecido(codigo="4", autor="OUTRA PESSOA"),
        ]

    def data_das_emendas(self):
        return "2026-10-29"


@pytest.fixture
def doc():
    return dinheiro.coletar(FonteFalsa(), ID, "Tabata Amaral", 57, 2023, 2024)


PAGINA = """<div>Gastos e recursos 2023</div><script>var x = 1;</script><h4>Cota parlamentar</h4> <span>?</span>
<table><tr><th>Percentual gasto</th></tr><tr><td>Cota Partamentar</td><td>Total (R$)</td><td>Percentual Gasto</td></tr>
<tr><td>480.571,79</td><td>99.34%</td></tr><tr><td>Não utilizado</td><td>3.214,83</td></tr></table>"""


def test_le_quadro_oficial_da_cota():
    assert dinheiro.ler_cota_da_pagina(PAGINA) == {"total": 480571.79, "percentual": 99.34, "nao_utilizado": 3214.83}


def test_pagina_sem_quadro_interrompe_a_coleta():
    with pytest.raises(RelatorioInvalido):
        dinheiro.ler_cota_da_pagina("<p>outra página</p>")


def test_cota_so_do_parlamentar_e_da_legislatura(doc):
    cota = doc["cota"]
    assert cota["por_ano"][0]["detalhado"] == 200.25
    assert dict(map(tuple, cota["categorias"])) == {"Telefonia": 170.5, "Passagens aéreas": 29.75}
    assert len(cota["comprovantes"]) == 4


def test_pessoa_fisica_nao_aparece_pelo_nome(doc):
    texto = json.dumps(doc, ensure_ascii=False)
    for proibido in ("FULANO PESSOA FISICA", "123.456.789-00", "MARIA DA SILVA", "11122233344", "FULANA DE TAL", "BSB/CGH"):
        assert proibido not in texto
    assert dinheiro.PESSOA_FISICA in texto
    assert {f[0] for f in doc["cota"]["fornecedores"]} == {"ACME LTDA", "CIA AEREA"}


def test_fornecedor_com_dois_cnpjs_soma_pelo_nome():
    class Fonte(FonteFalsa):
        def cota(self, ano):
            return [linha_cota("10.00", fornecedor="Empresa Individual", doc="11222333000144"), linha_cota("5.00", fornecedor="EMPRESA INDIVIDUAL", doc="99888777000166")]
    cota = dinheiro.cota_do_mandato(Fonte(), ID, 57, [2023])
    assert [valor for _, valor in cota["fornecedores"]] == [15.0]
    assert cota["total_fornecedores"] == 1


def test_comprovante_sem_arquivo_e_ordem_por_valor(doc):
    comprovantes = doc["cota"]["comprovantes"]
    assert [c["valor"] for c in comprovantes] == [100.5, 70.0, 50.0, -20.25]
    assert comprovantes[-1]["url"] is None
    assert comprovantes[0]["mes"] == "2023-03"


def test_emendas_filtram_autor_e_ano(doc):
    e = doc["emendas"]
    assert e["por_ano"] == [{"ano": 2023, "empenhado": 200.0, "liquidado": 40.0, "pago": 11.0, "restos_pagos": 5.0}]
    assert dict(map(tuple, e["funcoes"])) == {"Saúde": 15.0, "Educação": 1.0}
    assert dict(map(tuple, e["destinos"])) == {"Vários municípios (São Paulo)": 15.0, "Nacional": 1.0}
    assert dict(map(tuple, e["tipos"])) == {"Transferências Especiais": 16.0}
    assert e["arquivo_em"] == "2026-10-29"


def test_favorecidos_somam_por_codigo_e_escondem_pessoa_fisica(doc):
    e = doc["emendas"]
    assert e["favorecidos"][0] == {"nome": "FUNDO MUNICIPAL", "municipio": "CAJAMAR", "uf": "SP", "valor": 1500.0}
    assert e["favorecidos"][1] == {"nome": dinheiro.PESSOA_FISICA, "municipio": "", "uf": "", "valor": 50.0}
    assert e["total_favorecidos"] == 2
    assert e["total_recebido"] == 1550.0


@pytest.mark.parametrize("localidade, uf, esperado", [
    ("Nacional", "Sem informação", "Nacional"),
    ("SÃO PAULO (UF)", "SÃO PAULO", "São Paulo, sem município indicado"),
    ("MÚLTIPLO", "RIO GRANDE DO SUL", "Vários municípios (Rio Grande do Sul)"),
    ("MÚLTIPLO", "Múltiplo", "Vários estados"),
    ("SÃO VICENTE - SP", "SÃO PAULO", "São Vicente-SP"),
])
def test_destino_da_emenda(localidade, uf, esperado):
    assert dinheiro._destino({"Localidade de aplicação do recurso": localidade, "UF": uf}) == esperado


def test_funcao_multipla_tem_nome_legivel():
    doc = dinheiro.emendas_do_mandato([linha_emenda(funcao="Múltiplo")], [], "Tabata Amaral", 2023)
    assert doc["funcoes"][0][0] == "Várias áreas"


def test_nome_do_autor_ignora_acentos_e_caixa():
    assert dinheiro.nome_de_autor("Tábata Amaral ") == dinheiro.nome_de_autor("TABATA AMARAL")


def test_visao_mostra_total_oficial_e_o_que_nao_tem_detalhe(doc):
    v = dinheiro.visao(doc)
    assert v["cota"]["total"] == 250.25
    assert v["cota"]["detalhado"] == 200.25
    assert v["cota"]["sem_detalhe"] == 50.0
    assert {"nome": "Sem detalhamento nos arquivos abertos", "valor": 50.0, "largura": 29.3} in v["cota"]["categorias"]
    assert v["emendas"]["pago_total"] == 16.0
    assert v["emendas"]["ano_inicial"] == 2023


def test_centavos_de_arredondamento_nao_viram_valor_sem_detalhe():
    doc = {
        "cota": {"por_ano": [{"ano": 2024, "total": 518725.20, "percentual": 98.55, "nao_utilizado": 1.0, "detalhado": 518725.23}], "categorias": [], "fornecedores": [], "total_fornecedores": 0, "comprovantes": []},
        "emendas": {"por_ano": [], "funcoes": [], "tipos": [], "destinos": [], "favorecidos": [], "total_favorecidos": 0, "total_recebido": 0, "arquivo_em": "2026-10-29"},
    }
    assert dinheiro.visao(doc)["cota"]["sem_detalhe"] == 0

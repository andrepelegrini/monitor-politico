import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from conftest import cliente_falso, congresso_falso
from monitor_politico import perfis, plenario
from monitor_politico.build import construir
from monitor_politico.camara import coletar as coletar_camara
from monitor_politico.congresso import coletar as coletar_congresso
from monitor_politico.senado import coletar as coletar_senado

CPF = "11122233344"
HOJE = date(2026, 11, 4)


def candidato(ano_sq, cpf=CPF, cargo="DEPUTADO FEDERAL", partido="PSB", situacao="ELEITO POR QP"):
    return {
        "NR_CPF_CANDIDATO": cpf, "DS_CARGO": cargo, "SQ_CANDIDATO": ano_sq, "SG_PARTIDO": partido, "SG_UF": "SP",
        "DS_SIT_TOT_TURNO": situacao, "DT_NASCIMENTO": "01/01/1990", "DS_EMAIL": "pessoa@exemplo.org", "DS_COR_RACA": "X",
    }


class FonteFalsa:
    """Duas eleições: bens sobem de R$ 100 para R$ 150, e a pessoa foi eleita na última."""

    def candidatos(self, ano):
        return [candidato("outro", cpf="99999999999"), candidato(f"sq{ano}", cargo="SENADOR"), candidato(f"sq{ano}")] if ano != 2018 else [candidato("outro", cpf="99999999999")]

    def bens(self, ano):
        valor = {2022: "100,00", 2026: "100,50"}[ano]
        return [
            {"SQ_CANDIDATO": f"sq{ano}", "DS_TIPO_BEM_CANDIDATO": "Apartamento", "VR_BEM_CANDIDATO": valor, "DS_BEM_CANDIDATO": "Rua Secreta, 10"},
            {"SQ_CANDIDATO": f"sq{ano}", "DS_TIPO_BEM_CANDIDATO": "Poupança", "VR_BEM_CANDIDATO": "49,50" if ano == 2026 else "0,00", "DS_BEM_CANDIDATO": "Conta 123"},
            {"SQ_CANDIDATO": "outro", "DS_TIPO_BEM_CANDIDATO": "Apartamento", "VR_BEM_CANDIDATO": "9000,00", "DS_BEM_CANDIDATO": "x"},
        ]

    def votacao(self, ano, uf):
        return [
            {"SQ_CANDIDATO": f"sq{ano}", "NM_MUNICIPIO": "SÃO PAULO", "QT_VOTOS_NOMINAIS_VALIDOS": "70"},
            {"SQ_CANDIDATO": f"sq{ano}", "NM_MUNICIPIO": "SÃO PAULO", "QT_VOTOS_NOMINAIS_VALIDOS": "10"},
            {"SQ_CANDIDATO": f"sq{ano}", "NM_MUNICIPIO": "CAMPINAS", "QT_VOTOS_NOMINAIS_VALIDOS": "20"},
            {"SQ_CANDIDATO": "outro", "NM_MUNICIPIO": "OSASCO", "QT_VOTOS_NOMINAIS_VALIDOS": "500"},
        ]


HISTORICO = [
    {"dataHora": "2023-02-01T00:00", "idLegislatura": 58, "siglaPartido": "PSB", "siglaUf": "SP", "descricaoStatus": "Nome no início da legislatura / Partido no início da legislatura"},
    {"dataHora": "2023-02-01T12:05", "idLegislatura": 57, "siglaPartido": "PSB", "siglaUf": "SP", "descricaoStatus": "Entrada - Posse de Eleito Titular - Posse na Sessão Preparatória"},
    {"dataHora": "2019-02-01T11:45", "idLegislatura": 56, "siglaPartido": "PDT", "siglaUf": "SP", "descricaoStatus": "Entrada - Posse de Eleito Titular - Posse na Sessão Preparatória"},
    {"dataHora": "2021-09-28T19:32", "idLegislatura": 56, "siglaPartido": "PSB", "siglaUf": "SP", "descricaoStatus": "Alteração de partido"},
    {"dataHora": "2023-01-31T23:59", "idLegislatura": 56, "siglaPartido": "PSB", "siglaUf": "SP", "descricaoStatus": "Saída - Afastamento definitivo - Término da Legislatura"},
]
ORGAOS = [
    {"siglaOrgao": "CE", "nomeOrgao": "Comissão de Educação", "nomePublicacao": "Comissão de Educação", "titulo": "Titular", "dataFim": None},
    {"siglaOrgao": "CCJC", "nomeOrgao": "Comissão de Constituição", "nomePublicacao": None, "titulo": "Suplente", "dataFim": "2027-01-31T23:59"},
    {"siglaOrgao": "ANT", "nomeOrgao": "Comissão Antiga", "nomePublicacao": "Comissão Antiga", "titulo": "Titular", "dataFim": "2024-01-31T23:59"},
    {"siglaOrgao": "SEM", "nomeOrgao": "SECRETARIA DA MULHER", "nomePublicacao": "SECRETARIA DA MULHER", "titulo": "Presidente", "dataFim": None},
]


PLENARIO = {
    "votos": {
        "inicio": "2023-02-01", "votacoes_nominais": 3, "votos_registrados": 2, "procedimento": {"Sim": 1},
        "votos": [{
            "id": "10-1", "data": "2023-03-01", "voto": "Não", "classe": "texto", "proposicao_id": "10", "sigla": "PEC 18/2025",
            "ementa": "Ementa oficial " + "x" * 300, "descricao": "Aprovado o Projeto.", "sim": 30, "nao": 10, "outros": 1,
            "partido": "PSB", "orientacao": "Sim", "temas": ["Educação"],
        }],
    },
    "presenca": {"por_ano": [{"ano": 2023, "dias": 115, "presencas": 103, "justificadas": 10, "nao_justificadas": 2, "outros_eventos": 149}]},
}


def responder(request: httpx.Request) -> httpx.Response:
    caminho = request.url.path.removeprefix("/api/v2")
    if caminho.endswith("/historico"):
        return httpx.Response(200, json={"dados": HISTORICO})
    if caminho.endswith("/orgaos"):
        return httpx.Response(200, json={"dados": ORGAOS, "links": []})
    if caminho == "/legislaturas/57":
        return httpx.Response(200, json={"dados": [{"id": 57, "dataInicio": "2023-02-01", "dataFim": "2027-01-31"}]})
    return httpx.Response(200, json={"dados": {"id": 204534, "cpf": CPF, "dataNascimento": "1990-01-01", "redeSocial": ["x"]}})


@pytest.fixture
def doc():
    return perfis.coletar_perfil(204534, cliente_falso(responder), FonteFalsa(), hoje=HOJE)


def test_candidatura_exige_cpf_e_cargo():
    linhas = [candidato("a", cpf="1"), candidato("b", cargo="SENADOR"), candidato("c")]
    assert perfis.candidatura(linhas, CPF)["sq"] == "c"
    assert perfis.candidatura(linhas[:2], CPF) is None


def test_coleta_soma_so_a_pessoa_e_ignora_eleicao_sem_candidatura(doc):
    assert [e["ano"] for e in doc["eleicoes"]] == [2022, 2026]
    recente = doc["eleicoes"][1]
    assert recente["votos"] == 100
    assert recente["total_municipios"] == 2
    assert recente["municipios"][0] == ["SÃO PAULO", 80]
    assert recente["bens"]["total"] == 150.0
    assert doc["legislatura_atual"] == {"id": 57, "inicio": "2023-02-01", "fim": "2027-01-31"}


def test_json_nao_guarda_dados_pessoais(doc):
    texto = json.dumps(doc, ensure_ascii=False)
    for proibido in (CPF, "Rua Secreta", "Conta 123", "1990", "pessoa@exemplo.org", "redeSocial"):
        assert proibido not in texto


def test_trajetoria_mantem_posses_e_troca_de_partido():
    eventos = perfis.trajetoria(HISTORICO)
    assert [(e["data"], e["tipo"]) for e in eventos] == [("2019-02-01", "posse"), ("2021-09-28", "partido"), ("2023-02-01", "posse")]
    assert eventos[1]["partido_anterior"] == "PDT"


def test_comissoes_atuais_sem_as_encerradas():
    atuais = perfis.comissoes_atuais(ORGAOS, HOJE)
    assert [c["sigla"] for c in atuais] == ["SEM", "CE", "CCJC"]
    assert atuais[0]["nome"] == "Secretaria da Mulher"


def test_variacao_de_bens_com_e_sem_base():
    def eleicao(ano, total):
        return {"ano": ano, "bens": {"total": total, "categorias": [["Apartamento", total]]}}
    assert perfis.variacoes_de_bens([eleicao(2022, 556700.29), eleicao(2026, 674534.74)]) == [
        {"de": 2022, "para": 2026, "diferenca": 117834.45, "percentual": 21.2}
    ]
    assert perfis.variacoes_de_bens([eleicao(2022, 0), eleicao(2026, 10)])[0]["percentual"] is None
    # Eleição sem bens declarados não vira queda de 100%.
    sem_bens = {"ano": 2026, "bens": {"total": 0, "categorias": []}}
    assert perfis.variacoes_de_bens([eleicao(2022, 10), sem_bens]) == []


def test_novo_mandato_so_antes_da_posse_e_com_vitoria(doc):
    assert perfis.proximo_mandato(doc, HOJE)["inicio"] == "2027-02-01"
    assert perfis.proximo_mandato(doc, date(2027, 2, 1)) is None
    derrota = {**doc, "eleicoes": [{**e, "situacao": "SUPLENTE"} for e in doc["eleicoes"]]}
    assert perfis.proximo_mandato(derrota, HOJE) is None


def test_formatos_brasileiros():
    assert perfis.numero(476383) == "476.383"
    assert perfis.moeda(674534.74) == "R$ 674.534,74"
    assert perfis.percentual(21.2) == "+21,2%"
    assert perfis.percentual(-3.5) == "−3,5%"
    assert perfis.nome_proprio("SÃO JOSÉ DOS CAMPOS") == "São José dos Campos"


def test_data_da_coleta_no_horario_de_brasilia(doc):
    assert perfis.visao({**doc, "coletado_em": "2026-11-05T02:23:00+00:00"})["coleta_local"] == "2026-11-04"


def test_ler_perfis_sem_pasta(tmp_path):
    assert perfis.ler_perfis(tmp_path / "nao-existe") == {}


def test_mandato_pela_legislatura_e_nao_pelo_ano_da_posse():
    doc = {"trajetoria": [
        {"tipo": "posse", "data": "2019-02-01", "legislatura": 56},
        {"tipo": "posse", "data": "2024-05-10", "legislatura": 57},  # suplente assumindo no meio
        {"tipo": "posse", "data": "2025-03-01", "legislatura": 57},  # e voltando a assumir
    ]}
    assert perfis.mandatos_da_trajetoria(doc) == [{"inicio": "2019-02-01", "rotulo": "2019–2023"}, {"inicio": "2024-05-10", "rotulo": "2023–2027"}]


@pytest.fixture
def docs(tmp_path, cliente, senado):
    return (
        coletar_camara(cliente, tmp_path / "d.json", senado=senado),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )


def test_so_o_perfil_com_dados_ampliados_muda(tmp_path, docs, doc):
    base, ampliado = tmp_path / "base", tmp_path / "ampliado"
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, base)
    construir(*docs, ampliado, perfis_ampliados={alvo: {**doc, "id": alvo}})
    diferentes = [
        c.relative_to(base) for c in base.rglob("*.html")
        if c.read_bytes() != (ampliado / c.relative_to(base)).read_bytes()
    ]
    assert diferentes == [Path("deputados") / f"{alvo}.html"]

    pagina = (ampliado / diferentes[0]).read_text(encoding="utf-8")
    assert 'id="quem-e"' in pagina and 'id="contato"' in pagina
    assert "2 eleições, de 100 a 100 votos" in pagina
    assert "+50,0% de 2022 para 2026" in pagina
    assert "sem correção pela inflação" in pagina
    assert "não indica irregularidade" in pagina
    assert "Do PDT para o PSB." in pagina
    assert "Início do novo mandato" in pagina
    # Gênero fica de fora do perfil individual, como no restante do site.
    for genero in ("Reeleita", "Reeleito", "Deputada", "Eleita"):
        assert genero not in pagina


def test_perfil_com_plenario(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "plenario": PLENARIO}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="plenario"' in pagina and 'id="presenca"' in pagina and 'href="#plenario"' in pagina
    assert "2 votos registrados, 1 deles sobre o texto principal" in pagina
    assert "Presença em 103 dos 115 dias" in pagina
    assert 'data-classe="texto"' in pagina and 'data-temas="Educação"' in pagina and 'data-contra="1"' in pagina and 'data-difere="1"' in pagina
    assert 'static/perfil.js' in pagina
    assert (tmp_path / "site" / "static" / "perfil.js").exists()
    # Proposição com página própria aponta para o site; a ementa longa é cortada na lista.
    assert 'href="../proposicoes/pec-18-2025.html"' in pagina
    assert "x" * 300 not in pagina
    assert 'data-fragmento="../static/perfis/' in pagina
    fragmento = (tmp_path / "site" / "static" / "perfis" / f"{alvo}-votos.html").read_text(encoding="utf-8")
    assert 'data-classe="texto"' in fragmento and 'href="../proposicoes/pec-18-2025.html"' in fragmento
    assert "o que não significa ausência" in pagina
    assert "nem a intenção do parlamentar" in pagina


DINHEIRO = {
    "cota": {
        "por_ano": [{"ano": 2023, "total": 1964701.47, "percentual": 99.3, "nao_utilizado": 10.0, "detalhado": 1881485.31}],
        "categorias": [["Telefonia", 1881485.31]], "fornecedores": [["ACME LTDA", 100.0]], "total_fornecedores": 1,
        "comprovantes": [{"mes": "2023-03", "categoria": "Telefonia", "fornecedor": "ACME LTDA", "valor": 100.0, "url": "https://www.camara.leg.br/d.pdf"}],
    },
    "emendas": {
        "por_ano": [{"ano": 2023, "empenhado": 200.0, "liquidado": 40.0, "pago": 109000000.0, "restos_pagos": 110000.0}],
        "funcoes": [["Saúde", 15.0]], "tipos": [["Transferências Especiais", 16.0]], "destinos": [["Nacional", 1.0]],
        "favorecidos": [{"nome": "FUNDO MUNICIPAL", "municipio": "CAJAMAR", "uf": "SP", "valor": 1500.0}],
        "total_favorecidos": 1, "total_recebido": 1500.0, "arquivo_em": "2026-10-29",
    },
}


def test_perfil_com_dinheiro_publico(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "dinheiro": DINHEIRO}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="dinheiro"' in pagina and 'id="cota"' in pagina and 'id="emendas"' in pagina and 'href="#dinheiro"' in pagina
    assert "R$\u00a01,96\u00a0milhão em cota parlamentar e R$\u00a0109,11\u00a0milhões pagos em emendas" in pagina
    assert "Sem detalhamento nos arquivos abertos" in pagina
    assert "Usar a cota não indica irregularidade" in pagina
    assert "Pagamento não comprova a entrega" in pagina
    assert "Cajamar-SP" in pagina
    assert "static/perfil.js" in pagina
    assert json.loads((tmp_path / "site" / "static" / "perfis" / f"{alvo}-comprovantes.json").read_text(encoding="utf-8"))["itens"][0][2] == "ACME LTDA"


PROPOSTAS = {
    "inicio": "2023-02-01",
    "por_ano": [{"ano": 2023, "autoria": 344, "relatadas": 12}],
    "propostas": [
        {"id": "1", "sigla": "PEC 18/2025", "tipo": "PEC", "data": "2025-04-24", "ementa": "Ementa curta", "situacao": "Transformado em Norma Jurídica",
         "data_situacao": "2026-01-02", "participacao": "coautoria", "temas": ["Saúde"], "norma": {"nome": "Lei Ordinária 14786/2023", "data": "2023-12-28", "veto_parcial": True}},
        {"id": "2", "sigla": "PL 9/2024", "tipo": "PL", "data": "2024-01-02", "ementa": "y" * 400, "situacao": "", "data_situacao": "",
         "participacao": "apoio", "temas": [], "norma": None},
    ],
}
PROPOSTAS["inicio"] = "2023-02-01"


def test_perfil_com_propostas(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "propostas": PROPOSTAS}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="propostas"' in pagina and 'href="#propostas"' in pagina
    assert "1 proposta de autoria desde 2023, 1 virou lei" in pagina
    assert "Da autoria à lei" in pagina and 'id="autoria"' in pagina
    assert "1 de autoria principal" not in pagina and "1 em coautoria" in pagina
    assert "não medem qualidade nem resultado" in pagina
    assert "Lei Ordinária 14786/2023, de 28/12/2023" in pagina and "Com veto parcial" in pagina
    assert 'data-situacao="sem_situacao"' in pagina
    assert "Situação não informada na fonte" in pagina
    assert 'href="../proposicoes/pec-18-2025.html"' in pagina
    assert "y" * 400 not in pagina
    assert 'data-fragmento="../static/perfis/' in pagina
    assert "não pertence a uma pessoa só" in pagina
    assert "quantidade não mede qualidade" in pagina
    assert "static/perfil.js" in pagina


def test_perfil_sem_emendas_explica_em_vez_de_mostrar_tabela_vazia(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    sem = {**DINHEIRO, "emendas": {**DINHEIRO["emendas"], "por_ano": [], "funcoes": [], "destinos": [], "tipos": [], "favorecidos": []}}
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "dinheiro": sem}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert "não traz emendas individuais" in pagina and "Por ano da emenda" not in pagina
    assert "pagos em emendas" not in pagina


def test_build_com_perfis_em_disco_e_imagem(tmp_path, docs, doc):
    """Como o build de verdade: abre cada perfil só na hora, e quem não tem perfil fica com a página simples."""
    alvo, outro = docs[0]["deputados"][0]["id"], docs[0]["deputados"][1]["id"]
    pasta = tmp_path / "perfis"
    pasta.mkdir()
    (pasta / f"{alvo}.json").write_text(json.dumps({**doc, "id": alvo, "dinheiro": DINHEIRO, "propostas": PROPOSTAS, "plenario": PLENARIO}), encoding="utf-8")
    (pasta / f"{alvo}-compartilhar.jpg").write_bytes(b"imagem")
    construir(*docs, tmp_path / "site", site_url="https://exemplo.org", perfis_ampliados=perfis.PerfisEmDisco(pasta), pasta_imagens=pasta)
    site = tmp_path / "site"
    pagina = (site / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert f'content="https://exemplo.org/static/perfis/{alvo}-compartilhar.jpg"' in pagina
    assert (site / "static" / "perfis" / f"{alvo}-compartilhar.jpg").exists()
    for final in ("votos.html", "propostas.html", "comprovantes.json"):
        assert (site / "static" / "perfis" / f"{alvo}-{final}").exists()
    assert 'id="plenario"' not in (site / "deputados" / f"{outro}.html").read_text(encoding="utf-8")


def test_eleicao_sem_votos_validos_fica_na_tabela_mas_nao_no_titulo(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    anulada = {"ano": 2026, "partido": "PL", "uf": "RJ", "situacao": "#NULO", "votos": 0, "total_municipios": 0, "municipios": [], "bens": {"total": 0, "categorias": []}}
    zerada = {**anulada, "ano": 2018, "situacao": "NÃO ELEITO", "total_municipios": 2, "municipios": [["ACRELÂNDIA", 0]]}
    valida = {**anulada, "ano": 2022, "situacao": "ELEITO POR QP", "votos": 500, "total_municipios": 1, "municipios": [["NITERÓI", 500]]}
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "eleicoes": [zerada, valida, anulada]}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert "500 votos na eleição de 2022" in pagina and "Votos na eleição de 2022, por município" in pagina
    assert "Sem resultado informado" in pagina and "#NULO" not in pagina


def test_titulo_de_propostas_no_singular_e_sem_leis(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    uma = {"inicio": "2023-02-01", "por_ano": [], "propostas": [{**PROPOSTAS["propostas"][1], "participacao": "primeira"}]}
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo, "propostas": uma}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert "1 proposta de autoria desde 2023, nenhuma virou lei" in pagina


def test_quem_sai_do_exercicio_mantem_o_perfil_completo(tmp_path, docs, doc):
    legislatura = {"coletado_em": "2026-11-05T12:00:00+00:00", "legislatura_atual": 57, "ano_da_eleicao": 2026, "posse": "2027-02-01", "situacoes": {}, "eleitos_novos": []}
    base = docs[0]["deputados"][0]
    arquivo = [{**base, "id": 777, "nome": "Saiu Antes", "situacao": "Fim de Mandato", "saiu_em": "2027-02-01"}]
    construir(*docs, tmp_path / "site", legislatura=legislatura, arquivo_deputados=arquivo, perfis_ampliados={777: {**doc, "id": 777, "plenario": PLENARIO}})
    pagina = (tmp_path / "site" / "deputados" / "777.html").read_text(encoding="utf-8")
    assert 'id="plenario"' in pagina and "Fora de exercício desde 01/02/2027" in pagina and "Situação oficial: Fim de Mandato" in pagina
    assert "Estes são os dados do último registro" in pagina
    assert (tmp_path / "site" / "static" / "perfis" / "777-votos.html").exists()


def test_formato_em_milhoes():
    assert perfis.milhoes(1964701.47) == "R$\u00a01,96\u00a0milhão"
    assert perfis.milhoes(109107000) == "R$\u00a0109,11\u00a0milhões"
    assert perfis.milhoes(850000) == "R$\u00a0850\u00a0mil"


def test_perfil_sem_plenario_nao_mostra_a_secao(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="plenario"' not in pagina


def test_compartilhamento_do_perfil(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", site_url="https://exemplo.org", perfis_ampliados={alvo: {**doc, "id": alvo}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="compartilhar"' in pagina and "Copiar link" in pagina and "Compartilhar no WhatsApp" in pagina
    assert "Dados deste perfil coletados em" in pagina
    # Sem PNG gerado, fica a imagem padrão do site.
    assert 'content="https://exemplo.org/static/brand/social/open-graph-1200x630.png"' in pagina

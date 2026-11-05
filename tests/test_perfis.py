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


def test_piloto_restrito_ate_autorizacao_do_rollout():
    assert perfis.PILOTO == (204534,)
    guardados = {c.stem for c in Path("data/perfis").glob("*.json")}
    assert guardados <= {"204534"}


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
    assert "o que não significa ausência" in pagina
    assert "nem a intenção do parlamentar" in pagina


def test_perfil_sem_plenario_nao_carrega_o_script(tmp_path, docs, doc):
    alvo = docs[0]["deputados"][0]["id"]
    construir(*docs, tmp_path / "site", perfis_ampliados={alvo: {**doc, "id": alvo}})
    pagina = (tmp_path / "site" / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert 'id="plenario"' not in pagina and "perfil.js" not in pagina

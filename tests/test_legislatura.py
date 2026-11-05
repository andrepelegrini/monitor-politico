import json
from datetime import date
from pathlib import Path

import pytest

from conftest import cliente_falso, congresso_falso
from monitor_politico import camara as modulo_camara, legislatura
from monitor_politico.build import construir
from monitor_politico.camara import arquivar_saidas, coletar as coletar_camara
from monitor_politico.congresso import coletar as coletar_congresso
from monitor_politico.models import Deputado, Gabinete
from monitor_politico.senado import coletar as coletar_senado


def linha(cpf, cargo="DEPUTADO FEDERAL", resultado="ELEITO POR QP", turno="1", sq=None, nome="FULANO DE TAL", nascimento="01/01/1980"):
    return {
        "NR_CPF_CANDIDATO": cpf, "DS_CARGO": cargo, "DS_SIT_TOT_TURNO": resultado, "NR_TURNO": turno, "SQ_CANDIDATO": sq or f"sq{cpf}",
        "NM_CANDIDATO": nome, "NM_URNA_CANDIDATO": nome, "DT_NASCIMENTO": nascimento, "SG_PARTIDO": "PSB", "SG_UF": "SP",
    }


@pytest.mark.parametrize("cargo, resultado, chave, rotulo", [
    ("DEPUTADO FEDERAL", "ELEITO POR QP", "reeleicao", "Reeleição"),
    ("DEPUTADO FEDERAL", "ELEITO POR MÉDIA", "reeleicao", "Reeleição"),
    ("DEPUTADO FEDERAL", "SUPLENTE", "suplencia", "Suplência"),
    ("DEPUTADO FEDERAL", "NÃO ELEITO", "nao_reeleito", "Não se reelegeu"),
    ("DEPUTADO FEDERAL", "#NULO", "sem_resultado", "Candidatura sem resultado"),
    ("SENADOR", "ELEITO", "outro_eleito", "Eleição para o Senado"),
    ("GOVERNADOR", "ELEITO", "outro_eleito", "Eleição para o governo do estado"),
    ("SENADOR", "NÃO ELEITO", "outro_disputou", "Disputou outro cargo"),
])
def test_situacao_de_quem_tem_mandato(cargo, resultado, chave, rotulo):
    situacao = legislatura.situacao_de_quem_tem_mandato(linha("1", cargo, resultado))
    assert (situacao["chave"], situacao["rotulo"]) == (chave, rotulo)


def test_sem_candidatura():
    assert legislatura.situacao_de_quem_tem_mandato(None)["rotulo"] == "Sem candidatura em 2026"


def test_falecimento_nao_vira_sem_candidatura():
    situacao = legislatura.situacao_de_quem_tem_mandato(None, "2024-05-12")
    assert situacao == {"chave": "falecimento", "rotulo": "Falecimento em 12/05/2024"}
    assert legislatura.situacao_de_quem_tem_mandato(None, "")["chave"] == "sem_candidatura"


def test_rotulos_nao_tem_genero():
    for rotulo in legislatura.ROTULOS.values():
        for genero in ("Reeleit", "Novat", "Eleita", "Eleito", "Deputada"):
            assert genero not in rotulo


def test_segundo_turno_prevalece():
    por_cpf = legislatura.candidaturas_por_cpf([linha("1", "GOVERNADOR", "ELEITO", "2"), linha("1", "GOVERNADOR", "2º TURNO", "1")])
    assert por_cpf["1"]["DS_SIT_TOT_TURNO"] == "ELEITO"


HISTORICO = [
    {"uri": "https://x/deputados/10", "idLegislaturaFinal": "57", "nomeCivil": "Com Mandato Silva", "dataNascimento": "1970-01-01"},
    {"uri": "https://x/deputados/20", "idLegislaturaFinal": "57", "nomeCivil": "Saiu Antes Souza", "dataNascimento": "1971-01-01"},
    {"uri": "https://x/deputados/30", "idLegislaturaFinal": "55", "nomeCivil": "Antiga Parlamentar Lima", "dataNascimento": "1960-05-06"},
    {"uri": "https://x/deputados/31", "idLegislaturaFinal": "55", "nomeCivil": "Pessoa Outra Lima", "dataNascimento": "1961-05-06"},
]


def detalhes(id_):
    cpfs = {10: "c10", 20: "c20", 30: "c30", 31: "c-diferente"}
    return {
        "id": id_, "uri": f"https://x/deputados/{id_}", "cpf": cpfs[id_], "dataNascimento": "1970-01-01",
        "ultimoStatus": {"nome": f"Nome {id_}", "nomeEleitoral": f"Nome {id_}", "siglaPartido": "PL", "siglaUf": "RJ", "situacao": "Vacância", "data": "2025-01-01", "gabinete": {}},
    }


class Camara:
    def _get(self, url):
        return {"dados": detalhes(int(url.rsplit("/", 1)[-1]))}


class Fonte:
    def candidatos(self, _ano):
        return [
            linha("c10", sq="S10"),
            linha("c20", cargo="SENADOR", resultado="NÃO ELEITO", sq="S20"),
            linha("c30", sq="S30", nome="ANTIGA PARLAMENTAR LIMA", nascimento="06/05/1960"),
            linha("c-novo", sq="S40", nome="PESSOA NOVA", nascimento="02/02/1990"),
            linha("c-homonimo", sq="S41", nome="PESSOA OUTRA LIMA", nascimento="06/05/1961"),  # mesmo nome e data, outro CPF
            linha("c-sem-vaga", resultado="NÃO ELEITO", sq="S50"),
        ]

    def votacao(self, _ano, _uf):
        def v(sq, votos, municipio="SÃO PAULO", turno="1"):
            return {"SQ_CANDIDATO": sq, "NM_MUNICIPIO": municipio, "NR_TURNO": turno, "QT_VOTOS_NOMINAIS_VALIDOS": str(votos)}
        return [v("S10", 100), v("S40", 70), v("S40", 30, "OSASCO"), v("S20", 50)]

    def bens(self, _ano):
        return [{"SQ_CANDIDATO": "S40", "DS_TIPO_BEM_CANDIDATO": "Apartamento", "VR_BEM_CANDIDATO": "10,50", "DS_BEM_CANDIDATO": "Rua Secreta"}]


@pytest.fixture
def coleta():
    return legislatura.coletar(Camara(), Fonte(), HISTORICO, em_exercicio={10})


def test_quem_exerceu_mandato_recebe_situacao(coleta):
    doc, _ = coleta
    assert doc["situacoes"]["10"]["rotulo"] == "Reeleição" and doc["situacoes"]["10"]["votos"] == 100
    assert doc["situacoes"]["20"]["rotulo"] == "Disputou outro cargo"


def test_arquivo_tem_so_quem_esta_fora_de_exercicio(coleta):
    _, arquivo = coleta
    assert [d["id"] for d in arquivo] == [20]
    assert arquivo[0]["saiu_em"] == "2025-01-01" and arquivo[0]["situacao"] == "Vacância"
    assert "cpf" not in arquivo[0]


def test_eleitos_novos_separam_retorno_e_primeiro_mandato_pelo_cpf(coleta):
    doc, _ = coleta
    por_sq = {e["sq"]: e for e in doc["eleitos_novos"]}
    assert set(por_sq) == {"S30", "S40", "S41"}  # S10 já tem mandato e S50 não foi eleito
    assert por_sq["S30"]["chave"] == "retorno" and por_sq["S30"]["id_camara_antigo"] == 30
    assert por_sq["S40"]["chave"] == "primeiro"
    assert por_sq["S41"]["chave"] == "primeiro"  # nome e data iguais, CPF diferente


def test_eleito_novo_tem_votos_e_bens_sem_dados_pessoais(coleta):
    doc, _ = coleta
    novo = next(e for e in doc["eleitos_novos"] if e["sq"] == "S40")
    assert novo["votos"] == 100 and novo["total_municipios"] == 2 and novo["municipios"][0] == ["SÃO PAULO", 70]
    assert novo["bens"]["total"] == 10.5
    texto = json.dumps(coleta, ensure_ascii=False)
    for proibido in ("c10", "c-novo", "1990", "Rua Secreta"):
        assert proibido not in texto


def test_resumo_conta_quem_chega_e_quem_sai(coleta):
    doc, _ = coleta
    r = legislatura.resumo(doc)
    assert r["total_eleitos"] == 4
    assert {c["chave"]: c["valor"] for c in r["chegam"]} == {"reeleicao": 1, "retorno": 1, "primeiro": 2}
    assert {c["chave"]: c["valor"] for c in r["saem"]} == {"outro_disputou": 1}


def deputado(id_, nome="Fulano"):
    return Deputado(id=id_, nome=nome, partido="PT", uf="SP", url_foto=None, situacao="Exercício", condicao_eleitoral="Titular", gabinete=Gabinete(None, None, None, None, None), uri_api="", url_site="")


def test_quem_sai_vai_para_o_arquivo_e_quem_volta_sai_dele(tmp_path):
    caminho = tmp_path / "arquivo.json"
    caminho.write_text(json.dumps({"deputados": [{**deputado(3, "Voltou").para_dict(), "saiu_em": "2024-01-01"}, {**deputado(4, "Antigo").para_dict(), "saiu_em": "2024-01-01"}]}), encoding="utf-8")
    arquivar_saidas(caminho, {1: deputado(1, "Saiu"), 2: deputado(2, "Ficou")}, [deputado(2, "Ficou"), deputado(3, "Voltou")], date(2027, 2, 1))
    guardados = {d["id"]: d for d in json.loads(caminho.read_text(encoding="utf-8"))["deputados"]}
    assert set(guardados) == {1, 4}
    assert guardados[1]["saiu_em"] == "2027-02-01"
    assert guardados[4]["saiu_em"] == "2024-01-01"


def test_sem_arquivo_inicial_nada_e_criado(tmp_path):
    caminho = tmp_path / "arquivo.json"
    arquivar_saidas(caminho, {1: deputado(1)}, [], date(2027, 2, 1))
    assert not caminho.exists()


@pytest.fixture
def docs(tmp_path, cliente, senado):
    return (
        coletar_camara(cliente, tmp_path / "d.json", senado=senado),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )


LEGISLATURA = {
    "coletado_em": "2026-11-05T12:00:00+00:00", "legislatura_atual": 57, "ano_da_eleicao": 2026, "posse": "2027-02-01",
    "situacoes": {},
    "eleitos_novos": [{
        "sq": "S40", "nome": "PESSOA NOVA", "partido": "PSB", "uf": "SP", "chave": "primeiro", "rotulo": "Primeiro mandato", "id_camara_antigo": None,
        "votos": 100, "total_municipios": 2, "municipios": [["SÃO PAULO", 70], ["OSASCO", 30]], "bens": {"total": 10.5, "categorias": [["Apartamento", 10.5]]},
    }],
}


def test_paginas_da_virada_de_legislatura(tmp_path, docs):
    alvo = docs[0]["deputados"][0]["id"]
    leg = {**LEGISLATURA, "situacoes": {str(alvo): {"chave": "reeleicao", "rotulo": "Reeleição"}, "777": {"chave": "suplencia", "rotulo": "Suplência"}}}
    arquivo = [{**deputado(777, "Saiu Antes").para_dict(), "situacao": "Vacância", "saiu_em": "2025-01-01"}]
    construir(*docs, tmp_path / "site", legislatura=leg, arquivo_deputados=arquivo)
    site = tmp_path / "site"

    saiu = (site / "deputados" / "777.html").read_text(encoding="utf-8")
    assert "Fora de exercício desde 01/01/2025" in saiu and "Situação oficial: Vacância" in saiu and "Suplência" in saiu
    anteriores = (site / "deputados" / "anteriores.html").read_text(encoding="utf-8")
    assert 'href="777.html"' in anteriores and "Saiu Antes" in anteriores

    novo = (site / "deputados" / "eleitos" / "S40.html").read_text(encoding="utf-8")
    assert "<h1>Pessoa Nova</h1>" in novo and "Primeiro mandato" in novo and "Posse prevista para 01/02/2027" in novo
    assert "não indicam irregularidade" in novo
    indice = (site / "deputados" / "eleitos" / "index.html").read_text(encoding="utf-8")
    assert 'href="S40.html"' in indice and "Quem são os 2 eleitos" in indice and "Reeleição" in indice

    lista = (site / "deputados" / "index.html").read_text(encoding="utf-8")
    assert 'data-situacao="Reeleição"' in lista and 'id="f-situacao"' in lista and 'href="eleitos/index.html"' in lista
    perfil = (site / "deputados" / f"{alvo}.html").read_text(encoding="utf-8")
    assert '<span class="ce-badge ce-badge--outline">Reeleição</span>' in perfil

    busca = json.loads((site / "static" / "busca.json").read_text(encoding="utf-8"))
    enderecos = [p[4] for p in busca["parlamentares"]]
    assert "deputados/777.html" in enderecos and "deputados/eleitos/S40.html" in enderecos


def test_sem_dados_da_legislatura_as_paginas_nao_mudam(tmp_path, docs):
    construir(*docs, tmp_path / "site")
    assert not (tmp_path / "site" / "deputados" / "anteriores.html").exists()
    assert not (tmp_path / "site" / "deputados" / "eleitos").exists()
    lista = (tmp_path / "site" / "deputados" / "index.html").read_text(encoding="utf-8")
    assert "f-situacao" not in lista and "ce-badge" not in lista


def test_lista_de_senadores_nao_ganha_badge(tmp_path, docs):
    construir(*docs, tmp_path / "site", legislatura=LEGISLATURA, arquivo_deputados=[])
    pagina = (tmp_path / "site" / "senadores" / "index.html").read_text(encoding="utf-8")
    assert "f-situacao" not in pagina and "eleitos/index.html" not in pagina

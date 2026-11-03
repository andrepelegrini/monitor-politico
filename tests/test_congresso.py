from datetime import date

import pytest

from conftest import congresso_falso
from monitor_politico.congresso import ColetaIncompleta, coletar, eh_procedimento

HOJE = date(2026, 11, 2)


@pytest.fixture
def doc(tmp_path):
    return coletar(*congresso_falso(), tmp_path / "congresso.json", hoje=HOJE)


def test_reune_votadas_e_pauta(doc):
    # A urgência aprovada (só votação de rito) não entra sozinha; PL 3099/2019
    # entra pela pauta, e PEC 18/2025 e PDS 240/2011 pela pauta do Senado.
    assert set(doc["proposicoes"]) == {"PDL 274/2026", "PDS 240/2011", "PEC 18/2025", "PEC 221/2019", "PL 3099/2019", "PLP 186/2026"}
    assert doc["periodo"] == {"votacoes_desde": "2026-10-03", "pauta_ate": "2026-11-08"}


def test_mesma_proposicao_junta_votacoes_das_duas_casas(doc):
    plp = doc["proposicoes"]["PLP 186/2026"]
    assert [v["casa"] for v in plp["votacoes"]] == ["Câmara", "Câmara", "Câmara", "Senado"]
    assert plp["url_camara"] == "https://www.camara.leg.br/propostas-legislativas/2635476"
    assert plp["url_senado"].startswith("https://www25.senado.leg.br/web/atividade/materias/-/materia/")
    assert plp["situacao"]["norma"] == "Lei Complementar 238/2026"
    assert plp["casa_inicial"] == "Câmara"


def test_votacao_nominal_da_camara(doc):
    [principal] = [v for v in doc["proposicoes"]["PLP 186/2026"]["votacoes"] if v["casa"] == "Câmara" and not v["procedimento"]]
    assert principal["resultado"] == "aprovada"
    assert principal["nominal"]
    votos = principal["votos"]
    assert principal["placar"]["sim"] == sum(v["voto"] == "Sim" for v in votos)
    assert principal["placar"]["nao"] == sum(v["voto"] == "Não" for v in votos)
    assert ["Presidente da sessão (art. 17)", 1] in principal["placar"]["outros"]
    assert ["MISSÃO", "Não"] in principal["orientacoes"]
    assert ["PSB", None] in principal["orientacoes"]  # sem orientação registrada


def test_votacao_simbolica_nao_tem_votos(doc):
    simbolicas = [v for v in doc["proposicoes"]["PDL 274/2026"]["votacoes"] if not v["nominal"]]
    assert simbolicas
    for v in simbolicas:
        assert v["votos"] == [] and v["placar"] is None and v["orientacoes"] is None


def test_votacao_do_senado_descarta_dados_pessoais(doc, tmp_path):
    [senado] = [v for v in doc["proposicoes"]["PEC 221/2019"]["votacoes"] if v["casa"] == "Senado"]
    assert senado["nominal"] and senado["orientacoes"] is None
    assert all(set(v) == {"id", "nome", "partido", "uf", "voto"} for v in senado["votos"])
    assert "sexoParlamentar" not in (tmp_path / "congresso.json").read_text(encoding="utf-8")


def test_situacao_apelido_e_temas(doc):
    pec = doc["proposicoes"]["PEC 221/2019"]
    assert pec["apelido"] == "Fim da escala 6x1"
    assert pec["situacao"]["norma"] == "Emenda Constitucional 141/2026"
    assert "Trabalho e Emprego" in pec["temas"]
    # Proposição que está no Senado: situação vem do Senado, mais recente.
    assert doc["proposicoes"]["PEC 18/2025"]["situacao"]["casa"] == "Senado"


def test_pauta_das_duas_casas(doc):
    camara, senado = doc["pauta"]
    assert (camara["casa"], camara["data_hora"]) == ("Câmara", "2026-11-03T13:55")
    # O REQ de urgência vira o projeto a que se refere; o PDL repetido aparece uma vez.
    assert [i["chave"] for i in camara["itens"]] == ["PL 3099/2019", "PDL 274/2026"]
    assert senado["casa"] == "Senado"
    assert [i["chave"] for i in senado["itens"]] == ["PEC 18/2025", "PDS 240/2011"]


def test_falha_numa_proposicao_reaproveita_coleta_anterior(tmp_path, monkeypatch):
    monkeypatch.setattr("monitor_politico.congresso.LIMITE_FALHAS", 0.5)
    saida = tmp_path / "congresso.json"
    antes = coletar(*congresso_falso(), saida, hoje=HOJE)

    avisos = []
    depois = coletar(*congresso_falso(falhar=["/proposicoes/2204495"]), saida, hoje=HOJE, avisar=avisos.append)
    assert depois["proposicoes"]["PL 3099/2019"] == antes["proposicoes"]["PL 3099/2019"]
    assert any("PL 3099/2019" in a for a in avisos)


def test_muitas_falhas_abortam_sem_sobrescrever(tmp_path):
    saida = tmp_path / "congresso.json"
    coletar(*congresso_falso(), saida, hoje=HOJE)
    antes = saida.read_text(encoding="utf-8")

    with pytest.raises(ColetaIncompleta):
        coletar(*congresso_falso(falhar=["/proposicoes"]), saida, hoje=HOJE, avisar=lambda _m: None)
    assert saida.read_text(encoding="utf-8") == antes


@pytest.mark.parametrize("descricao, esperado", [
    ("Aprovado, por unanimidade, o Requerimento de Urgência (Art. 155 do RICD).", True),
    ("Aprovada a Redação Final assinada pelo relator.", True),
    ("Mantido o texto.", True),
    ("Aprovada a Medida Provisória nº 1.375, de 2026, na forma do Projeto de Lei de Conversão, ressalvado o destaque.", False),
    ("Votação nominal da Proposta de Emenda à Constituição nº 221, de 2019, em primeiro turno.", False),
])
def test_votacoes_de_rito(descricao, esperado):
    assert eh_procedimento(descricao) is esperado

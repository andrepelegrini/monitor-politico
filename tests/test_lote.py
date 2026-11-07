import json
import tarfile
from datetime import date
from pathlib import Path

import httpx
import pytest

from monitor_politico import lote, metricas, pacote, perfis


def test_cache_guarda_e_recupera(tmp_path):
    cache = lote.ler_cache(tmp_path)
    assert cache == {"normas": {}, "presenca": {}, "pagina": {}, "eleicoes": {}}
    cache["normas"]["1"] = {"nome": "Lei 1/2024"}
    lote.salvar_cache(tmp_path, cache)
    assert lote.ler_cache(tmp_path)["normas"]["1"]["nome"] == "Lei 1/2024"
    assert perfis.ler_perfis(tmp_path) == {}  # o cache não é confundido com um perfil


def test_falha_isolada_mantem_o_dado_anterior():
    def funcao(id_):
        if id_ == 2:
            raise httpx.ConnectError("fora")
        return id_ * 10
    assert lote._com_tolerancia(funcao, list(range(1, 11)), "teste", {2: "antigo"})[2] == "antigo"


def test_falha_em_massa_interrompe():
    def funcao(_id):
        raise httpx.ConnectError("fora")
    with pytest.raises(lote.ColetaInterrompida):
        lote._com_tolerancia(funcao, list(range(10)), "teste")


class Financas:
    def __init__(self):
        self.paginas = []

    def pagina_do_deputado(self, id_, ano):
        self.paginas.append((id_, ano))
        return """<h4>Cota parlamentar</h4> ? <td>Percentual Gasto</td><td>100,00</td><td>50.00%</td><td>Não utilizado</td><td>100,00</td>
        <div>Propostas legislativas de sua autoria</div> <a>3</a> <div>relatadas</div> <a>1</a>"""


class Arquivos:
    def __init__(self):
        self.relatorios = []

    def relatorio_de_presenca(self, id_, ano):
        self.relatorios.append((id_, ano))
        return {"dias": 10, "presencas": 9, "justificadas": 1, "nao_justificadas": 0}


def test_ano_passado_vem_do_cache_e_o_atual_e_consultado():
    financas, arquivos = Financas(), Arquivos()
    cache = {"normas": {}, "eleicoes": {}, "presenca": {"1": {"2025": {"dias": 1}}}, "pagina": {"1": {"2025": {"cota": {"total": 1}, "atuacao": None}}}}
    lote.paginas_oficiais(financas, arquivos, [1], {1: [2025, 2026]}, cache, 2026)
    assert financas.paginas == [(1, 2026)] and arquivos.relatorios == [(1, 2026)]
    assert cache["pagina"]["1"]["2026"]["cota"]["total"] == 100.0
    assert cache["pagina"]["1"]["2026"]["atuacao"] == {"autoria": 3, "relatadas": 1}
    assert cache["pagina"]["1"]["2025"]["cota"] == {"total": 1}


def test_pagina_que_mudou_de_formato_para_quase_todos_interrompe():
    class SemQuadro(Financas):
        def pagina_do_deputado(self, id_, ano):
            return "<p>outra página</p>"
    ids = list(range(20))
    cache = {"normas": {}, "eleicoes": {}, "presenca": {}, "pagina": {}}
    with pytest.raises(lote.ColetaInterrompida):
        lote.paginas_oficiais(SemQuadro(), Arquivos(), ids, {i: [2026] for i in ids}, cache, 2026)


def test_ano_sem_quadro_nao_e_falha_para_uma_pessoa():
    class Parcial(Financas):
        def pagina_do_deputado(self, id_, ano):
            return "<p>sem exercício</p>" if ano == 2025 else super().pagina_do_deputado(id_, ano)
    cache = {"normas": {}, "eleicoes": {}, "presenca": {}, "pagina": {}}
    lote.paginas_oficiais(Parcial(), Arquivos(), [1], {1: [2025, 2026]}, cache, 2026)
    assert cache["pagina"]["1"]["2025"] == {"cota": None, "atuacao": None}


def proposta(id_, participacao, data):
    return {"id": id_, "sigla": f"PL {id_}/2020", "participacao": participacao, "norma": {"nome": f"Lei {id_}", "data": data, "veto_parcial": False}}


def test_metricas_contam_pela_data_da_norma_sem_apoio():
    docs = {
        1: {"propostas": {"propostas": [proposta("a", "primeira", "2024-01-01"), proposta("b", "primeira", "2020-01-01"), proposta("c", "apoio", "2024-01-01")]}},
        2: {"propostas": {"propostas": [proposta("a", "coautoria", "2024-01-01"), {"id": "d", "participacao": "primeira", "norma": None}]}},
    }
    m = lote.metricas_dos_documentos(docs, metricas.INICIO_MANDATO, "agora")
    assert {k: (v["principal"], v["coautoria"]) for k, v in m["por_deputado"].items()} == {"1": (1, 0), "2": (0, 1)}
    assert [(n["id"], n["principal"], n["coautoria"]) for n in m["normas"]] == [("a", ["1"], ["2"])]


def test_metricas_somam_votos_presenca_e_relatorias_do_mandato():
    docs = {1: {
        "plenario": {"votos": {"votos_registrados": 957}, "presenca": {"por_ano": [{"ano": 2023, "presencas": 100, "dias": 110}, {"ano": 2024, "presencas": 80, "dias": 90}]}},
        "propostas": {"propostas": [], "por_ano": [{"ano": 2023, "relatadas": 9000}], "relatorias_no_mandato": 26},
    }}
    numeros = lote.metricas_dos_documentos(docs, "2023-02-01", "agora")["por_deputado"]["1"]
    assert (numeros["votos"], numeros["presencas"], numeros["dias"], numeros["relatorias"]) == (957, 180, 200, 26)


def test_pacote_ida_e_volta_com_checksum(tmp_path):
    origem = tmp_path / "origem"
    (origem / "_cache").mkdir(parents=True)
    (origem / "1.json").write_text('{"id": 1}', encoding="utf-8")
    (origem / "_cache" / "cache.json").write_text("{}", encoding="utf-8")
    versao = tmp_path / "versao.json"
    arquivo = pacote.empacotar(origem, versao, tmp_path)
    info = json.loads(versao.read_text(encoding="utf-8"))
    assert info["perfis"] == 1 and info["nome"] == arquivo.name

    conteudo = arquivo.read_bytes()
    cliente = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=conteudo)))
    destino = tmp_path / "destino"
    pacote.baixar(destino, versao, cliente)
    assert (destino / "1.json").exists() and (destino / "_cache" / "cache.json").exists()


@pytest.mark.parametrize("documento", [
    {"dinheiro": {"cota": {"comprovantes": [{"fornecedor": "FULANA DE TAL 04970541167"}]}}},
    {"dinheiro": {"cota": {"fornecedores": [["FULANO 489.909.226-15", 10.0]]}}},
    {"dinheiro": {"emendas": {"favorecidos": [{"nome": "FULANO 04970541167"}]}}},
    {"propostas": {"propostas": [{"ementa": "Prisão de Fulano (CPF 750.100.207-00)"}]}},
    {"cpf": "04970541167"},
])
def test_pacote_recusa_dados_pessoais(tmp_path, documento):
    pasta = tmp_path / "perfis"
    pasta.mkdir()
    (pasta / "1.json").write_text(json.dumps(documento), encoding="utf-8")
    with pytest.raises(pacote.PacoteInvalido):
        pacote.empacotar(pasta, tmp_path / "versao.json", tmp_path)
    assert not (tmp_path / "versao.json").exists()


def test_pacote_aceita_numeros_que_nao_sao_cpf():
    assert pacote.dados_pessoais_no_documento({
        "id": 204534, "fornecedor": "POSTO 12 DE OUTUBRO LTDA", "ementa": "Lei nº 14.786, de 2023; processo 12345678901",
        "url": "https://www.camara.leg.br/doc/12345678901.pdf",
    }) == []


def test_pacote_com_checksum_errado_e_recusado(tmp_path):
    versao = tmp_path / "versao.json"
    versao.write_text(json.dumps({"nome": "x.tar.gz", "sha256": "abc", "perfis": 1}), encoding="utf-8")
    cliente = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(200, content=b"outra coisa")))
    with pytest.raises(pacote.PacoteInvalido):
        pacote.baixar(tmp_path / "d", versao, cliente)


def test_download_que_falha_interrompe_o_build(tmp_path):
    versao = tmp_path / "versao.json"
    versao.write_text(json.dumps({"nome": "x.tar.gz", "sha256": "abc", "perfis": 1}), encoding="utf-8")
    cliente = httpx.Client(transport=httpx.MockTransport(lambda _r: httpx.Response(404)))
    with pytest.raises(httpx.HTTPStatusError):
        pacote.baixar(tmp_path / "d", versao, cliente)


def test_pacote_com_caminho_perigoso_e_recusado(tmp_path):
    arquivo = tmp_path / "ruim.tar.gz"
    origem = tmp_path / "x.txt"
    origem.write_text("x", encoding="utf-8")
    with tarfile.open(arquivo, "w:gz") as tar:
        tar.add(origem, arcname="../fora.txt")
    with pytest.raises(pacote.PacoteInvalido):
        pacote.extrair(arquivo, tmp_path / "destino")
    assert not (tmp_path / "fora.txt").exists()

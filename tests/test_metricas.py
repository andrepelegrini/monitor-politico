from datetime import date
from pathlib import Path

import pytest

from conftest import congresso_falso
from monitor_politico import metricas
from monitor_politico.build import construir
from monitor_politico.camara import coletar as coletar_camara
from monitor_politico.congresso import coletar as coletar_congresso
from monitor_politico.senado import coletar as coletar_senado

INICIO = "2023-02-01"


def autor(proposta, deputado, ordem="1", proponente="1"):
    return {"idProposicao": proposta, "idDeputadoAutor": str(deputado), "ordemAssinatura": ordem, "proponente": proponente}


def proposta(id_, tipo="PL", situacao="Transformado em Norma Jurídica"):
    return {"id": id_, "siglaTipo": tipo, "numero": id_, "ano": "2020", "ultimoStatus_descricaoSituacao": situacao}


class Fonte:
    def linhas(self, tipo, ano):
        if ano != 2020:
            return []
        if tipo == "proposicoesAutores":
            return [
                autor("1", 10), autor("1", 20, ordem="2"), autor("1", 99, ordem="3"),  # lei recente
                autor("2", 10),  # lei antiga, antes do mandato
                autor("3", 20), autor("3", 10, ordem="9", proponente="0"),  # apoio não conta
                autor("4", 10),  # ainda em tramitação
                autor("5", 10),  # requerimento
                autor("6", 10),  # sem número de norma na tramitação
            ]
        return [
            proposta("1"), proposta("2"), proposta("3", tipo="PEC"), proposta("4", situacao="Aguardando Parecer"),
            proposta("5", tipo="REQ"), proposta("6"),
        ]


class Camara:
    TRAMITACOES = {
        "1": ("2024-05-01T10:00", "Transformado na Lei Ordinária 14999/2024. DOU."),
        "2": ("2021-05-01T10:00", "Transformado na Lei Ordinária 14000/2021. DOU."),
        "3": ("2025-05-01T10:00", "Transformado na Emenda Constitucional 130/2025. DOU."),
        "6": ("2025-06-01T10:00", "Remessa ao Senado."),
    }

    def _get(self, url):
        id_ = url.split("/")[2]
        data, despacho = self.TRAMITACOES[id_]
        return {"dados": [{"dataHora": data, "despacho": despacho}]}


@pytest.fixture
def doc():
    return metricas.coletar(Fonte(), Camara(), [10, 20, 30], hoje=date(2020, 12, 1), inicio=INICIO)


def test_conta_por_data_da_lei_e_tipo_de_autoria(doc):
    assert doc["por_deputado"] == {
        "10": {"principal": 1, "coautoria": 0},
        "20": {"principal": 1, "coautoria": 1},
        "30": {"principal": 0, "coautoria": 0},
    }


def test_registra_as_leis_para_conferencia(doc):
    assert [(n["sigla"], n["norma"]) for n in doc["normas"]] == [("PEC 3/2020", "Emenda Constitucional 130/2025"), ("PL 1/2020", "Lei Ordinária 14999/2024")]
    assert doc["normas"][1]["principal"] == ["10"] and doc["normas"][1]["coautoria"] == ["20"]


def test_avisa_quando_a_norma_nao_foi_identificada(doc):
    assert doc["sem_norma_identificada"] == ["PL 6/2020"]


def test_falha_na_tramitacao_interrompe_a_coleta():
    class CamaraFora:
        def _get(self, _url):
            raise RuntimeError("fora do ar")
    with pytest.raises(RuntimeError):
        metricas.coletar(Fonte(), CamaraFora(), [10], hoje=date(2020, 12, 1), inicio=INICIO)


def test_quem_nao_esta_na_coleta_fica_com_zero(doc):
    assert metricas.do_deputado(doc, 999) == {"principal": 0, "coautoria": 0}


@pytest.fixture
def docs(tmp_path, cliente, senado):
    return (
        coletar_camara(cliente, tmp_path / "d.json", senado=senado),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )


def test_so_a_lista_de_deputados_muda(tmp_path, docs):
    alvo = docs[0]["deputados"][0]["id"]
    numeros = {"inicio": INICIO, "por_deputado": {str(alvo): {"principal": 6, "coautoria": 4}}}
    base, nova = tmp_path / "base", tmp_path / "nova"
    construir(*docs, base)
    construir(*docs, nova, metricas=numeros)
    diferentes = [c.relative_to(base) for c in base.rglob("*.html") if c.read_bytes() != (nova / c.relative_to(base)).read_bytes()]
    assert diferentes == [Path("deputados") / "index.html"]
    pagina = (nova / "deputados" / "index.html").read_text(encoding="utf-8")
    assert 'data-principal="6" data-coautoria="4"' in pagina
    assert "<strong>6</strong> leis de autoria principal · 4 em coautoria" in pagina
    assert "<strong>0</strong> leis de autoria principal · 0 em coautoria" in pagina
    assert 'id="f-ordem"' in pagina
    assert "não mede qualidade" in pagina
    assert "produtividade" not in pagina.lower()


def test_lista_de_senadores_nao_ganha_a_metrica(tmp_path, docs):
    construir(*docs, tmp_path / "site", metricas={"inicio": INICIO, "por_deputado": {}})
    pagina = (tmp_path / "site" / "senadores" / "index.html").read_text(encoding="utf-8")
    assert "f-ordem" not in pagina and "data-principal" not in pagina

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


def test_quem_nao_esta_na_coleta_fica_com_zero():
    assert metricas.do_deputado({"por_deputado": {"10": {"principal": 1, "coautoria": 0}}}, 999) == {"principal": 0, "coautoria": 0}
    assert metricas.do_deputado({"por_deputado": {"10": {"principal": 1, "coautoria": 0}}}, 10)["principal"] == 1


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

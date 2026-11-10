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


def test_quem_nao_esta_na_coleta_fica_com_zero_e_sem_percentual():
    numeros = metricas.do_deputado({"por_deputado": {"10": {"principal": 1}}}, 999)
    assert numeros["principal"] == 0 and numeros["votos"] == 0 and numeros["percentual_presenca"] is None


def test_percentual_de_presenca_sobre_os_dias_em_exercicio():
    numeros = metricas.do_deputado({"por_deputado": {"10": {"principal": 1, "presencas": 378, "dias": 400}}}, 10)
    assert numeros["principal"] == 1 and numeros["percentual_presenca"] == 94.5


@pytest.fixture
def docs(tmp_path, cliente, senado):
    return (
        coletar_camara(cliente, tmp_path / "d.json", senado=senado),
        coletar_senado(senado, tmp_path / "s.json", minimo=1),
        coletar_congresso(*congresso_falso(), tmp_path / "c.json", hoje=date(2026, 11, 2)),
    )


def test_so_a_lista_de_deputados_muda(tmp_path, docs):
    alvo = docs[0]["deputados"][0]["id"]
    numeros = {"inicio": INICIO, "por_deputado": {str(alvo): {"principal": 6, "coautoria": 4, "votos": 957, "presencas": 378, "dias": 400, "relatorias": 53}}}
    base, nova = tmp_path / "base", tmp_path / "nova"
    construir(*docs, base)
    construir(*docs, nova, metricas=numeros)
    diferentes = [c.relative_to(base) for c in base.rglob("*.html") if c.read_bytes() != (nova / c.relative_to(base)).read_bytes()]
    # Fora as páginas de estado, que também mostram os números de cada deputado, só a lista muda.
    assert [c for c in diferentes if c.parts[0] != "estados"] == [Path("deputados") / "index.html"]
    pagina = (nova / "deputados" / "index.html").read_text(encoding="utf-8")
    assert 'data-principal="6" data-coautoria="4" data-votos="957" data-presenca="94.5" data-relatorias="53"' in pagina
    assert "<strong>957</strong> votos · <strong>378</strong> de 400 dias · <strong>53</strong> relatorias atuais" in pagina
    assert 'data-presenca="-1"' in pagina  # quem não tem dias fica por último ao ordenar
    assert '<option value="presenca">' in pagina
    assert "<strong>6</strong> leis de autoria principal · 4 em coautoria" in pagina
    assert "<strong>0</strong> leis de autoria principal · 0 em coautoria" in pagina
    assert 'id="f-ordem"' in pagina
    assert "não medem qualidade" in pagina
    assert "produtividade" not in pagina.lower()


def test_lista_de_senadores_nao_ganha_a_metrica(tmp_path, docs):
    construir(*docs, tmp_path / "site", metricas={"inicio": INICIO, "por_deputado": {}})
    pagina = (tmp_path / "site" / "senadores" / "index.html").read_text(encoding="utf-8")
    assert "f-ordem" not in pagina and "data-principal" not in pagina

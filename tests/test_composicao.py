import httpx

from conftest import carregar, cliente_falso, responder_com_fixtures, senado_falso
from monitor_politico import composicao
from monitor_politico.camara import coletar as coletar_camara
from monitor_politico.senado import coletar as coletar_senado


def _cargos(lideres):
    return {l["cargo"]: (l["nome"], l["partido"], l["uf"]) for l in lideres}


def test_lideres_do_senado():
    lideres = composicao.lideres(carregar("senado_liderancas.json"), "SF")
    assert [l["cargo"] for l in lideres] == [
        "Líder do Governo", "Líder da Oposição", "Líder da Maioria", "Líder da Minoria", "Líder da Bancada Feminina",
    ]
    assert _cargos(lideres)["Líder do Governo"] == ("Teresa Leitão", "PT", "PE")


def test_lideres_da_camara_ignoram_vices_e_congresso():
    lideres = composicao.lideres(carregar("senado_liderancas.json"), "CD")
    cargos = _cargos(lideres)
    assert cargos["Líder do Governo"] == ("Paulo Pimenta", "PT", "RS")
    assert cargos["Líder da Minoria"] == ("Gustavo Gayer", "PL", "GO")  # não o 1º vice-líder
    assert all("Congresso" not in l["cargo"] for l in lideres)
    # Na Câmara, o id é o código do deputado na Câmara (o do perfil no site).
    assert next(l["id"] for l in lideres if l["nome"] == "Paulo Pimenta") == 74400  # e não 3726, o código no Senado


def test_presidente_da_camara_e_o_atual():
    presidente = composicao.presidente_da_camara(carregar("camara_mesa.json")["dados"])
    assert (presidente["nome"], presidente["id"], presidente["partido"]) == ("Hugo Motta", 160674, "REPUBLICANOS")


def test_presidente_do_senado():
    assert composicao.presidente_do_senado(carregar("senado_mesa.json")) == {
        "cargo": "Presidente", "id": 3830, "nome": "Davi Alcolumbre", "partido": "UNIÃO", "uf": "AP",
    }


def test_contar_sexo_guarda_so_totais():
    sexo = composicao.contar_sexo([("PL", False), ("PL", True), ("PT", True), ("PT", True), ("MDB", False)])
    assert sexo == {"mulheres": 3, "homens": 2, "mulheres_por_partido": {"PT": 2, "PL": 1}}


def test_resumo_do_senado(tmp_path):
    doc = coletar_senado(senado_falso(), tmp_path / "s.json", minimo=1)
    resumo = doc["resumo"]
    assert resumo["sexo"]["mulheres"] + resumo["sexo"]["homens"] == len(doc["senadores"])
    assert resumo["lideres"][0]["cargo"] == "Presidente"
    texto = (tmp_path / "s.json").read_text(encoding="utf-8")
    assert "Masculino" not in texto and "Feminino" not in texto  # nada de gênero por pessoa


def test_resumo_da_camara_tolera_falhas(tmp_path):
    def sem_contagem(request: httpx.Request) -> httpx.Response:
        if request.url.params.get("siglaSexo"):
            return httpx.Response(504)
        return responder_com_fixtures(request)

    avisos = []
    doc = coletar_camara(cliente_falso(sem_contagem), tmp_path / "d.json", senado=senado_falso(), avisar=avisos.append)
    assert doc["resumo"]["sexo"] is None
    assert [l["cargo"] for l in doc["resumo"]["lideres"]][:2] == ["Presidente", "Líder do Governo"]
    assert len(doc["deputados"]) == 4
    assert avisos


def test_resumo_da_camara(tmp_path):
    doc = coletar_camara(cliente_falso(), tmp_path / "d.json")
    assert doc["resumo"]["sexo"] == {"mulheres": 0, "homens": 4, "mulheres_por_partido": {}}
    # Sem cliente do Senado não há líderes, mas o presidente vem da própria Câmara.
    assert [l["cargo"] for l in doc["resumo"]["lideres"]] == ["Presidente"]

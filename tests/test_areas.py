import json
from types import SimpleNamespace

import pytest

from test_legislatura import docs  # noqa: F401  (fixture)
from test_resumos_ia import ClienteFalso
from monitor_politico import areas
from monitor_politico.build import construir


def resposta(classificacoes):
    return SimpleNamespace(
        stop_reason="end_turn", model="claude-sonnet-5-5",
        usage=SimpleNamespace(input_tokens=3000, output_tokens=500),
        content=[SimpleNamespace(type="text", text=json.dumps({"classificacoes": classificacoes}, ensure_ascii=False))],
    )


def prop(chave, ementa="Altera a lei.", **extra):
    return {"chave": chave, "tipo": "Projeto de Lei", "ementa": ementa, "votacoes": [{"id": 1}], **extra}


def test_lista_fechada_e_cada_assunto_numa_area_so():
    assert len(areas.ASSUNTOS) == len(set(areas.ASSUNTOS))
    assert len(areas.AREAS) == 9 and areas.OUTROS in areas.ROTINA["assuntos"]
    assert set(areas.ESQUEMA["properties"]["classificacoes"]["items"]["properties"]["assuntos"]["items"]["enum"]) == set(areas.ASSUNTOS)


def test_classificar_valida_a_resposta():
    cliente = ClienteFalso([resposta([
        {"chave": "PL 1/2024", "assuntos": ["Saúde inventada", "SUS e atendimento", "SUS e atendimento", "Drogas", "Mulheres", "Cultura"]},
        {"chave": "PL 9/2024", "assuntos": ["Drogas"]},  # não foi pedida
    ])])
    resultado, uso = areas.classificar(cliente, [prop("PL 1/2024", apelido="Lei da saúde")])
    assert resultado == {"PL 1/2024": ["SUS e atendimento", "Drogas", "Mulheres"]}
    assert uso == {"modelo": "claude-sonnet-5-5", "entrada": 3000, "saida": 500}
    pedido = cliente.pedidos[0]
    assert "Nome: Lei da saúde" in pedido["messages"][0]["content"] and pedido["output_config"]["effort"] == "low"


def test_atualizar_so_refaz_o_que_mudou_e_respeita_correcao_manual(tmp_path):
    saida = tmp_path / "areas.json"
    igual, manual, nova = prop("PL 1/2024"), prop("PL 2/2024"), prop("PL 3/2024")
    saida.write_text(json.dumps({"classificacoes": {
        "PL 1/2024": {"assuntos": ["Cultura"], "fonte_hash": areas.impressao_digital(igual)},
        "PL 2/2024": {"assuntos": ["Esporte"], "manual": True},
    }}), encoding="utf-8")
    cliente = ClienteFalso([resposta([{"chave": "PL 3/2024", "assuntos": ["Drogas"]}])])
    doc = areas.atualizar([igual, manual, nova], saida, cliente)
    assert len(cliente.pedidos) == 1 and "PL 3/2024" in cliente.pedidos[0]["messages"][0]["content"]
    assert "PL 1/2024" not in cliente.pedidos[0]["messages"][0]["content"]
    assert doc["classificacoes"]["PL 2/2024"]["assuntos"] == ["Esporte"]
    assert doc["classificacoes"]["PL 3/2024"]["assuntos"] == ["Drogas"]
    assert json.loads(saida.read_text(encoding="utf-8"))["versao"] == areas.VERSAO


def test_lote_com_erro_nao_derruba_os_outros(tmp_path):
    avisos = []
    cliente = ClienteFalso([RuntimeError("fora do ar"), resposta([{"chave": "PL 2/2024", "assuntos": ["Cultura"]}])])
    doc = areas.atualizar([prop("PL 1/2024"), prop("PL 2/2024")], tmp_path / "a.json", cliente, avisar=avisos.append, por_pedido=1)
    assert list(doc["classificacoes"]) == ["PL 2/2024"] and "fora do ar" in avisos[0]


def linha(sigla, lei=False):
    return {"sigla": sigla, "slug": sigla, "titulo": f"Título de {sigla}", "virou_lei": lei}


def test_paginas_separam_rotina_e_repetem_em_mais_de_uma_area():
    linhas = [linha("A", lei=True), linha("B"), linha("C"), linha("D")]
    classificacoes = {
        "A": {"assuntos": ["Reforma tributária", "SUS e atendimento"]},
        "B": {"assuntos": ["Acordos internacionais"]},
        "C": {"assuntos": ["Homenagens e datas", "Esporte"]},
    }
    v = areas.paginas(linhas, classificacoes)
    por = {a["slug"]: a for a in v["areas"]}
    assert [i["sigla"] for i in por["economia"]["itens"]] == ["A"] and [i["sigla"] for i in por["saude"]["itens"]] == ["A"]
    assert por["economia"]["leis"] == 1 and por["economia"]["filtros"] == [("Reforma tributária", 1)]
    assert [i["sigla"] for i in por["educacao"]["itens"]] == ["C"]
    # B só tem assunto de rotina; D ainda não foi classificada.
    assert [i["sigla"] for i in v["rotina"]["itens"]] == ["B", "D"] and v["rotina"]["itens"][1]["assuntos"] == [areas.OUTROS]
    assert v["classificadas"] == 3


def test_site_com_e_sem_areas(tmp_path, docs):  # noqa: F811
    construir(*docs, tmp_path / "sem")
    assert not (tmp_path / "sem" / "areas").exists()
    chaves = list(docs[2]["proposicoes"])
    construir(*docs, tmp_path / "com", areas={"classificacoes": {chaves[0]: {"assuntos": ["Drogas"]}}})
    site = tmp_path / "com"
    indice = (site / "areas" / "index.html").read_text(encoding="utf-8")
    assert indice.count('class="ar-card"') == 9 and 'href="rotina.html"' in indice and "IA" in indice
    seguranca = (site / "areas" / "seguranca.html").read_text(encoding="utf-8")
    assert seguranca.count("<li data-assuntos") == 1 and "static/areas.js" in seguranca
    assert 'href="areas/seguranca.html"' in (site / "index.html").read_text(encoding="utf-8")
    assert 'href="areas/index.html"' in (site / "votacoes.html").read_text(encoding="utf-8")
    assert 'id="areas"' in (site / "entenda.html").read_text(encoding="utf-8")

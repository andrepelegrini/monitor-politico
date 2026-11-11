import json
from types import SimpleNamespace

import httpx
import pytest

from monitor_politico import resumos_ia

PROP = {
    "chave": "PLP 186/2026",
    "tipo": "Projeto de Lei Complementar",
    "autores": ["Poder Executivo"],
    "ementa": "Altera a Lei Complementar nº 123 para dispor sobre o limite de receita bruta anual do MEI.",
    "url_inteiro_teor": "https://exemplo.leg.br/teor.pdf",
    "votacoes": [{"data_hora": "2026-10-14T19:42:50"}],
}
RESUMO = {
    "titulo": "Novo limite de faturamento do MEI",
    "o_que_muda": "Aumenta o limite de receita bruta anual para quem é MEI.",
    "quem_e_afetado": "Microempreendedores individuais.",
}


class ClienteFalso:
    """Imita client.beta.messages.create e guarda os pedidos."""

    def __init__(self, respostas):
        self.respostas = list(respostas)
        self.pedidos = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.pedidos.append(kwargs)
        resposta = self.respostas.pop(0)
        if isinstance(resposta, Exception):
            raise resposta
        return resposta


def resposta(dados=RESUMO, stop_reason="end_turn"):
    texto = dados if isinstance(dados, str) else json.dumps(dados, ensure_ascii=False)
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=texto)],
    )


def http_falso(status=200, tipo="application/pdf", corpo=b"%PDF-1.7 teste"):
    pedidos = []

    def handler(request):
        pedidos.append(str(request.url))
        return httpx.Response(status, headers={"content-type": tipo}, content=corpo)

    cliente = httpx.Client(transport=httpx.MockTransport(handler))
    cliente.pedidos = pedidos
    return cliente


def doc(*props):
    return {"proposicoes": {p["chave"]: p for p in props}}


def test_gera_resumo_com_o_pdf_e_guarda_a_fonte(tmp_path):
    cliente = ClienteFalso([resposta()])
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP), saida, cliente, http_falso(), avisar=pytest.fail)

    pedido = cliente.pedidos[0]
    assert pedido["model"] == "claude-opus-5-5"
    assert pedido["fallbacks"] == "default"
    assert pedido["output_config"]["format"]["schema"] == resumos_ia.ESQUEMA
    documento, texto = pedido["messages"][0]["content"]
    assert documento["type"] == "document" and documento["source"]["media_type"] == "application/pdf"
    assert "Ementa oficial" in texto["text"]

    guardado = json.loads(saida.read_text(encoding="utf-8"))["resumos"]["PLP 186/2026"]
    assert guardado["titulo"] == RESUMO["titulo"]
    assert guardado["fonte"] == "texto integral"
    assert guardado["fonte_hash"] == resumos_ia.impressao_digital(PROP)


def test_sem_pdf_resume_pela_ementa(tmp_path):
    cliente = ClienteFalso([resposta()])
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP), saida, cliente, http_falso(tipo="text/html"), avisar=pytest.fail)

    [conteudo] = cliente.pedidos[0]["messages"][0]["content"]
    assert conteudo["type"] == "text" and "não está disponível" in conteudo["text"]
    assert json.loads(saida.read_text(encoding="utf-8"))["resumos"]["PLP 186/2026"]["fonte"] == "ementa"


def test_nao_refaz_resumo_se_a_fonte_nao_mudou(tmp_path):
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP), saida, ClienteFalso([resposta()]), http_falso(), avisar=pytest.fail)

    sem_chamadas = ClienteFalso([])
    resumos_ia.atualizar(doc(PROP), saida, sem_chamadas, http_falso(), avisar=pytest.fail)
    assert sem_chamadas.pedidos == []

    mudou = ClienteFalso([resposta({**RESUMO, "titulo": "Outro título"})])
    resumos_ia.atualizar(doc({**PROP, "ementa": "Nova ementa."}), saida, mudou, http_falso(), avisar=pytest.fail)
    assert json.loads(saida.read_text(encoding="utf-8"))["resumos"]["PLP 186/2026"]["titulo"] == "Outro título"


@pytest.mark.parametrize("falha", [
    resposta(stop_reason="refusal"),
    resposta(stop_reason="max_tokens"),
    resposta("não é json"),
    resposta({**RESUMO, "o_que_muda": ""}),
    resposta({**RESUMO, "titulo": "x" * 200}),
    RuntimeError("erro da API"),
])
def test_falha_numa_proposicao_nao_derruba_as_outras(tmp_path, falha):
    outra = {**PROP, "chave": "PL 1/2026", "votacoes": []}
    cliente = ClienteFalso([falha, resposta()])  # a primeira (mais recente) falha
    avisos = []
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP, outra), saida, cliente, http_falso(), avisar=avisos.append)

    resumos = json.loads(saida.read_text(encoding="utf-8"))["resumos"]
    assert list(resumos) == ["PL 1/2026"]
    assert any("PLP 186/2026" in a for a in avisos)


def test_respeita_o_limite_por_execucao(tmp_path):
    props = [{**PROP, "chave": f"PL {i}/2026"} for i in range(3)]
    avisos = []
    cliente = ClienteFalso([resposta(), resposta()])
    resumos_ia.atualizar(doc(*props), tmp_path / "r.json", cliente, http_falso(), avisar=avisos.append, maximo=2)
    assert len(cliente.pedidos) == 2
    assert any("ficam para a próxima" in a for a in avisos)


def test_baixar_pdf_tenta_de_novo_em_erro_do_servidor(monkeypatch):
    monkeypatch.setattr(resumos_ia.time, "sleep", lambda _s: None)
    respostas = iter([httpx.Response(504), httpx.Response(200, headers={"content-type": "application/pdf"}, content=b"%PDF")])
    http = httpx.Client(transport=httpx.MockTransport(lambda _r: next(respostas)))
    assert resumos_ia.baixar_pdf("https://exemplo/teor", http) == b"%PDF"
    assert resumos_ia.baixar_pdf(None, http) is None


def test_texto_longo_perde_as_ultimas_frases_e_nao_o_resumo(tmp_path):
    longo = "Primeira frase curta. " + "Outra frase do resumo com algum detalhe. " * 30
    cliente = ClienteFalso([resposta({**RESUMO, "o_que_muda": longo})])
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP), saida, cliente, http_falso())
    guardado = json.loads(saida.read_text(encoding="utf-8"))["resumos"]["PLP 186/2026"]
    assert guardado["o_que_muda"].startswith("Primeira frase curta.")
    assert len(guardado["o_que_muda"]) <= resumos_ia.LIMITES["o_que_muda"] and guardado["o_que_muda"].endswith(".")


def test_mudar_a_instrucao_refaz_os_resumos(monkeypatch):
    antes = resumos_ia.impressao_digital(PROP)
    monkeypatch.setattr(resumos_ia, "VERSAO_INSTRUCOES", resumos_ia.VERSAO_INSTRUCOES + 1)
    assert resumos_ia.impressao_digital(PROP) != antes


class LeitorFalso:
    def __init__(self, paginas):
        self.pages = [SimpleNamespace(extract_text=lambda t=t: t) for t in paginas]


def test_pdf_com_texto_vai_como_texto_e_digitalizado_vai_inteiro(monkeypatch):
    import pypdf
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: LeitorFalso(["Art. 1º " + "texto " * 100, "Art. 2º " + "texto " * 100]))
    assert resumos_ia.texto_do_pdf(b"%PDF").startswith("Art. 1º")
    monkeypatch.setattr(pypdf, "PdfReader", lambda _: LeitorFalso(["", "  "]))
    assert resumos_ia.texto_do_pdf(b"%PDF") is None
    assert resumos_ia.texto_do_pdf(None) is None


def test_envia_o_texto_com_esforco_baixo_e_registra_o_consumo(tmp_path, monkeypatch):
    monkeypatch.setattr(resumos_ia, "texto_do_pdf", lambda pdf: "Art. 1º O limite passa a ser de R$ 110 mil.")
    com_uso = resposta()
    com_uso.usage = SimpleNamespace(input_tokens=4000, output_tokens=800)
    com_uso.model = "claude-opus-5-5"
    cliente = ClienteFalso([com_uso])
    saida = tmp_path / "resumos.json"
    resumos_ia.atualizar(doc(PROP), saida, cliente, http_falso())
    pedido = cliente.pedidos[0]
    blocos = pedido["messages"][0]["content"]
    assert [b["type"] for b in blocos] == ["text", "text"] and "<texto_oficial>" in blocos[0]["text"]
    assert pedido["output_config"]["effort"] == "low"
    guardado = json.loads(saida.read_text(encoding="utf-8"))["resumos"]["PLP 186/2026"]
    assert guardado["entrada"] == "texto"
    assert guardado["uso"] == {"modelo": "claude-opus-5-5", "entrada": 4000, "saida": 800}
    assert resumos_ia.custo(guardado["uso"]) == (4000 * 4 + 800 * 20) / 1_000_000


def test_haiku_vai_sem_a_reserva_do_servidor():
    cliente = ClienteFalso([resposta()])
    resumos_ia.gerar(cliente, PROP, None, None, modelo="claude-haiku-5-5")
    assert "fallbacks" not in cliente.pedidos[0] and "betas" not in cliente.pedidos[0]
    cliente = ClienteFalso([resposta()])
    resumos_ia.gerar(cliente, PROP, None, None, modelo="claude-sonnet-5-5")
    assert cliente.pedidos[0]["fallbacks"] == "default"


def test_comparar_roda_cada_modelo_e_nao_para_no_erro(monkeypatch):
    monkeypatch.setattr(resumos_ia, "texto_do_pdf", lambda pdf: None)
    cliente = ClienteFalso([resposta(), RuntimeError("falhou"), resposta()])
    linhas = resumos_ia.comparar(doc(PROP), cliente, http_falso(), chaves=("PLP 186/2026",))
    assert [l["modelo"] for l in linhas] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5"]
    assert "erro" in linhas[1] and linhas[2]["titulo"] == RESUMO["titulo"]

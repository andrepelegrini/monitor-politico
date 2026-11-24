from test_legislatura import docs  # noqa: F401  (fixture)
from monitor_politico import apoio
from monitor_politico.build import construir


def test_crc_e_codigo_do_qr():
    assert apoio._crc16("123456789") == "29B1"  # valor de referência do CRC-16/CCITT-FALSE
    # static/pix.svg foi gerado deste texto. Se o código mudar, gere o desenho de novo.
    assert apoio.codigo_pix() == "00020126580014br.gov.bcb.pix0136f71cf5e1-5b06-462d-a6cd-f925d7b6fd0f5204000053039865802BR5908CADENZIA6009SAO PAULO62070503***63046C31"


def test_pagina_apoie_e_links(tmp_path, docs):  # noqa: F811
    construir(*docs, tmp_path / "site")
    site = tmp_path / "site"
    pagina = (site / "apoie.html").read_text(encoding="utf-8")
    assert apoio.PIX_CHAVE in pagina and apoio.PIX_NOME in pagina and "static/pix.svg" in pagina
    assert (site / "static" / "pix.svg").exists()
    inicio = (site / "index.html").read_text(encoding="utf-8")
    assert inicio.count('href="./apoie.html"') == 2  # menu e rodapé
    assert "Apoio por Pix" in (site / "entenda.html").read_text(encoding="utf-8")

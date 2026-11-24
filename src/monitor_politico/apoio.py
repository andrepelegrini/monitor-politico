"""Página "Apoie": os dados do Pix e o código que o QR Code carrega (padrão BR Code, do Banco Central).

O desenho fica em static/pix.svg. Se a chave, o nome ou a cidade mudarem, gere o arquivo de novo com
`segno` (pip install segno) a partir de `codigo_pix()`; um teste confere o código esperado.
"""

from __future__ import annotations

PIX_CHAVE = "f71cf5e1-5b06-462d-a6cd-f925d7b6fd0f"  # chave aleatória ligada ao CNPJ; nunca usar CPF
PIX_NOME = "CADENZIA TECH"
PIX_CIDADE = "SAO PAULO"  # o padrão pede texto sem acento


def _campo(id_: str, valor: str) -> str:
    return f"{id_}{len(valor):02d}{valor}"


def _crc16(texto: str) -> str:
    """CRC-16/CCITT-FALSE, exigido no fim do código."""
    crc = 0xFFFF
    for byte in texto.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def codigo_pix(chave: str = PIX_CHAVE, nome: str = PIX_NOME, cidade: str = PIX_CIDADE) -> str:
    """Pix estático, sem valor definido: quem apoia escolhe quanto."""
    conta = _campo("00", "br.gov.bcb.pix") + _campo("01", chave)
    corpo = (
        _campo("00", "01") + _campo("26", conta) + _campo("52", "0000") + _campo("53", "986") + _campo("58", "BR")
        + _campo("59", nome) + _campo("60", cidade) + _campo("62", _campo("05", "***")) + "6304"
    )
    return corpo + _crc16(corpo)

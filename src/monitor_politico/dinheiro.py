"""Dinheiro público ligado a um mandato: cota parlamentar e emendas individuais.

Cota: o total de cada ano vem da página oficial do deputado, porque os arquivos abertos oscilam. Em
04/11/2026 eles traziam as passagens aéreas do SIGEPA até julho de 2025; em 05/11/2026, em nenhum ano.
Os arquivos dão o detalhe por categoria, fornecedor e comprovante, e a diferença para o total oficial
aparece na página como valor sem detalhamento.

Emendas: arquivos do Portal da Transparência (CGU). Pessoa física nunca aparece pelo nome: como nos
outros modelos, CPF, passageiro e trecho de viagem não chegam ao JSON.
"""

from __future__ import annotations

import csv
import html
import io
import re
import unicodedata
import zipfile
from collections import Counter
from typing import Any, Iterable, Iterator, Optional

import httpx

from monitor_politico.plenario import RelatorioInvalido

URL_COTA = "https://www.camara.leg.br/cotas/Ano-{ano}.csv.zip"
URL_PAGINA_DEPUTADO = "https://www.camara.leg.br/deputados/{id}?ano={ano}"
URL_EMENDAS = "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/emendas-parlamentares/EmendasParlamentares.zip"
ARQUIVO_EMENDAS = "EmendasParlamentares.csv"
ARQUIVO_FAVORECIDOS = "EmendasParlamentares_PorFavorecido.csv"
PESSOA_FISICA = "Pessoa física (nome não exibido)"
TAMANHO_CNPJ = 14
TAMANHO_CPF = 11
TOLERANCIA_ARREDONDAMENTO = 1.0  # A Câmara arredonda os meses: centavos de diferença não são "sem detalhamento".

CATEGORIAS = {
    "DIVULGAÇÃO DA ATIVIDADE PARLAMENTAR.": "Divulgação da atividade parlamentar",
    "MANUTENÇÃO DE ESCRITÓRIO DE APOIO À ATIVIDADE PARLAMENTAR": "Escritório de apoio",
    "PASSAGEM AÉREA - SIGEPA": "Passagens aéreas",
    "PASSAGEM AÉREA - RPA": "Passagens aéreas",
    "PASSAGEM AÉREA - REEMBOLSO": "Passagens aéreas",
    "PASSAGEM AÉREA - MISSÃO OFICIAL": "Passagens aéreas",
    "PASSAGENS TERRESTRES, MARÍTIMAS OU FLUVIAIS": "Passagens terrestres e fluviais",
    "COMBUSTÍVEIS E LUBRIFICANTES.": "Combustíveis",
    "LOCAÇÃO OU FRETAMENTO DE VEÍCULOS AUTOMOTORES": "Locação de veículos",
    "SERVIÇO DE TÁXI, PEDÁGIO E ESTACIONAMENTO": "Táxi, pedágio e estacionamento",
    "HOSPEDAGEM ,EXCETO DO PARLAMENTAR NO DISTRITO FEDERAL.": "Hospedagem",
    "TELEFONIA": "Telefonia",
    "CONSULTORIAS, PESQUISAS E TRABALHOS TÉCNICOS.": "Consultorias e pesquisas",
    "ASSINATURA DE PUBLICAÇÕES": "Assinatura de publicações",
    "FORNECIMENTO DE ALIMENTAÇÃO DO PARLAMENTAR": "Alimentação",
}
ETAPAS_EMENDA = {
    "empenhado": "Valor Empenhado",
    "liquidado": "Valor Liquidado",
    "pago": "Valor Pago",
    "restos_pagos": "Valor Restos A Pagar Pagos",
}
MINUSCULAS = {"de", "do", "da", "dos", "das", "e"}
FUNCOES = {"Múltiplo": "Várias áreas"}


def _ponto(texto: Optional[str]) -> float:
    return float((texto or "0").replace(",", "."))


def _virgula(texto: Optional[str]) -> float:
    return float((texto or "0").replace(".", "").replace(",", "."))


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode().upper().strip()


def ler_cota_da_pagina(pagina: str) -> dict[str, float]:
    """Total gasto, percentual usado e valor não utilizado no ano, como a Câmara publica."""
    sem_scripts = re.sub(r"<script.*?</script>|<style.*?</style>", "", pagina, flags=re.S)
    texto = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", sem_scripts)))
    achado = re.search(r"Cota parlamentar.*?Percentual Gasto ([\d.,]+) ([\d.,]+)% Não utilizado ([\d.,]+)", texto)
    if achado is None:
        raise RelatorioInvalido("página do deputado sem o quadro da cota")
    return {"total": _virgula(achado[1]), "percentual": float(achado[2].replace(",", ".")), "nao_utilizado": _virgula(achado[3])}


def fornecedor_publico(nome: str, documento: str) -> tuple[str, Optional[str]]:
    """Nome a exibir e chave de agrupamento. Pessoa física fica sem nome e sem documento."""
    digitos = re.sub(r"\D", "", documento or "")
    if len(digitos) == TAMANHO_CPF:
        return PESSOA_FISICA, None
    return nome.strip(), digitos if len(digitos) == TAMANHO_CNPJ else None


def cota_do_mandato(fonte: Any, id_: int, legislatura: int, anos: Iterable[int]) -> dict[str, Any]:
    categorias: Counter[str] = Counter()
    fornecedores: Counter[str] = Counter()
    nomes: dict[str, str] = {}
    comprovantes = []
    por_ano = []
    for ano in anos:
        detalhado = 0.0
        for linha in fonte.cota(ano):
            if linha["ideCadastro"] != str(id_) or linha["codLegislatura"] != str(legislatura):
                continue
            valor = _ponto(linha["vlrLiquido"])
            categoria = CATEGORIAS.get(linha["txtDescricao"], linha["txtDescricao"].capitalize().rstrip("."))
            nome, chave = fornecedor_publico(linha["txtFornecedor"], linha["txtCNPJCPF"])
            categorias[categoria] += valor
            detalhado += valor
            if chave:
                fornecedores[chave] += valor
                nomes[chave] = nome
            comprovantes.append({
                "mes": f"{linha['numAno']}-{int(linha['numMes']):02d}",
                "categoria": categoria,
                "fornecedor": nome,
                "valor": round(valor, 2),
                "url": linha["urlDocumento"] or None,
            })
        por_ano.append({"ano": ano, **fonte.cota_oficial(id_, ano), "detalhado": round(detalhado, 2)})
    comprovantes.sort(key=lambda c: (-c["valor"], c["mes"]))
    # Primeiro por CNPJ, porque o mesmo CNPJ vem com grafias diferentes; depois pelo nome, porque uma
    # empresa individual pode ter mais de um CNPJ.
    por_nome: Counter[str] = Counter()
    nome_exibido: dict[str, str] = {}
    for chave, valor in fornecedores.items():
        normalizado = _sem_acento(nomes[chave])
        por_nome[normalizado] += valor
        nome_exibido[normalizado] = nomes[chave]
    return {
        "por_ano": por_ano,
        "categorias": [[nome, round(valor, 2)] for nome, valor in categorias.most_common()],
        "fornecedores": [[nome_exibido[chave], round(valor, 2)] for chave, valor in por_nome.most_common(10)],
        "total_fornecedores": len(por_nome),
        "comprovantes": comprovantes,
    }


def nome_de_autor(nome: str) -> str:
    return _sem_acento(nome)


def emendas_do_mandato(linhas: Iterable[dict[str, str]], favorecidos: Iterable[dict[str, str]], autor: str, ano_inicial: int) -> dict[str, Any]:
    alvo = nome_de_autor(autor)
    por_ano: dict[str, Counter[str]] = {}
    funcoes: Counter[str] = Counter()
    tipos: Counter[str] = Counter()
    destinos: Counter[str] = Counter()
    for linha in linhas:
        ano = linha["Ano da Emenda"]
        if nome_de_autor(linha["Nome do Autor da Emenda"]) != alvo or int(ano) < ano_inicial:
            continue
        etapas = por_ano.setdefault(ano, Counter())
        for chave, coluna in ETAPAS_EMENDA.items():
            etapas[chave] += _virgula(linha[coluna])
        pago = _virgula(linha["Valor Pago"]) + _virgula(linha["Valor Restos A Pagar Pagos"])
        funcoes[FUNCOES.get(linha["Nome Função"], linha["Nome Função"])] += pago
        tipos[linha["Tipo de Emenda"].replace("Emenda Individual - ", "")] += pago
        destinos[_destino(linha)] += pago

    recebido: Counter[str] = Counter()
    dados: dict[str, dict[str, str]] = {}
    for linha in favorecidos:
        if nome_de_autor(linha["Nome do Autor da Emenda"]) != alvo or int(linha["Código da Emenda"][:4]) < ano_inicial:
            continue
        pessoa_fisica = "Jur" not in linha["Tipo Favorecido"]
        chave = PESSOA_FISICA if pessoa_fisica else linha["Código do Favorecido"]
        recebido[chave] += _virgula(linha["Valor Recebido"])
        dados[chave] = {
            "nome": PESSOA_FISICA if pessoa_fisica else linha["Favorecido"],
            "municipio": "" if pessoa_fisica else linha["Município Favorecido"],
            "uf": "" if pessoa_fisica else linha["UF Favorecido"],
        }
    return {
        "por_ano": [{"ano": int(ano), **{c: round(v, 2) for c, v in por_ano[ano].items()}} for ano in sorted(por_ano)],
        "funcoes": [[nome, round(valor, 2)] for nome, valor in funcoes.most_common() if valor > 0],
        "tipos": [[nome, round(valor, 2)] for nome, valor in tipos.most_common() if valor > 0],
        "destinos": [[nome, round(valor, 2)] for nome, valor in destinos.most_common() if valor > 0],
        "favorecidos": [{**dados[chave], "valor": round(valor, 2)} for chave, valor in recebido.most_common(10)],
        "total_favorecidos": len(recebido),
        "total_recebido": round(sum(recebido.values()), 2),
    }


def _titulo(texto: str) -> str:
    return " ".join(p.lower() if p.lower() in MINUSCULAS else p.capitalize() for p in texto.split())


def _destino(linha: dict[str, str]) -> str:
    """A CGU informa o local em formatos diferentes: "Nacional", "SÃO PAULO (UF)", "MÚLTIPLO" ou "SÃO VICENTE - SP"."""
    localidade, uf = linha["Localidade de aplicação do recurso"], linha["UF"]
    if localidade.endswith("(UF)"):
        return f"{_titulo(localidade[:-4])}, sem município indicado"
    if localidade == "MÚLTIPLO":
        return "Vários estados" if uf in ("Múltiplo", "Sem informação") else f"Vários municípios ({_titulo(uf)})"
    municipio, separador, sigla = localidade.rpartition(" - ")
    return f"{_titulo(municipio)}-{sigla}" if separador else _titulo(localidade)


class FonteDinheiro:
    def __init__(self, http: Optional[httpx.Client] = None) -> None:
        self.http = http or httpx.Client(timeout=300, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (monitor-politico)"})
        self._emendas: Optional[zipfile.ZipFile] = None

    def cota(self, ano: int) -> Iterator[dict[str, str]]:
        arquivo = zipfile.ZipFile(io.BytesIO(self.http.get(URL_COTA.format(ano=ano)).raise_for_status().content))
        with arquivo.open(arquivo.namelist()[0]) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="utf-8-sig", newline=""), delimiter=";")

    def cota_oficial(self, id_: int, ano: int) -> dict[str, float]:
        return ler_cota_da_pagina(self.http.get(URL_PAGINA_DEPUTADO.format(id=id_, ano=ano)).raise_for_status().text)

    def _zip_emendas(self) -> zipfile.ZipFile:
        if self._emendas is None:
            self._emendas = zipfile.ZipFile(io.BytesIO(self.http.get(URL_EMENDAS).raise_for_status().content))
        return self._emendas

    def _linhas_emendas(self, nome: str) -> Iterator[dict[str, str]]:
        with self._zip_emendas().open(nome) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")

    def emendas(self) -> Iterator[dict[str, str]]:
        return self._linhas_emendas(ARQUIVO_EMENDAS)

    def favorecidos(self) -> Iterator[dict[str, str]]:
        return self._linhas_emendas(ARQUIVO_FAVORECIDOS)

    def data_das_emendas(self) -> str:
        ano, mes, dia, *_ = self._zip_emendas().getinfo(ARQUIVO_EMENDAS).date_time
        return f"{ano:04d}-{mes:02d}-{dia:02d}"


def coletar(fonte: Any, id_: int, nome: str, legislatura: int, ano_inicial: int, ano_final: int) -> dict[str, Any]:
    return {
        "cota": cota_do_mandato(fonte, id_, legislatura, range(ano_inicial, ano_final + 1)),
        "emendas": {**emendas_do_mandato(fonte.emendas(), fonte.favorecidos(), nome, ano_inicial), "arquivo_em": fonte.data_das_emendas()},
    }


# --- O que a página mostra


def _com_largura(itens: Iterable[list[Any]]) -> list[dict[str, Any]]:
    itens = list(itens)
    maior = max((v for _, v in itens), default=0) or 1
    return [{"nome": nome, "valor": valor, "largura": round(max(valor, 0) / maior * 100, 1)} for nome, valor in itens]


def visao(doc: dict[str, Any]) -> dict[str, Any]:
    cota, emendas = doc["cota"], doc["emendas"]
    por_ano = []
    for ano in cota["por_ano"]:
        falta = round(ano["total"] - ano["detalhado"], 2)
        por_ano.append({**ano, "sem_detalhe": falta if falta > TOLERANCIA_ARREDONDAMENTO else 0})
    total = round(sum(a["total"] for a in por_ano), 2)
    sem_detalhe = round(sum(a["sem_detalhe"] for a in por_ano), 2)
    categorias = list(cota["categorias"])
    if sem_detalhe:
        categorias = sorted(categorias + [["Sem detalhamento nos arquivos abertos", sem_detalhe]], key=lambda c: -c[1])
    totais_emendas = {c: round(sum(a.get(c, 0) for a in emendas["por_ano"]), 2) for c in ETAPAS_EMENDA}
    return {
        "cota": {
            "total": total,
            "por_ano": por_ano,
            "detalhado": round(sum(a["detalhado"] for a in por_ano), 2),
            "sem_detalhe": sem_detalhe,
            "categorias": _com_largura(categorias),
            "fornecedores": cota["fornecedores"],
            "total_fornecedores": cota["total_fornecedores"],
            "total_comprovantes": len(cota["comprovantes"]),
            "maiores_comprovantes": cota["comprovantes"][:10],
            "opcoes_categorias": sorted({c["categoria"] for c in cota["comprovantes"]}),
        },
        "emendas": {
            **emendas,
            "totais": totais_emendas,
            "pago_total": round(totais_emendas["pago"] + totais_emendas["restos_pagos"], 2),
            "destinos": _com_largura(emendas["destinos"][:6]),
            "funcoes": _com_largura(emendas["funcoes"][:6]),
            "ano_inicial": emendas["por_ano"][0]["ano"] if emendas["por_ano"] else None,
        },
    }

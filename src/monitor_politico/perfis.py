"""Coleta do perfil ampliado de parlamentar: eleições, bens, trajetória e comissões.

Piloto: só os IDs de PILOTO têm perfil ampliado até o rollout ser autorizado. A coleta é manual e
fica fora do robô diário, porque os arquivos do TSE são grandes e mudam pouco.

O CPF liga os registros da Câmara aos do TSE. Ele é usado só em memória: como nos outros modelos,
apenas os campos declarados aqui chegam ao JSON. A descrição livre de cada bem não é guardada.

Uso: python -m monitor_politico.perfis [pasta_saida]
"""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional
from zoneinfo import ZoneInfo

import httpx

from monitor_politico import dinheiro, plenario, propostas
from monitor_politico.camara import ClienteCamara

PILOTO = (204534,)  # Tabata Amaral
ELEICOES = (2018, 2022, 2026)
SAIDA_PADRAO = Path("data/perfis")
CARGO_DEPUTADO = "DEPUTADO FEDERAL"
MUNICIPIOS_GUARDADOS = 8
FUSO = ZoneInfo("America/Sao_Paulo")

URL_TSE = "https://cdn.tse.jus.br/estatistica/sead/odsele"
URL_CANDIDATOS = URL_TSE + "/consulta_cand/consulta_cand_{ano}.zip"
URL_BENS = URL_TSE + "/bem_candidato/bem_candidato_{ano}.zip"
URL_VOTACAO = URL_TSE + "/votacao_candidato_munzona/votacao_candidato_munzona_{ano}.zip"

Linhas = Iterable[dict[str, str]]


# --- Regras sobre as linhas dos arquivos


def candidatura(linhas: Linhas, cpf: str, cargo: str = CARGO_DEPUTADO) -> Optional[dict[str, str]]:
    """Registro da pessoa na eleição, só com os campos públicos que o site usa."""
    for linha in linhas:
        if linha["NR_CPF_CANDIDATO"] == cpf and linha["DS_CARGO"].upper() == cargo:
            return {
                "sq": linha["SQ_CANDIDATO"],
                "partido": linha["SG_PARTIDO"],
                "uf": linha["SG_UF"],
                "situacao": linha["DS_SIT_TOT_TURNO"],
            }
    return None


def _valor(texto: str) -> float:
    return float(texto.replace(",", "."))


def bens_declarados(linhas: Linhas, sq: str) -> dict[str, Any]:
    """Total e valor por tipo de bem. A descrição livre fica de fora por poder trazer dados pessoais."""
    categorias: Counter[str] = Counter()
    for linha in linhas:
        if linha["SQ_CANDIDATO"] == sq:
            categorias[linha["DS_TIPO_BEM_CANDIDATO"]] += _valor(linha["VR_BEM_CANDIDATO"])
    return {
        "total": round(sum(categorias.values()), 2),
        "categorias": [[tipo, round(valor, 2)] for tipo, valor in categorias.most_common()],
    }


def votacao(linhas: Linhas, sq: str) -> dict[str, Any]:
    por_municipio: Counter[str] = Counter()
    for linha in linhas:
        if linha["SQ_CANDIDATO"] == sq:
            por_municipio[linha["NM_MUNICIPIO"]] += int(linha["QT_VOTOS_NOMINAIS_VALIDOS"])
    return {
        "votos": sum(por_municipio.values()),
        "total_municipios": len(por_municipio),
        "municipios": [[nome, votos] for nome, votos in por_municipio.most_common(MUNICIPIOS_GUARDADOS)],
    }


def trajetoria(historico: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Posses, saídas e trocas de partido, sem as linhas técnicas do histórico da Câmara."""
    eventos = []
    partido_anterior = None
    for item in sorted(historico, key=lambda i: i["dataHora"]):
        descricao = item.get("descricaoStatus") or ""
        partido = item["siglaPartido"]
        evento = {"data": item["dataHora"][:10], "legislatura": item["idLegislatura"], "partido": partido, "uf": item.get("siglaUf")}
        if descricao.startswith("Entrada") and "Posse" in descricao:
            eventos.append({**evento, "tipo": "posse"})
        elif descricao.startswith("Alteração de partido") and partido_anterior:
            eventos.append({**evento, "tipo": "partido", "partido_anterior": partido_anterior})
        elif descricao.startswith("Saída") and "Término da Legislatura" not in descricao:
            eventos.append({**evento, "tipo": "saida", "descricao": descricao.split(" - ", 1)[-1]})
        partido_anterior = partido
    return eventos


def comissoes_atuais(orgaos: list[dict[str, Any]], hoje: date) -> list[dict[str, str]]:
    atuais = []
    for orgao in orgaos:
        fim = orgao.get("dataFim")
        if fim and fim[:10] < hoje.isoformat():
            continue
        nome = orgao.get("nomePublicacao") or orgao["nomeOrgao"]
        atuais.append({"sigla": orgao["siglaOrgao"], "nome": nome_proprio(nome) if nome.isupper() else nome, "funcao": orgao["titulo"]})
    # Funções de direção primeiro; depois titular e suplente, como no regimento.
    ordem = {"Titular": 1, "Suplente": 2}
    return sorted(atuais, key=lambda o: (ordem.get(o["funcao"], 0), o["nome"]))


# --- Acesso aos arquivos do TSE


class ArquivoRemoto:
    """Leitura de um arquivo remoto por trechos: o zip de votação tem centenas de MB e só um estado interessa."""

    TAMANHO_BLOCO = 8 << 20
    BLOCOS_EM_MEMORIA = 8

    def __init__(self, url: str, http: httpx.Client) -> None:
        self.url, self.http, self.posicao = url, http, 0
        self.tamanho = int(http.head(url).raise_for_status().headers["Content-Length"])
        self.blocos: dict[int, bytes] = {}

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.posicao

    def seek(self, deslocamento: int, origem: int = 0) -> int:
        self.posicao = {0: deslocamento, 1: self.posicao + deslocamento, 2: self.tamanho + deslocamento}[origem]
        return self.posicao

    def _bloco(self, indice: int) -> bytes:
        if indice not in self.blocos:
            if len(self.blocos) >= self.BLOCOS_EM_MEMORIA:
                self.blocos.pop(next(iter(self.blocos)))
            inicio = indice * self.TAMANHO_BLOCO
            fim = min(inicio + self.TAMANHO_BLOCO, self.tamanho) - 1
            self.blocos[indice] = self.http.get(self.url, headers={"Range": f"bytes={inicio}-{fim}"}).raise_for_status().content
        return self.blocos[indice]

    def read(self, quantidade: int = -1) -> bytes:
        restante = self.tamanho - self.posicao if quantidade is None or quantidade < 0 else min(quantidade, self.tamanho - self.posicao)
        partes = []
        while restante > 0:
            indice, inicio = divmod(self.posicao, self.TAMANHO_BLOCO)
            parte = self._bloco(indice)[inicio : inicio + restante]
            partes.append(parte)
            self.posicao += len(parte)
            restante -= len(parte)
        return b"".join(partes)


class FonteTSE:
    def __init__(self, http: Optional[httpx.Client] = None) -> None:
        self.http = http or httpx.Client(timeout=180, follow_redirects=True)

    def _linhas(self, url: str, sufixo: str) -> Iterator[dict[str, str]]:
        arquivo = zipfile.ZipFile(ArquivoRemoto(url, self.http))  # type: ignore[arg-type]
        nome = next(n for n in arquivo.namelist() if n.endswith(sufixo))
        with arquivo.open(nome) as bruto:
            yield from csv.DictReader(io.TextIOWrapper(bruto, encoding="latin-1", newline=""), delimiter=";")

    def candidatos(self, ano: int) -> Linhas:
        return self._linhas(URL_CANDIDATOS.format(ano=ano), "_BRASIL.csv")

    def bens(self, ano: int) -> Linhas:
        return self._linhas(URL_BENS.format(ano=ano), "_BRASIL.csv")

    def votacao(self, ano: int, uf: str) -> Linhas:
        return self._linhas(URL_VOTACAO.format(ano=ano), f"_{uf}.csv")


# --- Coleta


def eleicoes_da_pessoa(fonte: Any, cpf: str, anos: Iterable[int] = ELEICOES) -> list[dict[str, Any]]:
    resultado = []
    for ano in anos:
        registro = candidatura(fonte.candidatos(ano), cpf)
        if registro is None:
            continue
        sq = registro.pop("sq")
        resultado.append({
            "ano": ano,
            **registro,
            **votacao(fonte.votacao(ano, registro["uf"]), sq),
            "bens": bens_declarados(fonte.bens(ano), sq),
        })
    return resultado


def coletar_perfil(
    id_: int, camara: ClienteCamara, fonte: Any, hoje: Optional[date] = None, arquivos: Any = None, financas: Any = None
) -> dict[str, Any]:
    hoje = hoje or date.today()
    detalhe = camara._get(f"/deputados/{id_}")["dados"]
    eventos = trajetoria(camara._get(f"/deputados/{id_}/historico")["dados"])
    orgaos = list(camara._paginar(f"/deputados/{id_}/orgaos", {"itens": 100, "ordem": "DESC", "ordenarPor": "dataInicio"}))
    legislatura = None
    posses = [e for e in eventos if e["tipo"] == "posse"]
    if posses:
        dados = camara._get(f"/legislaturas/{posses[-1]['legislatura']}")["dados"]
        dados = dados[0] if isinstance(dados, list) else dados
        legislatura = {"id": dados["id"], "inicio": dados["dataInicio"][:10], "fim": dados["dataFim"][:10]}
    return {
        "id": id_,
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legislatura_atual": legislatura,
        "eleicoes": eleicoes_da_pessoa(fonte, detalhe["cpf"]),
        "trajetoria": eventos,
        "comissoes": comissoes_atuais(orgaos, hoje),
        "plenario": plenario.coletar(arquivos, id_, legislatura["inicio"], hoje) if arquivos and legislatura else None,
        # Desde a primeira posse: muitas leis de um mandato vêm de propostas apresentadas no anterior.
        "propostas": propostas.coletar(arquivos, camara, id_, posses[0]["data"], hoje) if arquivos and posses else None,
        "dinheiro": (
            dinheiro.coletar(financas, id_, detalhe["ultimoStatus"]["nomeEleitoral"], legislatura["id"], int(legislatura["inicio"][:4]), hoje.year)
            if financas and legislatura else None
        ),
    }


def ler_perfis(pasta: Path) -> dict[int, dict[str, Any]]:
    if not pasta.is_dir():
        return {}
    documentos = (json.loads(c.read_text(encoding="utf-8")) for c in sorted(pasta.glob("*.json")))
    return {d["id"]: d for d in documentos}


# --- O que a página mostra

RESULTADOS = {
    "ELEITO": "Eleição direta",
    "ELEITO POR QP": "Por quociente partidário",
    "ELEITO POR MÉDIA": "Por média",
    "SUPLENTE": "Suplência",
    "NÃO ELEITO": "Sem vaga",
}


def foi_eleito(eleicao: dict[str, Any]) -> bool:
    return eleicao["situacao"].startswith("ELEITO")


def variacoes_de_bens(eleicoes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Variação entre eleições seguidas, da mais recente para a mais antiga. Sem base positiva, não há percentual."""
    com_bens = sorted((e for e in eleicoes if e["bens"]["categorias"]), key=lambda e: e["ano"])
    pares = []
    for antes, depois in zip(com_bens, com_bens[1:]):
        base, atual = antes["bens"]["total"], depois["bens"]["total"]
        pares.append({
            "de": antes["ano"],
            "para": depois["ano"],
            "diferenca": round(atual - base, 2),
            "percentual": round((atual - base) / base * 100, 1) if base > 0 else None,
        })
    return list(reversed(pares))


def linha_do_tempo(doc: dict[str, Any], hoje: date) -> list[dict[str, Any]]:
    """Trajetória da mais recente para a mais antiga, com os votos da eleição que levou a cada posse."""
    por_ano = {e["ano"]: e for e in doc["eleicoes"]}
    itens: list[dict[str, Any]] = []
    for evento in doc["trajetoria"]:
        item = {"data": evento["data"], "futuro": False, "detalhe": ""}
        if evento["tipo"] == "posse":
            item["titulo"] = f"Posse na {evento['legislatura']}ª legislatura"
            eleicao = por_ano.get(int(evento["data"][:4]) - 1)
            item["detalhe"] = f"{evento['partido']}-{evento['uf']}"
            if eleicao:
                item["votos"], item["ano_eleicao"] = eleicao["votos"], eleicao["ano"]
        elif evento["tipo"] == "partido":
            item["titulo"] = "Mudança de partido"
            item["detalhe"] = f"Do {evento['partido_anterior']} para o {evento['partido']}."
        else:
            item["titulo"] = "Saída"
            item["detalhe"] = evento["descricao"]
        itens.append(item)
    proxima = proximo_mandato(doc, hoje)
    if proxima:
        itens.append({
            "data": proxima["inicio"], "futuro": True, "titulo": "Início do novo mandato",
            "detalhe": f"Data prevista. {proxima['partido']}-{proxima['uf']}",
            "votos": proxima["votos"], "ano_eleicao": proxima["ano"],
        })
    return sorted(itens, key=lambda i: i["data"], reverse=True)


def proximo_mandato(doc: dict[str, Any], hoje: date) -> Optional[dict[str, Any]]:
    """Mandato ainda não iniciado que veio da eleição mais recente, se houver vitória nas urnas."""
    if not doc["eleicoes"]:
        return None
    ultima = max(doc["eleicoes"], key=lambda e: e["ano"])
    inicio = date(ultima["ano"] + 1, 2, 1)
    if not foi_eleito(ultima) or inicio <= hoje:
        return None
    return {**ultima, "inicio": inicio.isoformat(), "fim_ano": ultima["ano"] + 5, "inicio_ano": ultima["ano"] + 1}


def mandatos_da_trajetoria(doc: dict[str, Any]) -> list[dict[str, str]]:
    """Mandatos pelas posses, do mais antigo para o mais recente. Cada um vai até o início do seguinte."""
    posses = [e for e in doc["trajetoria"] if e["tipo"] == "posse"]
    return [{"inicio": e["data"], "rotulo": f"{e['data'][:4]}–{int(e['data'][:4]) + 4}"} for e in posses]


def visao(doc: dict[str, Any], hoje: Optional[date] = None, slugs: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """Dados já prontos para o template."""
    coleta_local = datetime.fromisoformat(doc["coletado_em"]).astimezone(FUSO).date()
    hoje = hoje or coleta_local
    eleicoes = sorted(doc["eleicoes"], key=lambda e: e["ano"], reverse=True)
    com_bens = [e for e in eleicoes if e["bens"]["categorias"]]
    maior_bem = max((e["bens"]["total"] for e in com_bens), default=0) or 1
    recente = eleicoes[0] if eleicoes else None
    return {
        **doc,
        "coleta_local": coleta_local.isoformat(),
        "eleicoes": [{**e, "resultado": RESULTADOS.get(e["situacao"], e["situacao"].capitalize())} for e in eleicoes],
        "eleicao_recente": recente,
        "maior_voto_municipio": recente["municipios"][0][1] if recente and recente["municipios"] else 1,
        "com_bens": [{**e, "largura": round(e["bens"]["total"] / maior_bem * 100, 1)} for e in sorted(com_bens, key=lambda e: e["ano"])],
        "variacoes": variacoes_de_bens(eleicoes),
        "linha_do_tempo": linha_do_tempo(doc, hoje),
        "proximo_mandato": proximo_mandato(doc, hoje),
        "plenario": plenario.visao(doc["plenario"], slugs) if doc.get("plenario") else None,
        "dinheiro": dinheiro.visao(doc["dinheiro"]) if doc.get("dinheiro") else None,
        "propostas": propostas.visao(doc["propostas"], slugs, mandatos_da_trajetoria(doc)) if doc.get("propostas") else None,
    }


def numero(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def moeda(valor: float) -> str:
    return "R$ " + f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def milhoes(valor: float) -> str:
    """Valor resumido para títulos: "R$ 1,96 milhão", "R$ 109,11 milhões", "R$ 850 mil". Sem quebra de linha no meio."""
    if abs(valor) < 1_000_000:
        return f"R$\u00a0{valor / 1000:,.0f}\u00a0mil".replace(",", ".")
    em_milhoes = valor / 1_000_000
    return "R$\u00a0" + f"{em_milhoes:.2f}".replace(".", ",") + ("\u00a0milhão" if abs(em_milhoes) < 2 else "\u00a0milhões")


def percentual(valor: float) -> str:
    sinal = "+" if valor >= 0 else "−"
    return sinal + f"{abs(valor):.1f}".replace(".", ",") + "%"


def diferenca(valor: float) -> str:
    return ("+" if valor >= 0 else "−") + moeda(abs(valor))


def nome_proprio(texto: str) -> str:
    return " ".join(p.capitalize() if p.lower() not in {"de", "do", "da", "dos", "das", "e"} else p.lower() for p in texto.split())


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    destino.mkdir(parents=True, exist_ok=True)
    camara, tse, arquivos_camara, financas_camara = ClienteCamara(), FonteTSE(), plenario.ArquivosCamara(), dinheiro.FonteDinheiro()
    for id_parlamentar in PILOTO:
        perfil = coletar_perfil(id_parlamentar, camara, tse, arquivos=arquivos_camara, financas=financas_camara)
        (destino / f"{id_parlamentar}.json").write_text(json.dumps(perfil, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Perfil {id_parlamentar}: {len(perfil['eleicoes'])} eleições, {len(perfil['comissoes'])} comissões")

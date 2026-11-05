"""Virada de legislatura: situação eleitoral de cada deputado em 2026 e quem chega em 2027.

Liga a Câmara ao TSE pelo CPF, que fica só em memória. Gera dois arquivos:
- data/legislatura.json: o badge de quem exerceu mandato na legislatura atual e os eleitos que ainda
  não exercem mandato nela, com a página própria até a posse.
- data/arquivo_deputados.json: quem exerceu mandato na legislatura atual e não está mais em exercício.
  Depois da primeira carga, a coleta diária mantém esse arquivo (veja camara.arquivar_saidas).

A coleta é manual, porque o resultado da eleição não muda. Uso: python -m monitor_politico.legislatura
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

import httpx

from monitor_politico.camara import ARQUIVO_PADRAO, ClienteCamara
from monitor_politico.models import Deputado
from monitor_politico.perfis import CARGO_DEPUTADO, FonteTSE, bens_declarados

LEGISLATURA_ATUAL = 57
ANO_DA_ELEICAO = 2026
POSSE = "2027-02-01"
URL_DEPUTADOS = "https://dadosabertos.camara.leg.br/arquivos/deputados/csv/deputados.csv"
SAIDA_PADRAO = Path("data/legislatura.json")
MUNICIPIOS_GUARDADOS = 6
PALAVRAS_VAZIAS = {"DE", "DA", "DO", "DOS", "DAS", "E"}

ELEITO = {"ELEITO", "ELEITO POR QP", "ELEITO POR MÉDIA"}
NOMES_DOS_CARGOS = {
    "SENADOR": "o Senado",
    "1º SUPLENTE": "a suplência do Senado",
    "2º SUPLENTE": "a suplência do Senado",
    "GOVERNADOR": "o governo do estado",
    "VICE-GOVERNADOR": "o governo do estado, como vice",
    "PRESIDENTE": "a Presidência da República",
    "VICE-PRESIDENTE": "a Presidência da República, como vice",
    "DEPUTADO ESTADUAL": "a assembleia estadual",
    "DEPUTADO DISTRITAL": "a Câmara Legislativa do DF",
}
ROTULOS = {
    "reeleicao": "Reeleição",
    "retorno": "Retorno à Câmara",
    "primeiro": "Primeiro mandato",
    "suplencia": "Suplência",
    "nao_reeleito": "Não se reelegeu",
    "outro_eleito": "Eleição para outro cargo",
    "outro_disputou": "Disputou outro cargo",
    "sem_candidatura": "Sem candidatura em 2026",
    "sem_resultado": "Candidatura sem resultado",
    "falecimento": "Falecimento",
}
CHEGAM = ("reeleicao", "retorno", "primeiro")
SAEM = ("suplencia", "nao_reeleito", "outro_eleito", "outro_disputou", "sem_candidatura", "sem_resultado", "falecimento")


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFD", texto or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z ]", "", sem_acento).strip()


def data_iso(texto: str) -> str:
    achado = re.match(r"(\d\d)/(\d\d)/(\d{4})", texto or "")
    return f"{achado[3]}-{achado[2]}-{achado[1]}" if achado else ""


def candidaturas_por_cpf(linhas: Iterable[dict[str, str]]) -> dict[str, dict[str, str]]:
    """Uma linha por pessoa. Em eleição com segundo turno, vale a linha do turno mais recente."""
    por_cpf: dict[str, dict[str, str]] = {}
    for linha in linhas:
        cpf = linha["NR_CPF_CANDIDATO"]
        if cpf not in por_cpf or linha["NR_TURNO"] > por_cpf[cpf]["NR_TURNO"]:
            por_cpf[cpf] = linha
    return por_cpf


def situacao_de_quem_tem_mandato(candidatura: Optional[dict[str, str]], falecimento: Optional[str] = None) -> dict[str, Any]:
    """Badge de quem exerceu mandato na legislatura atual, a partir da candidatura em 2026.

    Quem faleceu não pode aparecer como quem escolheu não concorrer.
    """
    if falecimento and candidatura is None:
        ano, mes, dia = falecimento[:10].split("-")
        return {"chave": "falecimento", "rotulo": f"{ROTULOS['falecimento']} em {dia}/{mes}/{ano}"}
    if candidatura is None:
        return {"chave": "sem_candidatura", "rotulo": ROTULOS["sem_candidatura"]}
    cargo, resultado = candidatura["DS_CARGO"].upper(), candidatura["DS_SIT_TOT_TURNO"]
    if cargo == CARGO_DEPUTADO:
        if resultado in ELEITO:
            chave = "reeleicao"
        elif resultado == "SUPLENTE":
            chave = "suplencia"
        elif resultado == "NÃO ELEITO":
            chave = "nao_reeleito"
        else:
            chave = "sem_resultado"
        return {"chave": chave, "rotulo": ROTULOS[chave]}
    nome_do_cargo = NOMES_DOS_CARGOS.get(cargo, cargo.lower())
    if resultado in ELEITO:
        return {"chave": "outro_eleito", "rotulo": f"Eleição para {nome_do_cargo}"}
    return {"chave": "outro_disputou", "rotulo": ROTULOS["outro_disputou"], "detalhe": f"Disputou {nome_do_cargo} em {ANO_DA_ELEICAO}."}


def candidatos_no_historico(historico: list[dict[str, str]], nome: str, nascimento: str) -> list[dict[str, str]]:
    """Possíveis registros antigos da pessoa na Câmara: mesma data de nascimento e ao menos dois nomes em comum."""
    alvo = set(normalizar(nome).split()) - PALAVRAS_VAZIAS
    return [
        r for r in historico
        if nascimento and r["dataNascimento"] == nascimento
        and len(alvo & (set(normalizar(r["nomeCivil"]).split()) - PALAVRAS_VAZIAS)) >= 2
    ]


def votos_por_candidatura(linhas: Iterable[dict[str, str]], guardar_municipios: set[str]) -> dict[str, dict[str, Any]]:
    """Votos do turno mais recente de cada candidatura, com os municípios só de quem vai ter página própria."""
    turnos: dict[str, str] = {}
    votos: dict[str, Counter[str]] = defaultdict(Counter)
    for linha in linhas:
        sq, turno = linha["SQ_CANDIDATO"], linha["NR_TURNO"]
        if turno > turnos.get(sq, ""):
            turnos[sq] = turno
            votos[sq] = Counter()
        if turno == turnos[sq]:
            votos[sq][linha["NM_MUNICIPIO"]] += int(linha["QT_VOTOS_NOMINAIS_VALIDOS"])
    resultado = {}
    for sq, por_municipio in votos.items():
        resultado[sq] = {"votos": sum(por_municipio.values())}
        if sq in guardar_municipios:
            resultado[sq]["total_municipios"] = len(por_municipio)
            resultado[sq]["municipios"] = [[n, v] for n, v in por_municipio.most_common(MUNICIPIOS_GUARDADOS)]
    return resultado


def coletar(camara: Any, fonte: Any, historico: list[dict[str, str]], em_exercicio: set[int]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidaturas = candidaturas_por_cpf(fonte.candidatos(ANO_DA_ELEICAO))
    do_mandato = [r for r in historico if r["idLegislaturaFinal"] == str(LEGISLATURA_ATUAL)]

    situacoes: dict[str, dict[str, Any]] = {}
    arquivo: list[dict[str, Any]] = []
    cpfs_com_mandato: dict[str, int] = {}
    sq_por_id: dict[int, str] = {}
    for registro in do_mandato:
        id_ = int(registro["uri"].rsplit("/", 1)[-1])
        dados = camara._get(f"/deputados/{id_}")["dados"]
        candidatura = candidaturas.get(dados["cpf"])
        cpfs_com_mandato[dados["cpf"]] = id_
        situacoes[str(id_)] = situacao_de_quem_tem_mandato(candidatura, registro.get("dataFalecimento"))
        if candidatura:
            sq_por_id[id_] = candidatura["SQ_CANDIDATO"]
        if id_ not in em_exercicio:
            status = dados["ultimoStatus"]
            arquivo.append({**Deputado.da_api(dados).para_dict(), "saiu_em": (status.get("data") or "")[:10] or None})

    eleitos = []
    for cpf, candidatura in candidaturas.items():
        if candidatura["DS_CARGO"].upper() != CARGO_DEPUTADO or candidatura["DS_SIT_TOT_TURNO"] not in ELEITO or cpf in cpfs_com_mandato:
            continue
        id_antigo = None
        for registro in candidatos_no_historico(historico, candidatura["NM_CANDIDATO"], data_iso(candidatura["DT_NASCIMENTO"])):
            id_candidato = int(registro["uri"].rsplit("/", 1)[-1])
            if camara._get(f"/deputados/{id_candidato}")["dados"].get("cpf") == cpf:
                id_antigo = id_candidato
                break
        chave = "retorno" if id_antigo else "primeiro"
        eleitos.append({
            "sq": candidatura["SQ_CANDIDATO"],
            "nome": candidatura["NM_URNA_CANDIDATO"],
            "partido": candidatura["SG_PARTIDO"],
            "uf": candidatura["SG_UF"],
            "chave": chave,
            "rotulo": ROTULOS[chave],
            "id_camara_antigo": id_antigo,
        })

    novos = {e["sq"] for e in eleitos}
    votos = votos_por_candidatura(fonte.votacao(ANO_DA_ELEICAO, "BRASIL"), novos)
    bens_de_todos = list(fonte.bens(ANO_DA_ELEICAO))
    bens_por_sq: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in bens_de_todos:
        if linha["SQ_CANDIDATO"] in novos:
            bens_por_sq[linha["SQ_CANDIDATO"]].append(linha)
    for eleito in eleitos:
        eleito.update(votos.get(eleito["sq"], {"votos": 0}))
        eleito["bens"] = bens_declarados(bens_por_sq[eleito["sq"]], eleito["sq"])
    for id_texto, situacao in situacoes.items():
        sq = sq_por_id.get(int(id_texto))
        if sq and sq in votos:
            situacao["votos"] = votos[sq]["votos"]
    eleitos.sort(key=lambda e: normalizar(e["nome"]))
    arquivo.sort(key=lambda d: normalizar(d["nome"]))
    documento = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "legislatura_atual": LEGISLATURA_ATUAL,
        "ano_da_eleicao": ANO_DA_ELEICAO,
        "posse": POSSE,
        "situacoes": situacoes,
        "eleitos_novos": eleitos,
    }
    return documento, arquivo


def ler(caminho: Path) -> Optional[dict[str, Any]]:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


# --- O que a página mostra


def resumo(doc: dict[str, Any]) -> dict[str, Any]:
    contagem = Counter(s["chave"] for s in doc["situacoes"].values())
    contagem.update(e["chave"] for e in doc["eleitos_novos"])
    chegam = [{"chave": c, "rotulo": ROTULOS[c], "valor": contagem[c]} for c in CHEGAM if contagem[c]]
    saem = [{"chave": c, "rotulo": ROTULOS[c], "valor": contagem[c]} for c in SAEM if contagem[c]]
    total = sum(c["valor"] for c in chegam) or 1
    maior = max((c["valor"] for c in saem), default=1)
    return {
        "chegam": [{**c, "largura": round(c["valor"] / total * 100, 2)} for c in chegam],
        "saem": [{**c, "largura": round(c["valor"] / maior * 100, 1)} for c in saem],
        "total_eleitos": sum(c["valor"] for c in chegam),
    }


def baixar_historico(http: Optional[httpx.Client] = None) -> list[dict[str, str]]:
    cliente = http or httpx.Client(timeout=120, follow_redirects=True)
    texto = cliente.get(URL_DEPUTADOS).raise_for_status().content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texto, newline=""), delimiter=";"))


if __name__ == "__main__":
    atuais = {d["id"] for d in json.loads(Path("data/deputados.json").read_text(encoding="utf-8"))["deputados"]}
    doc, saidas = coletar(ClienteCamara(), FonteTSE(), baixar_historico(), atuais)
    SAIDA_PADRAO.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    ARQUIVO_PADRAO.write_text(json.dumps({"deputados": saidas}, ensure_ascii=False, indent=1), encoding="utf-8")
    contagem_final = Counter(s["chave"] for s in doc["situacoes"].values())
    contagem_final.update(e["chave"] for e in doc["eleitos_novos"])
    print(f"Situações: {dict(contagem_final)}; {len(saidas)} no arquivo", file=sys.stderr)

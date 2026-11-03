"""Coleta do que está em discussão no plenário da Câmara e do Senado.

Junta, por proposição: as votações de plenário dos últimos dias (com placar,
voto de cada parlamentar e orientação dos partidos, quando existem), a pauta
dos próximos dias, a situação atual, os temas e os links oficiais.

A mesma proposição tem a mesma identificação nas duas casas ("PLP 186/2026"),
então as votações da Câmara e do Senado caem no mesmo registro.

Como em `models.py`, só os campos montados aqui chegam ao JSON: dados pessoais
presentes nas respostas (como o sexo do parlamentar no Senado) ficam de fora.

Uso: python -m monitor_politico.congresso [saida.json]
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

import httpx

from monitor_politico.camara import ClienteCamara
from monitor_politico.models import como_lista
from monitor_politico.senado import ClienteSenado

SAIDA_PADRAO = Path("data/congresso.json")
DIAS_VOTACOES = 30
DIAS_PAUTA = 7
LIMITE_FALHAS = 0.1  # fração de proposições que pode falhar antes de abortar a coleta
FUSO = ZoneInfo("America/Sao_Paulo")

URL_CAMARA = "https://www.camara.leg.br/propostas-legislativas/{id}"
URL_SENADO = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}"

# Votações de rito (urgência, redação final, admissibilidade de MP…), que não
# decidem o mérito. Ficam na página da proposição, mas não a colocam na lista
# de "votado recentemente" sozinhas.
PROCEDIMENTO = re.compile(
    r"requerimento|reda[cç][aã]o final|emenda de reda[cç][aã]o|pressupostos constitucionais"
    r"|regime de tramita|mantido o texto",
    re.IGNORECASE,
)
IDENTIFICACAO = re.compile(r"^\s*([A-Z]+)\s+(\d+)/(\d{4})\s*$")
VOTOS_PLACAR = {"Sim": "sim", "Não": "nao", "Abstenção": "abstencao"}


class ColetaIncompleta(RuntimeError):
    pass


def chave(sigla: str, numero: Any, ano: Any) -> str:
    return f"{sigla} {int(numero)}/{int(ano)}"


def separar_chave(identificacao: str) -> Optional[tuple[str, int, int]]:
    m = IDENTIFICACAO.match(identificacao or "")
    return (m[1], int(m[2]), int(m[3])) if m else None


def eh_procedimento(descricao: str) -> bool:
    return bool(PROCEDIMENTO.search(descricao or ""))


def _placar(votos: list[dict[str, Any]]) -> dict[str, Any]:
    placar: dict[str, Any] = {"sim": 0, "nao": 0, "abstencao": 0}
    outros: dict[str, int] = defaultdict(int)
    for v in votos:
        if v["voto"] in VOTOS_PLACAR:
            placar[VOTOS_PLACAR[v["voto"]]] += 1
        else:
            outros[v["voto"]] += 1
    placar["outros"] = [[rotulo, n] for rotulo, n in sorted(outros.items(), key=lambda kv: -kv[1])]
    return placar


def _resultado(aprovada: Optional[bool]) -> Optional[str]:
    return None if aprovada is None else ("aprovada" if aprovada else "rejeitada")


# Câmara


def votacao_camara(cliente: ClienteCamara, bruta: dict[str, Any]) -> dict[str, Any]:
    votos = [
        {
            "id": v["deputado_"]["id"],
            "nome": v["deputado_"]["nome"],
            "partido": v["deputado_"]["siglaPartido"],
            "uf": v["deputado_"]["siglaUf"],
            "voto": "Presidente da sessão (art. 17)" if v["tipoVoto"] == "Artigo 17" else v["tipoVoto"],
        }
        for v in cliente.votos(bruta["id"])
    ]
    orientacoes = None
    if votos:
        orientacoes = [[o["siglaPartidoBloco"], o["orientacaoVoto"] or None] for o in cliente.orientacoes(bruta["id"])]
    aprovacao = bruta.get("aprovacao")
    return {
        "id": bruta["id"],
        "casa": "Câmara",
        "data_hora": bruta.get("dataHoraRegistro") or bruta["data"],
        "descricao": bruta["descricao"],
        "resultado": _resultado(None if aprovacao is None else bool(aprovacao)),
        "procedimento": eh_procedimento(bruta["descricao"]),
        "nominal": bool(votos),
        "placar": _placar(votos) if votos else None,
        "orientacoes": orientacoes,
        "votos": sorted(votos, key=lambda v: v["nome"]),
    }


def _situacao_camara(prop: dict[str, Any]) -> Optional[dict[str, Any]]:
    status = prop.get("statusProposicao") or {}
    if not status.get("dataHora"):
        return None
    norma = None
    despacho = status.get("despacho") or ""
    m = re.match(r"Transformad[oa] n[ao] (.+?)\.(\s|$)", despacho)
    if m:
        norma = m[1]
    return {
        "descricao": status.get("descricaoSituacao") or status.get("descricaoTramitacao"),
        "data": status["dataHora"][:10],
        "casa": "Câmara",
        "norma": norma,
    }


# Senado


def votacao_senado(bruta: dict[str, Any]) -> dict[str, Any]:
    votos = [
        {
            "id": v["codigoParlamentar"],
            "nome": v["nomeParlamentar"],
            "partido": v["siglaPartidoParlamentar"],
            "uf": v["siglaUFParlamentar"],
            "voto": v["siglaVotoParlamentar"] if v["siglaVotoParlamentar"] in VOTOS_PLACAR
            else (v.get("descricaoVotoParlamentar") or v["siglaVotoParlamentar"]),
        }
        for v in bruta.get("votos") or []
    ]
    resultado = {"A": "aprovada", "R": "rejeitada"}.get(bruta.get("resultadoVotacao") or "")
    return {
        "id": f"SF-{bruta['codigoSessaoVotacao']}",
        "casa": "Senado",
        "data_hora": bruta["dataSessao"],  # o Senado não informa a hora; a ordem da lista é a da sessão
        "descricao": bruta["descricaoVotacao"],
        "resultado": resultado,
        "procedimento": eh_procedimento(bruta["descricaoVotacao"]),
        "nominal": bool(votos) and bruta.get("votacaoSecreta") != "S",
        "placar": _placar(votos) if votos else None,
        "orientacoes": None,
        "votos": sorted(votos, key=lambda v: v["nome"]),
    }


def _sentenca(texto: str) -> str:
    texto = texto.strip()
    return texto[:1].upper() + texto[1:].lower() if texto.isupper() else texto


def _situacao_senado(proc: dict[str, Any]) -> Optional[dict[str, Any]]:
    if not proc.get("dataSituacaoAtual"):
        return None
    norma = proc.get("normaGerada")
    if isinstance(norma, dict):
        norma = norma.get("descricao")
    return {
        "descricao": _sentenca(proc.get("situacaoAtual") or ""),
        "data": proc["dataSituacaoAtual"][:10],
        "casa": "Senado",
        "norma": norma or None,
    }


def _temas_senado(detalhe: dict[str, Any]) -> list[str]:
    """Usa o segundo nível da classificação do Senado ("Política Social / Trabalho e
    Emprego / Jornada"), que costuma coincidir com os temas da Câmara."""
    temas = []
    for c in detalhe.get("classificacoes") or []:
        niveis = [n.strip() for n in (c.get("descricaoHierarquia") or c.get("descricao") or "").split("/")]
        tema = niveis[1] if len(niveis) > 1 else niveis[0]
        if tema and tema not in temas:
            temas.append(tema)
    return temas


# Pauta


def pauta_camara(cliente: ClienteCamara, inicio: date, fim: date) -> list[dict[str, Any]]:
    sessoes = []
    for evento in cliente.sessoes_deliberativas(inicio, fim):
        itens, vistos = [], set()
        for item in cliente.pauta(evento["id"]):
            prop = item.get("proposicaoRelacionada_") or item.get("proposicao_") or {}
            if not prop.get("siglaTipo") or prop["siglaTipo"] == "REQ" or not int(prop.get("ano") or 0):
                continue
            k = chave(prop["siglaTipo"], prop["numero"], prop["ano"])
            if k in vistos:
                continue
            vistos.add(k)
            itens.append({"chave": k, "id_camara": int(prop["id"]), "ementa": prop.get("ementa"), "fase": item.get("topico") or item.get("regime")})
        sessoes.append({
            "casa": "Câmara",
            "data_hora": evento["dataHoraInicio"],
            "sessao": evento["descricaoTipo"],
            "itens": itens,
        })
    return sessoes


def pauta_senado(cliente: ClienteSenado, inicio: date, fim: date) -> list[dict[str, Any]]:
    brutas = cliente.agenda_do_mes(inicio)
    if fim.month != inicio.month:
        brutas += cliente.agenda_do_mes(fim.replace(day=1))
    sessoes = []
    for s in brutas:
        dia = date.fromisoformat(s["Data"])
        if not inicio <= dia <= fim:
            continue
        itens = []
        for m in como_lista((s.get("Materias") or {}).get("Materia")):
            partes = separar_chave(m.get("DescricaoIdentificacaoMateria", ""))
            if not partes:
                continue
            fase = (m.get("Apreciacao") or "").strip()
            itens.append({"chave": chave(*partes), "ementa": m.get("Ementa"), "fase": fase if fase not in ("", "-") else None})
        if itens:
            sessoes.append({
                "casa": "Senado",
                "data_hora": f"{s['Data']}T{(s.get('Hora') or '00:00').strip()}",
                "sessao": _sentenca(s.get("TipoSessao") or ""),
                "itens": itens,
            })
    return sessoes


# Proposição


def montar_proposicao(
    k: str,
    camara: ClienteCamara,
    senado: ClienteSenado,
    id_camara: Optional[int],
    votacoes: list[dict[str, Any]],
) -> dict[str, Any]:
    sigla, numero, ano = separar_chave(k)  # type: ignore[misc]
    if id_camara is None:
        id_camara = camara.buscar_proposicao(sigla, numero, ano)
    prop_camara = camara.proposicao(id_camara) if id_camara else None
    proc_senado = senado.processo(sigla, numero, ano)

    temas = camara.temas(id_camara) if id_camara else []
    if not temas and proc_senado:
        temas = _temas_senado(senado.processo_detalhe(proc_senado["id"]))

    autores: list[str] = camara.autores(id_camara) if id_camara else []
    if not autores and proc_senado and proc_senado.get("autoria"):
        autores = [proc_senado["autoria"]]

    situacoes = [s for s in (_situacao_camara(prop_camara or {}), _situacao_senado(proc_senado or {})) if s]
    situacao = max(situacoes, key=lambda s: s["data"]) if situacoes else None
    if situacao and not situacao["norma"]:
        situacao["norma"] = next((s["norma"] for s in situacoes if s["norma"]), None)

    ementa = (prop_camara or {}).get("ementa") or (proc_senado or {}).get("ementa")
    # A casa onde foi apresentada primeiro é a de origem.
    apresentacoes = sorted(
        (data[:10], casa)
        for casa, data in (("Câmara", (prop_camara or {}).get("dataApresentacao")), ("Senado", (proc_senado or {}).get("dataApresentacao")))
        if data
    )
    apresentacao, casa_inicial = apresentacoes[0] if apresentacoes else (None, None)
    return {
        "chave": k,
        "slug": f"{sigla}-{numero}-{ano}".lower(),
        "sigla": sigla,
        "numero": numero,
        "ano": ano,
        "tipo": (prop_camara or {}).get("descricaoTipo") or (proc_senado or {}).get("tipoDocumento"),
        "ementa": ementa,
        "apelido": (proc_senado or {}).get("apelido") or None,
        "autores": autores,
        "data_apresentacao": apresentacao,
        "casa_inicial": casa_inicial,
        "temas": temas,
        "situacao": situacao,
        "url_camara": URL_CAMARA.format(id=id_camara) if id_camara else None,
        "url_senado": URL_SENADO.format(codigo=proc_senado["codigoMateria"]) if proc_senado and proc_senado.get("codigoMateria") else None,
        "url_inteiro_teor": (prop_camara or {}).get("urlInteiroTeor") or (proc_senado or {}).get("urlDocumento"),
        "votacoes": sorted(votacoes, key=lambda v: v["data_hora"]),
    }


def coletar(
    camara: ClienteCamara,
    senado: ClienteSenado,
    saida: Path = SAIDA_PADRAO,
    hoje: Optional[date] = None,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
) -> dict[str, Any]:
    hoje = hoje or datetime.now(FUSO).date()
    inicio_votacoes = hoje - timedelta(days=DIAS_VOTACOES)
    fim_pauta = hoje + timedelta(days=DIAS_PAUTA - 1)
    anteriores = _ler_anteriores(saida)

    # 1. Listas (uma falha aqui aborta: sem elas não há o que mostrar).
    camara_por_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for v in camara.votacoes_plenario(inicio_votacoes, hoje):
        camara_por_id[int(v["id"].split("-")[0])].append(v)
    # Proposições com só votações de rito (ex.: urgência aprovada) ainda não foram votadas no mérito.
    camara_por_id = {i: vs for i, vs in camara_por_id.items() if not all(eh_procedimento(v["descricao"]) for v in vs)}
    senado_votacoes = senado.votacoes(inicio_votacoes, hoje)
    pauta = pauta_camara(camara, hoje, fim_pauta) + pauta_senado(senado, hoje, fim_pauta)

    # 2. Detalhes por proposição; uma falha reaproveita a coleta anterior.
    falhas: list[str] = []
    sementes: dict[str, dict[str, Any]] = defaultdict(lambda: {"id_camara": None, "votacoes": []})
    for id_camara, brutas in camara_por_id.items():
        try:
            prop = camara.proposicao(id_camara)
            semente = sementes[chave(prop["siglaTipo"], prop["numero"], prop["ano"])]
            semente["id_camara"] = id_camara
            semente["votacoes"] += [votacao_camara(camara, v) for v in brutas]
        except httpx.HTTPError as erro:
            falhas.append(f"Câmara {id_camara}")
            avisar(f"proposição {id_camara} da Câmara falhou ({erro})")
    for v in senado_votacoes:
        partes = separar_chave(v.get("identificacao", ""))
        if partes:
            sementes[chave(*partes)]["votacoes"].append(votacao_senado(v))
    for sessao in pauta:
        for item in sessao["itens"]:
            semente = sementes[item["chave"]]
            semente["id_camara"] = semente["id_camara"] or item.get("id_camara")

    proposicoes: dict[str, dict[str, Any]] = {}
    for k, semente in sementes.items():
        try:
            proposicoes[k] = montar_proposicao(k, camara, senado, semente["id_camara"], semente["votacoes"])
        except httpx.HTTPError as erro:
            falhas.append(k)
            avisar(f"{k} falhou ({erro})")
            if k in anteriores:
                proposicoes[k] = anteriores[k]

    total = len(camara_por_id) + len(sementes)
    if falhas and len(falhas) > LIMITE_FALHAS * total:
        raise ColetaIncompleta(f"{len(falhas)} de {total} consultas falharam: {', '.join(falhas[:10])}")

    for sessao in pauta:
        for item in sessao["itens"]:
            item.pop("id_camara", None)
    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "periodo": {"votacoes_desde": inicio_votacoes.isoformat(), "pauta_ate": fim_pauta.isoformat()},
        "pauta": sorted(pauta, key=lambda s: (s["data_hora"], s["casa"])),
        "proposicoes": dict(sorted(proposicoes.items())),
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


def _ler_anteriores(caminho: Path) -> dict[str, dict[str, Any]]:
    if not caminho.exists():
        return {}
    return json.loads(caminho.read_text(encoding="utf-8")).get("proposicoes", {})


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    doc = coletar(ClienteCamara(), ClienteSenado(), destino)
    sessoes = sum(len(s["itens"]) for s in doc["pauta"])
    print(f"{len(doc['proposicoes'])} proposições e {sessoes} itens de pauta salvos em {destino}")

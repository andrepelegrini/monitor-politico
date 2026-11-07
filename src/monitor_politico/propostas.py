"""Projetos e PECs assinados por um deputado desde o primeiro mandato, e quais viraram norma jurídica.

A lista vem dos arquivos anuais de Dados Abertos da Câmara. O número da norma só existe na tramitação
de cada proposta. Os totais por ano de todos os tipos de proposta e de relatorias vêm da página oficial.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Callable, Iterable, Optional

from monitor_politico.plenario import ementa_atual, limpar_texto

TIPOS = ("PL", "PLP", "PEC")
TIPOS_DE_RELATORIA = ("PL", "PLP", "PEC", "MPV", "PDL", "PRC")
ITENS_NA_PAGINA = 15  # O restante da lista é baixado quando alguém usa os filtros.
ROTULOS_PARTICIPACAO = {"primeira": "Autoria principal", "coautoria": "Coautoria", "apoio": "Apoio em PEC"}
EXPLICACOES_PARTICIPACAO = {
    "primeira": "Primeira assinatura da proposta",
    "coautoria": "Assinou como autoria, sem ser a primeira",
    "apoio": "Assinou para atingir o mínimo de apoios, sem ser proponente",
}
ROTULOS_SITUACAO = {
    "norma": "Virou norma",
    "senado": "Aguardando o Senado",
    "tramitacao": "Em tramitação na Câmara",
    "encerrada": "Arquivada ou retirada",
    "sem_situacao": "Sem situação informada",
}
ROTULOS_SITUACAO_SENADO = {**ROTULOS_SITUACAO, "senado": "Aguardando a Câmara", "tramitacao": "Em tramitação no Senado"}
SITUACOES_ENCERRADAS = re.compile(r"arquivad|retirad|devolvid|rejeitad|prejudicad", re.IGNORECASE)
NORMA_NO_DESPACHO = re.compile(r"Transformad[oa] n[ao] (.+?)\.(\s|$)", re.IGNORECASE)
TRAMITACAO_DE_NORMA = re.compile(r"Transforma\w+ em Norma", re.IGNORECASE)
NORMA_SEM_NUMERO = "Norma sem número informado na tramitação"


def participacao(linha_autor: dict[str, str]) -> str:
    """Em PEC, quem assina para atingir o mínimo de apoios não é proponente."""
    if linha_autor["proponente"] != "1":
        return "apoio"
    return "primeira" if linha_autor["ordemAssinatura"] == "1" else "coautoria"


def grupo_da_situacao(situacao: str) -> str:
    if not situacao:
        return "sem_situacao"
    if "norma" in situacao.lower():
        return "norma"
    if "senado federal" in situacao.lower():
        return "senado"
    return "encerrada" if SITUACOES_ENCERRADAS.search(situacao) else "tramitacao"


def norma_da_tramitacao(tramitacoes: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Nome da norma, data e se houve veto parcial. A mais recente vale se houver retificação.

    Há tramitações do tipo "Transformação em Norma Jurídica" com o texto vazio: a norma existe e a data
    vale, só falta o número.
    """
    achada = None
    for item in sorted(tramitacoes, key=lambda t: t.get("dataHora") or ""):
        despacho = item.get("despacho") or ""
        encontrado = NORMA_NO_DESPACHO.search(despacho)
        if encontrado:
            nome = re.sub(r"\s+", " ", encontrado[1]).strip()
        elif TRAMITACAO_DE_NORMA.search(item.get("descricaoTramitacao") or ""):
            nome = NORMA_SEM_NUMERO
        else:
            continue
        achada = {"nome": nome, "data": item["dataHora"][:10], "veto_parcial": "vetado parcialmente" in despacho.lower()}
    return achada


def palavra_da_norma(normas: Iterable[dict[str, Any]]) -> str:
    """"lei" só quando todas são leis: uma PEC aprovada, por exemplo, vira emenda constitucional."""
    nomes = [(n.get("norma") or {}).get("nome", "") for n in normas]
    return "lei" if all(nome.startswith("Lei") for nome in nomes) else "norma"


def relator_do_projeto(proposta: dict[str, str], inicio: str) -> Optional[int]:
    """Relator mais recente de um projeto, se a situação foi registrada no mandato.

    Fora os requerimentos de informação, que a Mesa relata aos milhares por causa do cargo, e as concessões de rádio e TV.
    """
    uri = proposta.get("ultimoStatus_uriRelator") or ""
    if not uri or proposta["siglaTipo"] not in TIPOS_DE_RELATORIA or (proposta.get("ultimoStatus_dataHora") or "")[:10] < inicio:
        return None
    return int(uri.rsplit("/", 1)[-1])


def propostas_de_todos(
    fonte: Any, consultar_norma: Callable[[str], Optional[dict[str, Any]]], inicios: dict[int, str], anos: Iterable[int],
    relatorias: Optional[Counter[int]] = None, inicio_relatorias: str = "",
) -> dict[int, list[dict[str, Any]]]:
    """Projetos e PECs de cada parlamentar, desde a primeira posse de cada um, numa passada só.

    Se `relatorias` vier, conta também em quantos projetos a pessoa é a relatora mais recente, no mesmo arquivo.
    """
    anos = list(anos)
    alvo = {str(i) for i in inicios}
    assinaturas: dict[str, dict[str, str]] = defaultdict(dict)
    for ano in anos:
        for linha in fonte.linhas("proposicoesAutores", ano):
            if linha["idDeputadoAutor"] in alvo:
                assinaturas[linha["idProposicao"]][linha["idDeputadoAutor"]] = participacao(linha)

    catalogo: dict[str, dict[str, Any]] = {}
    for ano in anos:
        for proposta in fonte.linhas("proposicoes", ano):
            if relatorias is not None:
                relator = relator_do_projeto(proposta, inicio_relatorias)
                if relator in inicios:
                    relatorias[relator] += 1
            if proposta["id"] not in assinaturas or proposta["siglaTipo"] not in TIPOS:
                continue
            catalogo[proposta["id"]] = {
                "id": proposta["id"],
                "sigla": f"{proposta['siglaTipo']} {proposta['numero']}/{proposta['ano']}",
                "tipo": proposta["siglaTipo"],
                "data": proposta["dataApresentacao"][:10],
                "ementa": limpar_texto(proposta["ementa"]),
                "situacao": limpar_texto(proposta["ultimoStatus_descricaoSituacao"]),
                "data_situacao": proposta["ultimoStatus_dataHora"][:10],
                "temas": [],
                "norma": None,
            }
    for ano in anos:
        for linha in fonte.linhas("proposicoesTemas", ano):
            proposta = catalogo.get(linha["uriProposicao"].rsplit("/", 1)[-1])
            if proposta and linha["tema"] not in proposta["temas"]:
                proposta["temas"].append(linha["tema"])
    for proposta in catalogo.values():
        proposta["temas"].sort()
        if grupo_da_situacao(proposta["situacao"]) == "norma":
            # A situação oficial já diz que virou norma. Sem texto na tramitação, falta só o número.
            proposta["norma"] = consultar_norma(proposta["id"]) or {"nome": NORMA_SEM_NUMERO, "data": proposta["data_situacao"], "veto_parcial": False}

    # Não filtra pela data da posse: a assinatura é a prova, e o histórico de quem foi suplente pode estar incompleto.
    por_pessoa: dict[int, list[dict[str, Any]]] = {i: [] for i in inicios}
    for id_proposta, proposta in catalogo.items():
        for id_deputado, tipo in assinaturas[id_proposta].items():
            por_pessoa[int(id_deputado)].append({**proposta, "participacao": tipo})
    for lista in por_pessoa.values():
        lista.sort(key=lambda p: (p["data"], p["id"]), reverse=True)
    return por_pessoa


def propostas_desde(fonte: Any, camara: Any, id_: int, inicio: str, anos: Iterable[int]) -> dict[str, Any]:
    anos = list(anos)
    def consultar(id_proposta: str) -> Optional[dict[str, Any]]:
        return norma_da_tramitacao(camara._get(f"/proposicoes/{id_proposta}/tramitacoes")["dados"])
    return {
        "inicio": inicio,
        "por_ano": [{"ano": ano, **fonte.atuacao_oficial(id_, ano)} for ano in anos],
        "propostas": propostas_de_todos(fonte, consultar, {id_: inicio}, anos)[id_],
    }


def coletar(fonte: Any, camara: Any, id_: int, inicio: str, hoje: date) -> dict[str, Any]:
    return propostas_desde(fonte, camara, id_, inicio, range(int(inicio[:4]), hoje.year + 1))


# --- O que a página mostra


def mandato_da_data(data: str, mandatos: list[dict[str, str]]) -> str:
    """Mandato em que a proposta foi apresentada. `mandatos` vem do mais antigo para o mais recente."""
    atual = mandatos[0]["rotulo"] if mandatos else ""
    for mandato in mandatos:
        if data >= mandato["inicio"]:
            atual = mandato["rotulo"]
    return atual


def _rotulo_situacao(chave: str, palavra: str, casa: str = "camara") -> str:
    if chave == "norma":
        return f"Virou {palavra}"
    return (ROTULOS_SITUACAO_SENADO if casa == "senado" else ROTULOS_SITUACAO)[chave]


def _caminho(propostas: list[dict[str, Any]], palavra: str, casa: str = "camara") -> list[dict[str, Any]]:
    """Uma linha por tipo de participação, com a largura proporcional ao total de propostas."""
    maior = max((sum(p["participacao"] == c for p in propostas) for c in ROTULOS_PARTICIPACAO), default=1) or 1
    linhas = []
    for chave, rotulo in ROTULOS_PARTICIPACAO.items():
        grupo = [p for p in propostas if p["participacao"] == chave]
        if not grupo:
            continue
        contagem = Counter(p["grupo"] for p in grupo)
        linhas.append({
            "chave": chave,
            "rotulo": rotulo,
            "explicacao": EXPLICACOES_PARTICIPACAO[chave],
            "total": len(grupo),
            "normas": contagem["norma"],
            "largura": round(len(grupo) / maior * 100, 1),
            "situacoes": [
                {"chave": c, "rotulo": _rotulo_situacao(c, palavra, casa), "valor": contagem[c], "largura": round(contagem[c] / len(grupo) * 100, 2)}
                for c in ROTULOS_SITUACAO if contagem[c]
            ],
        })
    return linhas


def visao(
    doc: dict[str, Any], slugs: Optional[dict[str, str]] = None, mandatos: Optional[list[dict[str, str]]] = None,
    inicio_mandato: Optional[str] = None, casa: str = "camara",
) -> dict[str, Any]:
    slugs, mandatos = slugs or {}, mandatos or []
    propostas = []
    for proposta in doc["propostas"]:
        propostas.append({
            **proposta,
            "ementa": ementa_atual(proposta["ementa"]),
            "grupo": proposta.get("grupo") or grupo_da_situacao(proposta["situacao"]),
            "rotulo_participacao": ROTULOS_PARTICIPACAO[proposta["participacao"]],
            "slug": slugs.get(proposta["sigla"]),
            "mandato": mandato_da_data(proposta["data"], mandatos),
        })
    normas = sorted((p for p in propostas if p["grupo"] == "norma"), key=lambda p: (p["norma"] or {}).get("data") or p["data"], reverse=True)
    assuntos = Counter(t for p in propostas for t in p["temas"])
    maior = max(assuntos.values(), default=1)
    situacoes = Counter(p["grupo"] for p in propostas)
    palavra = palavra_da_norma(normas)
    no_mandato = [p for p in normas if inicio_mandato and p["norma"] and p["norma"]["data"] >= inicio_mandato and p["participacao"] != "apoio"]
    por_mandato = []
    for mandato in reversed(mandatos):
        grupo = [p for p in propostas if p["mandato"] == mandato["rotulo"]]
        por_mandato.append({
            "rotulo": mandato["rotulo"],
            "primeira": sum(p["participacao"] == "primeira" for p in grupo),
            "coautoria": sum(p["participacao"] == "coautoria" for p in grupo),
            "normas": sum(p["grupo"] == "norma" and p["participacao"] != "apoio" for p in grupo),
        })
    return {
        "inicio": doc["inicio"],
        "ano_inicial": doc["inicio"][:4],
        "propostas": propostas,
        "propostas_iniciais": propostas[:ITENS_NA_PAGINA],
        "total": len(propostas),
        "total_autoria_propostas": sum(p["participacao"] != "apoio" for p in propostas),
        "normas": normas,
        "normas_principais": [p for p in normas if p["participacao"] == "primeira"],
        "normas_coautoria": [p for p in normas if p["participacao"] == "coautoria"],
        "palavra_norma": palavra,
        "inicio_mandato": inicio_mandato,
        "norma_sem_numero": NORMA_SEM_NUMERO,
        "sancionadas_no_mandato": {
            "total": len(no_mandato),
            "principal": sum(p["participacao"] == "primeira" for p in no_mandato),
            "coautoria": sum(p["participacao"] == "coautoria" for p in no_mandato),
        },
        "caminho": _caminho(propostas, palavra, casa),
        "por_mandato": por_mandato,
        "tipos": [(t, sum(p["tipo"] == t for p in propostas)) for t in TIPOS if any(p["tipo"] == t for p in propostas)],
        "situacoes": [(_rotulo_situacao(c, palavra, casa), situacoes[c], c) for c in ROTULOS_SITUACAO if situacoes[c]],
        "temas": [{"nome": t, "valor": n, "largura": round(n / maior * 100, 1)} for t, n in assuntos.most_common(6)],
        "opcoes_temas": sorted(assuntos),
        "por_ano": doc["por_ano"],
        "total_autoria": sum(a["autoria"] for a in doc["por_ano"]),
        "total_relatadas": sum(a["relatadas"] for a in doc["por_ano"]),
        "relatorias_no_mandato": doc.get("relatorias_no_mandato"),
    }

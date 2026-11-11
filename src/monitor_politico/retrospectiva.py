"""Retrospectiva da legislatura 2023–2027 de cada parlamentar, com referências da Casa inteira.

Os números são os do perfil completo e da lista comparável, no mesmo período e com o mesmo critério
para todos. As referências são a mediana e contagens objetivas ("N têm mais"), calculadas só entre
quem exerceu pelo menos três quartos do período, para não comparar quem assumiu há pouco com quem
está desde o início. Quem exerceu menos que isso vê os próprios números sem as referências de contagem.
"""

from __future__ import annotations

import statistics
from typing import Any, Optional

from monitor_politico import metricas as modulo_metricas
from monitor_politico.perfis import numero, partir

FRACAO_PERIODO_COMPLETO = 0.75
MAX_LEIS_NA_PAGINA = 8
TAMANHO_DESCRICAO = 150


def referencias(metricas: Optional[dict[str, Any]], ids: list[int]) -> dict[str, Any]:
    """Mediana e distribuição da Casa, entre quem exerceu ao menos três quartos do período."""
    numeros = {i: modulo_metricas.do_deputado(metricas, i) for i in ids}
    maior = max((n["dias"] for n in numeros.values()), default=0)
    completos = [n for n in numeros.values() if maior and n["dias"] >= FRACAO_PERIODO_COMPLETO * maior]

    def mediana(campo: str) -> Optional[float]:
        valores = [n[campo] for n in completos if n[campo] is not None]
        return statistics.median(valores) if valores else None

    return {
        "total": len(numeros),
        "completos": completos,
        "maior_periodo": maior,
        "mediana_presenca": mediana("percentual_presenca"),
        "mediana_votos": mediana("votos"),
        "mediana_relatorias": mediana("relatorias"),
        "sem_lei": sum(1 for n in numeros.values() if n["principal"] == 0),
    }


def _mais_que(ref: dict[str, Any], campo: str, valor: float) -> int:
    return sum(1 for n in ref["completos"] if n[campo] > valor)


def _pct(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + "%"


def cartao(r: dict[str, Any]) -> list[dict[str, str]]:
    """Os quatro números das imagens para compartilhar, com o rótulo curto (feed) e o longo (stories)."""
    n, ref, senado = r["numeros"], r["ref"], r["senado"]
    itens = [{
        "valor": str(n["principal"]),
        "rotulo": "lei de autoria principal" if n["principal"] == 1 else "leis de autoria principal",
        "detalhe": ("lei" if n["principal"] == 1 else "leis") + f" de autoria principal · {ref['sem_lei']} de {ref['total']} não têm nenhuma",
    }]
    if n["percentual_presenca"] is not None:
        nome = "de participação nas votações" if senado else "de presença"
        mediana = f" (mediana: {_pct(ref['mediana_presenca'])})" if ref["mediana_presenca"] is not None else ""
        itens.append({"valor": _pct(n["percentual_presenca"]), "rotulo": nome + mediana, "detalhe": nome + mediana})
    mediana_votos = f" · mediana {numero(ref['mediana_votos'])}" if r["completo"] and ref["mediana_votos"] is not None else ""
    itens.append({"valor": numero(n["votos"]), "rotulo": "votos no Plenário", "detalhe": "votos no Plenário" + mediana_votos})
    total = r["propostas_principal"] + r["propostas_coautoria"]
    itens.append({"valor": numero(total), "rotulo": "propostas apresentadas", "detalhe": f"propostas apresentadas · {r['propostas_principal']} de autoria principal"})
    return itens


def visao(perfil: dict[str, Any], numeros: dict[str, Any], ref: dict[str, Any], inicio: str = modulo_metricas.INICIO_MANDATO) -> dict[str, Any]:
    """Dados da página a partir da visão do perfil completo (perfis.visao) e dos números da lista."""
    senado = perfil.get("casa") == "senado"
    completo = bool(ref["maior_periodo"]) and numeros["dias"] >= FRACAO_PERIODO_COMPLETO * ref["maior_periodo"]
    propostas = perfil.get("propostas") or {}
    no_periodo = [p for p in propostas.get("propostas", []) if p["data"] >= inicio and p["participacao"] != "apoio"]
    leis = sorted(
        (p for p in propostas.get("normas", []) if p.get("norma") and p["norma"]["data"] >= inicio and p["participacao"] == "primeira"),
        key=lambda p: p["norma"]["data"], reverse=True,
    )
    plenario = perfil.get("plenario") or {}
    dinheiro = perfil.get("dinheiro") or {}
    cota = dinheiro.get("cota") or {}
    emendas = dinheiro.get("emendas") or {}
    anos_completos = [a for a in cota.get("por_ano", []) if a.get("percentual") is not None and int(a["ano"]) < int(perfil["coleta_local"][:4])]
    funcao = (emendas.get("funcoes") or [None])[0]
    resultado = {
        "senado": senado,
        "completo": completo,
        "inicio_exercicio": (perfil.get("legislatura_atual") or {}).get("inicio"),
        "numeros": numeros,
        "ref": {k: v for k, v in ref.items() if k != "completos"},
        "leis_mais": _mais_que(ref, "principal", numeros["principal"]) if completo else None,
        "relatorias_mais": _mais_que(ref, "relatorias", numeros["relatorias"]) if completo else None,
        "propostas_principal": sum(1 for p in no_periodo if p["participacao"] == "primeira"),
        "propostas_coautoria": sum(1 for p in no_periodo if p["participacao"] == "coautoria"),
        "leis": [
            {**p, "descricao": partir(p.get("ementa") or "", TAMANHO_DESCRICAO)}
            for p in leis[:MAX_LEIS_NA_PAGINA]
        ],
        "leis_alem": max(len(leis) - MAX_LEIS_NA_PAGINA, 0),
        "votacoes_nominais": plenario.get("votacoes_nominais"),
        "texto": plenario.get("texto"),
        "total_texto": plenario.get("total_texto", 0),
        "contra_texto": plenario.get("contra_texto", 0),
        "difere_texto": plenario.get("difere_texto", 0),
        "com_orientacao": plenario.get("com_orientacao", 0),
        "temas": (propostas.get("temas") or [])[:4],
        "cota_total": cota.get("total"),
        "cota_percentuais": [a["percentual"] for a in anos_completos],
        "cota_anos": [a["ano"] for a in anos_completos],
        "emendas_pago": emendas.get("pago_total"),
        "emendas_funcao": {"nome": funcao["nome"], "valor": funcao["valor"]} if funcao else None,
    }
    resultado["cartao"] = cartao(resultado)
    return resultado

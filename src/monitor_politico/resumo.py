"""Prepara o resumo que abre as páginas de deputados e senadores: composição
por partido, mulheres e homens, quem conduz a Casa, suplentes, bancadas por
estado (Câmara), blocos e mandatos (Senado)."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Optional, Sequence, Union

from monitor_politico.models import Deputado, Senador
from monitor_politico.painel import data_br

Parlamentar = Union[Deputado, Senador]


def pct(parte: int, total: int) -> str:
    """Porcentagem no formato brasileiro: 18,5%."""
    return f"{100 * parte / total:.1f}%".replace(".", ",") if total else "0%"


def _largura(n: int, maior: int) -> str:
    return f"{100 * n / maior:.1f}%" if maior else "0%"


def por_partido(parlamentares: Sequence[Parlamentar]) -> list[dict[str, Any]]:
    contagem = Counter(p.partido for p in parlamentares)
    maior = max(contagem.values(), default=0)
    return [
        {"sigla": sigla, "n": n, "pct": pct(n, len(parlamentares)), "largura": _largura(n, maior)}
        for sigla, n in sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def sexo(dados: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not dados:
        return None
    total = dados["mulheres"] + dados["homens"]
    return {
        **dados,
        "pct_mulheres": pct(dados["mulheres"], total),
        "pct_homens": pct(dados["homens"], total),
        "largura_mulheres": _largura(dados["mulheres"], total),
        "largura_homens": _largura(dados["homens"], total),
    }


def lideres(dados: Optional[list[dict[str, Any]]], ids_com_perfil: set[int]) -> list[dict[str, Any]]:
    return [{**l, "tem_perfil": l["id"] in ids_com_perfil} for l in dados or []]


def bancadas_por_uf(deputados: Sequence[Deputado]) -> list[dict[str, Any]]:
    por_uf: dict[str, Counter[str]] = defaultdict(Counter)
    for d in deputados:
        por_uf[d.uf][d.partido] += 1
    linhas = []
    for uf, partidos in por_uf.items():
        topo = max(partidos.values())
        lideres_uf = sorted(p for p, n in partidos.items() if n == topo)
        maior = f"{lideres_uf[0]} {topo}" if len(lideres_uf) == 1 else f"{', '.join(lideres_uf)} · {topo} cada"
        linhas.append({"uf": uf, "n": sum(partidos.values()), "maior": maior, "empate": len(lideres_uf) > 1})
    return sorted(linhas, key=lambda l: (-l["n"], l["uf"]))


def blocos(senadores: Sequence[Senador]) -> list[dict[str, Any]]:
    por_bloco: dict[Optional[str], Counter[str]] = defaultdict(Counter)
    for s in senadores:
        por_bloco[s.bloco][s.partido] += 1
    maior = max((sum(c.values()) for c in por_bloco.values()), default=0)
    linhas = []
    for bloco, partidos in por_bloco.items():
        n = sum(partidos.values())
        nome = (bloco or "Sem bloco").removeprefix("Bloco Parlamentar ").removeprefix("da ").removeprefix("do ")
        linhas.append({
            "nome": nome[:1].upper() + nome[1:],
            "nome_completo": bloco or "Sem bloco",
            "n": n,
            "largura": _largura(n, maior),
            "partidos": " · ".join(f"{p} {q}" for p, q in sorted(partidos.items(), key=lambda kv: (-kv[1], kv[0]))),
            "sem_bloco": bloco is None,
        })
    return sorted(linhas, key=lambda l: (l["sem_bloco"], -l["n"], l["nome"]))


def mandatos(senadores: Sequence[Senador]) -> list[dict[str, Any]]:
    contagem = Counter(s.fim_mandato for s in senadores if s.fim_mandato)
    total = sum(contagem.values())
    return [
        {"fim": data_br(fim), "ano": fim[:4], "n": n, "largura": _largura(n, total)}
        for fim, n in sorted(contagem.items())
    ]


def _cartoes(total: int, rotulo: str, detalhe_total: str, partidos: list[dict[str, Any]],
             sexo_: Optional[dict[str, Any]], suplentes: int, detalhe_suplentes: str, feminino: str) -> list[dict[str, str]]:
    cartoes = [
        {"valor": str(total), "rotulo": rotulo, "detalhe": detalhe_total},
        {"valor": str(len(partidos)), "rotulo": "partidos", "detalhe": f"O maior é o {partidos[0]['sigla']}, com {partidos[0]['n']}" if partidos else ""},
    ]
    if sexo_:
        cartoes.append({"valor": sexo_["pct_mulheres"], "rotulo": "são mulheres", "detalhe": f"{sexo_['mulheres']} {feminino if sexo_['mulheres'] != 1 else feminino[:-1]}"})
    cartoes.append({"valor": str(suplentes), "rotulo": "suplentes em exercício", "detalhe": detalhe_suplentes})
    return cartoes


def da_camara(deputados: Sequence[Deputado], dados: dict[str, Any]) -> dict[str, Any]:
    condicoes = Counter(d.condicao_eleitoral for d in deputados)
    efetivados, suplentes = condicoes.get("Efetivado", 0), condicoes.get("Suplente", 0)
    partidos = por_partido(deputados)
    bancadas = bancadas_por_uf(deputados)
    sexo_ = sexo(dados.get("sexo"))
    tamanhos = [b["n"] for b in bancadas]
    return {
        "cartoes": _cartoes(
            len(deputados), "deputados",
            f"De {min(tamanhos)} a {max(tamanhos)} por estado" if tamanhos else "",
            partidos, sexo_, efetivados + suplentes,
            f"{efetivados} efetivados e {suplentes} temporários", "deputadas",
        ),
        "partidos": partidos,
        "sexo": sexo_,
        "lideres": lideres(dados.get("lideres"), {d.id for d in deputados}),
        "titulares": condicoes.get("Titular", 0),
        "efetivados": efetivados,
        "suplentes": suplentes,
        "bancadas": bancadas,
    }


def do_senado(senadores: Sequence[Senador], dados: dict[str, Any]) -> dict[str, Any]:
    suplentes = sum(1 for s in senadores if s.condicao and s.condicao != "Titular")
    partidos = por_partido(senadores)
    sexo_ = sexo(dados.get("sexo"))
    return {
        "cartoes": _cartoes(
            len(senadores), "senadores", "3 por estado e pelo DF", partidos, sexo_,
            suplentes, "No lugar do titular", "senadoras",
        ),
        "partidos": partidos,
        "sexo": sexo_,
        "lideres": lideres(dados.get("lideres"), {s.id for s in senadores}),
        "suplentes": suplentes,
        "blocos": blocos(senadores),
        "mandatos": mandatos(senadores),
    }

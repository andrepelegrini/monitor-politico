"""Dados de composição das Casas que vão para o resumo no topo das páginas de
deputados e senadores: quem preside, os principais líderes e a contagem de
mulheres e homens.

O gênero entra só como contagem (total e por partido), nunca no registro de cada
parlamentar: o JSON continua sem dados pessoais por pessoa.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any, Iterable, Optional

from monitor_politico.models import como_lista

# Ordem em que os cargos aparecem; a chave é um trecho do nome da liderança na API do Senado.
CARGOS = [
    ("Governo", "Líder do Governo"),
    ("Oposição", "Líder da Oposição"),
    ("Maioria", "Líder da Maioria"),
    ("Minoria", "Líder da Minoria"),
    ("Bancada Feminina", "Líder da Bancada Feminina"),
]
CASAS = {"CD": "na Câmara dos Deputados", "SF": "no Senado Federal"}


def lideres(liderancas: list[dict[str, Any]], casa: str) -> list[dict[str, Any]]:
    """Líderes atuais de `casa` ("CD" ou "SF") a partir de GET /composicao/lideranca
    (API do Senado, que cobre as duas Casas). Só o líder ("L"), não os vices; se a
    API listar mais de um para o mesmo cargo, vale a designação mais recente."""
    escolhidos: dict[str, dict[str, Any]] = {}
    for item in liderancas:
        unidade = item.get("descricaoTipoUnidadeLideranca") or ""
        if item.get("casa") != casa or item.get("siglaTipoLideranca") != "L" or not unidade.endswith(CASAS[casa]):
            continue
        cargo = next((rotulo for trecho, rotulo in CARGOS if trecho in unidade), None)
        if not cargo:
            continue
        atual = escolhidos.get(cargo)
        if atual is None or item.get("dataDesignacao", "") > atual["_data"]:
            escolhidos[cargo] = {
                "cargo": cargo,
                "id": int(item["codigoDeputado"] if casa == "CD" and item.get("codigoDeputado") else item["codigoParlamentar"]),
                "nome": item["nomeParlamentar"],
                "partido": item.get("siglaPartidoFiliacao"),
                "uf": item.get("uf"),
                "_data": item.get("dataDesignacao", ""),
            }
    ordem = [rotulo for _t, rotulo in CARGOS]
    return [{k: v for k, v in l.items() if k != "_data"} for l in sorted(escolhidos.values(), key=lambda l: ordem.index(l["cargo"]))]


def presidente_da_camara(mesa: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Presidente atual a partir de GET /legislaturas/{id}/mesa (API da Câmara)."""
    for membro in mesa:
        if membro.get("titulo") == "Presidente" and not membro.get("dataFim"):
            return {"cargo": "Presidente", "id": membro["id"], "nome": membro["nome"],
                    "partido": membro.get("siglaPartido"), "uf": membro.get("siglaUf")}
    return None


def presidente_do_senado(mesa: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Presidente a partir de GET /composicao/mesaSF."""
    for colegiado in como_lista(((mesa.get("MesaSenado") or {}).get("Colegiados") or {}).get("Colegiado")):
        for cargo in como_lista((colegiado.get("Cargos") or {}).get("Cargo")):
            if "PRESIDENTE" in como_lista(cargo.get("Cargo")):
                partido, uf = _bancada(cargo.get("Bancada", ""))
                return {
                    "cargo": "Presidente",
                    "id": int(cargo["Http"]),
                    "nome": re.sub(r"^Senador[a]?\s+", "", cargo["NomeParlamentar"]),
                    "partido": partido,
                    "uf": uf,
                }
    return None


def _bancada(texto: str) -> tuple[Optional[str], Optional[str]]:
    """"(UNIÃO-AP)" -> ("UNIÃO", "AP")."""
    m = re.match(r"^\((.+)-([A-Z]{2})\)$", texto.strip())
    return (m[1], m[2]) if m else (None, None)


def contar_sexo(pares: Iterable[tuple[str, bool]]) -> dict[str, Any]:
    """Recebe (partido, é_mulher) de cada parlamentar e devolve só as contagens."""
    total: Counter[str] = Counter()
    por_partido: dict[str, Counter[str]] = defaultdict(Counter)
    for partido, mulher in pares:
        chave = "mulheres" if mulher else "homens"
        total[chave] += 1
        por_partido[partido][chave] += 1
    return {
        "mulheres": total["mulheres"],
        "homens": total["homens"],
        "mulheres_por_partido": dict(sorted(
            ((p, c["mulheres"]) for p, c in por_partido.items() if c["mulheres"]),
            key=lambda kv: (-kv[1], kv[0]),
        )),
    }

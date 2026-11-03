"""Gera o site estático a partir dos JSON coletados.

Uso: python -m monitor_politico.build [deputados.json] [senadores.json] [congresso.json] [pasta_saida]
"""

from __future__ import annotations

import json
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence, Union
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, select_autoescape

from monitor_politico import painel
from monitor_politico.models import Deputado, Senador

DEPUTADOS_PADRAO = Path("data/deputados.json")
SENADORES_PADRAO = Path("data/senadores.json")
CONGRESSO_PADRAO = Path("data/congresso.json")
SAIDA_PADRAO = Path("site")
FUSO = ZoneInfo("America/Sao_Paulo")
PACOTE = Path(__file__).parent

FONTE_CAMARA = ("Dados Abertos da Câmara dos Deputados", "https://dadosabertos.camara.leg.br/")
FONTE_SENADO = ("Dados Abertos do Senado Federal", "https://www12.senado.leg.br/dados-abertos")


def chave_alfabetica(texto: str) -> str:
    """Ordem alfabética ignorando acentos e maiúsculas ("Acácio" antes de "AJ")."""
    sem_acento = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def _formatar_data(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(FUSO).strftime("%d/%m/%Y às %H:%M (horário de Brasília)")


def _gerar_casa(
    env: Environment,
    pasta: Path,
    parlamentares: Sequence[Union[Deputado, Senador]],
    perfil: str,
    variavel: str,
    contexto: dict[str, Any],
) -> None:
    pasta.mkdir(parents=True)
    (pasta / "index.html").write_text(
        env.get_template("lista.html").render(
            **contexto,
            parlamentares=parlamentares,
            partidos=sorted({p.partido for p in parlamentares}),
            ufs=sorted({p.uf for p in parlamentares}),
        ),
        encoding="utf-8",
    )
    modelo = env.get_template(perfil)
    for p in parlamentares:
        (pasta / f"{p.id}.html").write_text(modelo.render(**contexto, **{variavel: p}), encoding="utf-8")


def construir(
    doc_deputados: dict[str, Any],
    doc_senadores: dict[str, Any],
    doc_congresso: dict[str, Any],
    saida: Path = SAIDA_PADRAO,
) -> None:
    env = Environment(
        loader=PackageLoader("monitor_politico", "templates"),
        autoescape=select_autoescape(),
    )
    env.filters["data_br"] = painel.data_br
    deputados = sorted((Deputado.de_dict(d) for d in doc_deputados["deputados"]), key=lambda d: chave_alfabetica(d.nome))
    senadores = sorted((Senador.de_dict(s) for s in doc_senadores["senadores"]), key=lambda s: chave_alfabetica(s.nome))
    atualizado_camara = _formatar_data(doc_deputados["coletado_em"])
    atualizado_senado = _formatar_data(doc_senadores["coletado_em"])

    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    shutil.copytree(PACOTE / "static", saida / "static")

    atualizado_congresso = _formatar_data(doc_congresso["coletado_em"])
    (saida / "index.html").write_text(
        env.get_template("inicio.html").render(
            raiz=".", casa="inicio", atualizado_congresso=atualizado_congresso, **painel.inicio(doc_congresso)
        ),
        encoding="utf-8",
    )
    (saida / "proposicoes").mkdir()
    modelo = env.get_template("proposicao.html")
    ids_deputados = {d.id for d in deputados}
    ids_senadores = {s.id for s in senadores}
    for prop in doc_congresso["proposicoes"].values():
        (saida / "proposicoes" / f"{prop['slug']}.html").write_text(
            modelo.render(
                raiz="..",
                casa=None,
                atualizado_congresso=atualizado_congresso,
                p=prop,
                etapas=painel.etapas(prop, doc_congresso["pauta"]),
                votacoes=painel.votacoes_da_pagina(prop, ids_deputados, ids_senadores),
            ),
            encoding="utf-8",
        )
    _gerar_casa(
        env, saida / "deputados", deputados, "perfil_deputado.html", "d",
        {"raiz": "..", "casa": "camara", "titulo": "Deputados federais", "singular": "deputado", "plural": "deputados",
         "atualizado_em": atualizado_camara, "fonte_nome": FONTE_CAMARA[0], "fonte_url": FONTE_CAMARA[1]},
    )
    _gerar_casa(
        env, saida / "senadores", senadores, "perfil_senador.html", "s",
        {"raiz": "..", "casa": "senado", "titulo": "Senadores", "singular": "senador", "plural": "senadores",
         "atualizado_em": atualizado_senado, "fonte_nome": FONTE_SENADO[0], "fonte_url": FONTE_SENADO[1]},
    )


if __name__ == "__main__":
    args = sys.argv[1:]
    entrada_dep = Path(args[0]) if len(args) > 0 else DEPUTADOS_PADRAO
    entrada_sen = Path(args[1]) if len(args) > 1 else SENADORES_PADRAO
    entrada_con = Path(args[2]) if len(args) > 2 else CONGRESSO_PADRAO
    destino = Path(args[3]) if len(args) > 3 else SAIDA_PADRAO
    doc_dep = json.loads(entrada_dep.read_text(encoding="utf-8"))
    doc_sen = json.loads(entrada_sen.read_text(encoding="utf-8"))
    doc_con = json.loads(entrada_con.read_text(encoding="utf-8"))
    construir(doc_dep, doc_sen, doc_con, destino)
    print(
        f"Site gerado em {destino}/ ({len(doc_dep['deputados'])} deputados, {len(doc_sen['senadores'])} senadores, "
        f"{len(doc_con['proposicoes'])} proposições)"
    )

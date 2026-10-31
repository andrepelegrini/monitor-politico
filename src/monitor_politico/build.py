"""Gera o site estático a partir do JSON coletado.

Uso: python -m monitor_politico.build [entrada.json] [pasta_saida]
"""

from __future__ import annotations

import json
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, select_autoescape

from monitor_politico.models import Deputado

ENTRADA_PADRAO = Path("data/deputados.json")
SAIDA_PADRAO = Path("site")
FUSO = ZoneInfo("America/Sao_Paulo")
PACOTE = Path(__file__).parent


def chave_alfabetica(texto: str) -> str:
    """Ordem alfabética ignorando acentos e maiúsculas ("Acácio" antes de "AJ")."""
    sem_acento = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
    return sem_acento.casefold()


def _formatar_data(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(FUSO).strftime("%d/%m/%Y às %H:%M (horário de Brasília)")


def construir(doc: dict[str, Any], saida: Path = SAIDA_PADRAO) -> None:
    env = Environment(
        loader=PackageLoader("monitor_politico", "templates"),
        autoescape=select_autoescape(),
    )
    deputados = sorted(
        (Deputado.de_dict(d) for d in doc["deputados"]),
        key=lambda d: chave_alfabetica(d.nome),
    )
    contexto = {
        "atualizado_em": _formatar_data(doc["coletado_em"]),
        "fonte": doc["fonte"],
    }

    if saida.exists():
        shutil.rmtree(saida)
    (saida / "deputados").mkdir(parents=True)
    shutil.copytree(PACOTE / "static", saida / "static")

    (saida / "index.html").write_text(
        env.get_template("lista.html").render(
            **contexto,
            raiz=".",
            deputados=deputados,
            partidos=sorted({d.partido for d in deputados}),
            ufs=sorted({d.uf for d in deputados}),
        ),
        encoding="utf-8",
    )
    perfil = env.get_template("perfil.html")
    for d in deputados:
        (saida / "deputados" / f"{d.id}.html").write_text(
            perfil.render(**contexto, raiz="..", d=d),
            encoding="utf-8",
        )


if __name__ == "__main__":
    entrada = Path(sys.argv[1]) if len(sys.argv) > 1 else ENTRADA_PADRAO
    destino = Path(sys.argv[2]) if len(sys.argv) > 2 else SAIDA_PADRAO
    doc = json.loads(entrada.read_text(encoding="utf-8"))
    construir(doc, destino)
    print(f"Site gerado em {destino}/ ({len(doc['deputados'])} perfis)")

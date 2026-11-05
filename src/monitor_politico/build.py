"""Gera o site estático a partir dos JSON coletados.

Uso: python -m monitor_politico.build [deputados.json] [senadores.json] [congresso.json] [pasta_saida]
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Sequence, Union
from zoneinfo import ZoneInfo

from jinja2 import Environment, PackageLoader, select_autoescape

from monitor_politico import painel, perfis, resumo
from monitor_politico.models import Deputado, Senador

DEPUTADOS_PADRAO = Path("data/deputados.json")
SENADORES_PADRAO = Path("data/senadores.json")
CONGRESSO_PADRAO = Path("data/congresso.json")
RESUMOS_PADRAO = Path("data/resumos.json")
PERFIS_PADRAO = Path("data/perfis")
SAIDA_PADRAO = Path("site")
FUSO = ZoneInfo("America/Sao_Paulo")
PACOTE = Path(__file__).parent

FONTE_CAMARA = ("Dados Abertos da Câmara dos Deputados", "https://dadosabertos.camara.leg.br/")
FONTE_SENADO = ("Dados Abertos do Senado Federal", "https://www12.senado.leg.br/dados-abertos")


def url_do_site(ambiente: Optional[dict[str, str]] = None) -> str:
    """Endereço público do site, usado nas tags de compartilhamento (Open Graph).

    SITE_URL tem prioridade; na Vercel, VERCEL_PROJECT_PRODUCTION_URL traz o domínio de produção
    sem o esquema. Sem nenhum dos dois (build local, testes), as tags com endereço absoluto ficam de fora.
    """
    ambiente = os.environ if ambiente is None else ambiente
    url = (ambiente.get("SITE_URL") or ambiente.get("VERCEL_PROJECT_PRODUCTION_URL") or "").strip().rstrip("/")
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def indice_de_busca(
    deputados: Sequence[Deputado], senadores: Sequence[Senador], proposicoes: dict[str, dict[str, Any]]
) -> dict[str, list[list[str]]]:
    """Índice compacto para a busca do topo: listas em vez de objetos, para o arquivo ficar pequeno."""
    pessoas = [[d.nome, "D", d.partido, d.uf, f"deputados/{d.id}.html"] for d in deputados]
    pessoas += [[s.nome, "S", s.partido, s.uf, f"senadores/{s.id}.html"] for s in senadores]
    pessoas.sort(key=lambda p: chave_alfabetica(p[0]))
    props = [
        [p["chave"], (p.get("resumo") or {}).get("titulo") or p.get("apelido") or p.get("ementa") or "", f"proposicoes/{p['slug']}.html"]
        for p in proposicoes.values()
    ]
    return {"parlamentares": pessoas, "proposicoes": props}


def numeros_do_periodo(doc_congresso: dict[str, Any]) -> dict[str, Any]:
    votacoes = [v for p in doc_congresso["proposicoes"].values() for v in p.get("votacoes", [])]
    desde = (doc_congresso.get("periodo") or {}).get("votacoes_desde")
    return {
        "votacoes": len(votacoes),
        "nominais": sum(1 for v in votacoes if v.get("nominal")),
        "proposicoes": sum(1 for p in doc_congresso["proposicoes"].values() if p.get("votacoes")),
        "desde": painel.data_br(desde) if desde else "",
    }


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
    perfis_ampliados: Optional[dict[int, dict[str, Any]]] = None,
) -> None:
    pasta.mkdir(parents=True)
    (pasta / "index.html").write_text(
        env.get_template("lista.html").render(
            **contexto,
            caminho=f"{pasta.name}/index.html",
            parlamentares=parlamentares,
            partidos=sorted({p.partido for p in parlamentares}),
            ufs=sorted({p.uf for p in parlamentares}),
        ),
        encoding="utf-8",
    )
    modelo = env.get_template(perfil)
    perfis_ampliados = perfis_ampliados or {}
    for p in parlamentares:
        caminho = f"{pasta.name}/{p.id}.html"
        ampliado = perfis_ampliados.get(p.id)
        if ampliado:
            pagina = env.get_template("perfil_ampliado.html").render(
                **contexto, caminho=caminho, **{variavel: p}, perfil=ampliado
            )
        else:
            pagina = modelo.render(**contexto, caminho=caminho, **{variavel: p})
        (pasta / f"{p.id}.html").write_text(pagina, encoding="utf-8")


def construir(
    doc_deputados: dict[str, Any],
    doc_senadores: dict[str, Any],
    doc_congresso: dict[str, Any],
    saida: Path = SAIDA_PADRAO,
    doc_resumos: Optional[dict[str, Any]] = None,
    site_url: Optional[str] = None,
    perfis_ampliados: Optional[dict[int, dict[str, Any]]] = None,
) -> None:
    env = Environment(
        loader=PackageLoader("monitor_politico", "templates"),
        autoescape=select_autoescape(),
    )
    env.filters["data_br"] = painel.data_br
    for nome in ("numero", "moeda", "milhoes", "percentual", "diferenca", "nome_proprio"):
        env.filters[nome] = getattr(perfis, nome)
    env.globals["site_url"] = url_do_site() if site_url is None else site_url.rstrip("/")
    deputados = sorted((Deputado.de_dict(d) for d in doc_deputados["deputados"]), key=lambda d: chave_alfabetica(d.nome))
    senadores = sorted((Senador.de_dict(s) for s in doc_senadores["senadores"]), key=lambda s: chave_alfabetica(s.nome))
    atualizado_camara = _formatar_data(doc_deputados["coletado_em"])
    atualizado_senado = _formatar_data(doc_senadores["coletado_em"])

    if saida.exists():
        shutil.rmtree(saida)
    saida.mkdir(parents=True)
    shutil.copytree(PACOTE / "static", saida / "static")

    atualizado_congresso = _formatar_data(doc_congresso["coletado_em"])
    resumos = (doc_resumos or {}).get("resumos", {})
    doc_congresso = {
        **doc_congresso,
        "proposicoes": {k: {**p, "resumo": resumos.get(k)} for k, p in doc_congresso["proposicoes"].items()},
    }
    (saida / "index.html").write_text(
        env.get_template("inicio.html").render(
            raiz=".", casa="inicio", caminho="index.html", atualizado_congresso=atualizado_congresso, **painel.inicio(doc_congresso)
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
                caminho=f"proposicoes/{prop['slug']}.html",
                atualizado_congresso=atualizado_congresso,
                p=prop,
                etapas=painel.etapas(prop, doc_congresso["pauta"]),
                votacoes=painel.votacoes_da_pagina(prop, ids_deputados, ids_senadores),
            ),
            encoding="utf-8",
        )
    (saida / "entenda.html").write_text(
        env.get_template("entenda.html").render(
            raiz=".", casa=None, caminho="entenda.html", atualizado_congresso=atualizado_congresso,
            numeros=numeros_do_periodo(doc_congresso), tem_resumos=bool(resumos),
        ),
        encoding="utf-8",
    )
    (saida / "static" / "busca.json").write_text(
        json.dumps(indice_de_busca(deputados, senadores, doc_congresso["proposicoes"]), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    slugs = {p["chave"]: p["slug"] for p in doc_congresso["proposicoes"].values()}
    visoes_ampliadas = {id_: perfis.visao(doc, slugs=slugs) for id_, doc in (perfis_ampliados or {}).items()}
    for id_, doc in (perfis_ampliados or {}).items():
        if doc.get("dinheiro"):
            pasta_perfis = saida / "static" / "perfis"
            pasta_perfis.mkdir(exist_ok=True)
            (pasta_perfis / f"{id_}-comprovantes.json").write_text(
                json.dumps(doc["dinheiro"]["cota"]["comprovantes"], ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
            )
    _gerar_casa(
        env, saida / "deputados", deputados, "perfil_deputado.html", "d",
        {"raiz": "..", "casa": "camara", "titulo": "Deputados federais", "singular": "deputado", "plural": "deputados",
         "nome_casa": "Câmara dos Deputados", "resumo": resumo.da_camara(deputados, doc_deputados.get("resumo") or {}),
         "atualizado_em": atualizado_camara, "fonte_nome": FONTE_CAMARA[0], "fonte_url": FONTE_CAMARA[1]},
        visoes_ampliadas,
    )
    _gerar_casa(
        env, saida / "senadores", senadores, "perfil_senador.html", "s",
        {"raiz": "..", "casa": "senado", "titulo": "Senadores", "singular": "senador", "plural": "senadores",
         "nome_casa": "Senado Federal", "resumo": resumo.do_senado(senadores, doc_senadores.get("resumo") or {}),
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
    # Os resumos por IA são opcionais: sem o arquivo, as páginas mostram só a ementa oficial.
    doc_res = json.loads(RESUMOS_PADRAO.read_text(encoding="utf-8")) if RESUMOS_PADRAO.exists() else None
    construir(doc_dep, doc_sen, doc_con, destino, doc_res, perfis_ampliados=perfis.ler_perfis(PERFIS_PADRAO))
    print(
        f"Site gerado em {destino}/ ({len(doc_dep['deputados'])} deputados, {len(doc_sen['senadores'])} senadores, "
        f"{len(doc_con['proposicoes'])} proposições)"
    )

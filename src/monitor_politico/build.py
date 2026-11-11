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

from monitor_politico import retrospectiva as modulo_retro
from monitor_politico import estados as modulo_estados, legislatura as modulo_legislatura, mapa as modulo_mapa, metricas as modulo_metricas, painel, perfis, resumo
from monitor_politico.lote_senado import ROTULOS_ELEITOS as ROTULOS_ELEITOS_SENADO
from monitor_politico.models import Deputado, Senador

DEPUTADOS_PADRAO = Path("data/deputados.json")
SENADORES_PADRAO = Path("data/senadores.json")
CONGRESSO_PADRAO = Path("data/congresso.json")
RESUMOS_PADRAO = Path("data/resumos.json")
PERFIS_PADRAO = Path("data/perfis")
METRICAS_PADRAO = Path("data/metricas_deputados.json")
LEGISLATURA_PADRAO = Path("data/legislatura.json")
ARQUIVO_PADRAO = Path("data/arquivo_deputados.json")
PERFIS_SENADO_PADRAO = PERFIS_PADRAO / "senado"
METRICAS_SENADO_PADRAO = Path("data/metricas_senadores.json")
LEGISLATURA_SENADO_PADRAO = Path("data/legislatura_senado.json")
ARQUIVO_SENADO_PADRAO = Path("data/arquivo_senadores.json")
HISTORICO_PADRAO = Path("data/historico.json")
NOME_DA_IMAGEM = "{id}-compartilhar.jpg"
PREFIXO_COMPROVANTE = "https://www.camara.leg.br/cota-parlamentar/documentos/publ/"
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
    deputados: Sequence[Deputado], senadores: Sequence[Senador], proposicoes: dict[str, dict[str, Any]],
    outros_deputados: Sequence[Deputado] = (), eleitos: Sequence[dict[str, Any]] = (),
    outros_senadores: Sequence[Senador] = (), eleitos_senado: Sequence[dict[str, Any]] = (),
) -> dict[str, list[list[str]]]:
    """Índice compacto para a busca do topo: listas em vez de objetos, para o arquivo ficar pequeno."""
    pessoas = [[d.nome, "D", d.partido, d.uf, f"deputados/{d.id}.html"] for d in list(deputados) + list(outros_deputados)]
    pessoas += [[perfis.nome_proprio(e["nome"]), "D", e["partido"], e["uf"], f"deputados/eleitos/{e['sq']}.html"] for e in eleitos]
    pessoas += [[s.nome, "S", s.partido, s.uf, f"senadores/{s.id}.html"] for s in list(senadores) + list(outros_senadores)]
    pessoas += [[perfis.nome_proprio(e["nome"]), "S", e["partido"], e["uf"], f"senadores/eleitos/{e['sq']}.html"] for e in eleitos_senado]
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
    perfis_ampliados: Any = None,
    slugs: Optional[dict[str, str]] = None,
    pasta_imagens: Optional[Path] = None,
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
    # Retrospectiva da legislatura: só para quem tem perfil completo e números na lista comparável.
    retro_ref = modulo_retro.referencias(contexto["metricas"], [p.id for p in parlamentares]) if contexto.get("metricas") and perfis_ampliados else None
    if retro_ref:
        (pasta / "retrospectiva").mkdir()
    for p in parlamentares:
        caminho = f"{pasta.name}/{p.id}.html"
        ampliado = perfis_ampliados.get(p.id)
        if ampliado:
            pagina = _gerar_perfil_ampliado(env, pasta.parent, p, ampliado, {**contexto, "caminho": caminho, "d": p}, slugs or {}, pasta_imagens, retro_ref, pasta)
        else:
            pagina = modelo.render(**contexto, caminho=caminho, **{variavel: p})
        (pasta / f"{p.id}.html").write_text(pagina, encoding="utf-8")


def _gerar_perfil_ampliado(
    env: Environment, saida: Path, deputado: Deputado, doc: dict[str, Any], contexto: dict[str, Any], slugs: dict[str, str], pasta_imagens: Optional[Path],
    retro_ref: Optional[dict[str, Any]] = None, pasta_casa: Optional[Path] = None,
) -> str:
    """Página do perfil completo e os arquivos com as listas longas, baixados só quando alguém as usa."""
    visao = perfis.visao(doc, slugs=slugs)
    # Deputados e senadores têm numerações independentes, então os arquivos do Senado levam um prefixo.
    arquivo = f"senado-{deputado.id}" if doc.get("casa") == "senado" else str(deputado.id)
    visao["arquivo"] = arquivo
    pasta = saida / "static" / "perfis"
    pasta.mkdir(exist_ok=True)
    imagem = (pasta_imagens / NOME_DA_IMAGEM.format(id=deputado.id)) if pasta_imagens else None
    visao["imagem"] = bool(imagem and imagem.exists())
    if visao["imagem"]:
        shutil.copyfile(imagem, pasta / NOME_DA_IMAGEM.format(id=arquivo))
    if visao.get("plenario"):
        (pasta / f"{arquivo}-votos.html").write_text(
            "".join(env.get_template("perfil_voto_item.html").render(raiz=contexto["raiz"], v=v) for v in visao["plenario"]["votos"]), encoding="utf-8"
        )
    if visao.get("propostas"):
        (pasta / f"{arquivo}-propostas.html").write_text(
            "".join(
                env.get_template("perfil_proposta_item.html").render(raiz=contexto["raiz"], p=p, palavra_norma=visao["propostas"]["palavra_norma"])
                for p in visao["propostas"]["propostas"]
            ),
            encoding="utf-8",
        )
    if doc.get("dinheiro"):
        (pasta / f"{arquivo}-comprovantes.json").write_text(
            json.dumps(comprovantes_compactos(doc["dinheiro"]["cota"]["comprovantes"]), ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
    if retro_ref and pasta_casa:
        visao["retrospectiva"] = True
        retro = modulo_retro.visao(visao, modulo_metricas.do_deputado(contexto["metricas"], deputado.id), retro_ref)
        situacao = (contexto.get("situacoes_eleitorais") or {}).get(str(deputado.id))
        (pasta_casa / "retrospectiva" / f"{deputado.id}.html").write_text(
            env.get_template("retrospectiva.html").render(
                **{**contexto, "raiz": "../..", "caminho": f"{pasta_casa.name}/retrospectiva/{deputado.id}.html"},
                perfil=visao, retro=retro, cartao=retro["cartao"], situacao=situacao,
            ),
            encoding="utf-8",
        )
    return env.get_template("perfil_ampliado.html").render(**contexto, perfil=visao)


def comprovantes_compactos(comprovantes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Listas em vez de objetos, e categorias e endereços abreviados: com 513 deputados, faz diferença."""
    categorias = sorted({c["categoria"] for c in comprovantes})
    indice = {nome: i for i, nome in enumerate(categorias)}
    itens = []
    for c in comprovantes:
        url = c["url"] or ""
        if url.startswith(PREFIXO_COMPROVANTE):
            url = url[len(PREFIXO_COMPROVANTE):]
        itens.append([c["mes"], indice[c["categoria"]], c["fornecedor"], c["valor"], url])
    return {"categorias": categorias, "prefixo": PREFIXO_COMPROVANTE, "itens": itens}


def _gerar_legislatura(
    env: Environment, pasta: Path, anteriores: Sequence[Deputado], saidas: dict[int, Optional[str]], legislatura: dict[str, Any],
    situacoes_eleitorais: dict[str, Any], contexto: dict[str, Any], perfis_ampliados: Any = None, slugs: Optional[dict[str, str]] = None,
    pasta_imagens: Optional[Path] = None, modelo_perfil: str = "perfil_deputado.html", variavel: str = "d", resumo_da_casa: Optional[dict[str, Any]] = None,
) -> None:
    """Páginas de quem saiu do exercício e de quem chega em 2027."""
    coleta = datetime.fromisoformat(legislatura["coletado_em"]).astimezone(FUSO).date().isoformat()
    comum = {**contexto, "legislatura": legislatura, "coleta_legislatura": coleta, "situacoes_eleitorais": situacoes_eleitorais}
    modelo = env.get_template(modelo_perfil)
    casa = pasta.name
    for d in anteriores:
        pagina = {**comum, "raiz": "..", "caminho": f"{casa}/{d.id}.html", variavel: d, "d": d, "fora_de_exercicio": True, "saiu_em": saidas.get(d.id)}
        # Quem saiu mantém o perfil completo que já tinha, com os dados do último registro.
        ampliado = perfis_ampliados.get(d.id) if perfis_ampliados else None
        conteudo = _gerar_perfil_ampliado(env, pasta.parent, d, ampliado, pagina, slugs or {}, pasta_imagens) if ampliado else modelo.render(**pagina)
        (pasta / f"{d.id}.html").write_text(conteudo, encoding="utf-8")
    (pasta / "anteriores.html").write_text(
        env.get_template("deputados_anteriores.html").render(
            **comum, raiz="..", caminho=f"{casa}/anteriores.html", arquivo=anteriores,
            partidos=sorted({d.partido for d in anteriores}), ufs=sorted({d.uf for d in anteriores}),
        ),
        encoding="utf-8",
    )
    eleitos = legislatura["eleitos_novos"]
    pasta_eleitos = pasta / "eleitos"
    pasta_eleitos.mkdir()
    (pasta_eleitos / "index.html").write_text(
        env.get_template("eleitos.html").render(
            **comum, raiz="../..", caminho=f"{casa}/eleitos/index.html", eleitos=eleitos,
            resumo_legislatura=resumo_da_casa or modulo_legislatura.resumo(legislatura),
            partidos=sorted({e["partido"] for e in eleitos}), ufs=sorted({e["uf"] for e in eleitos}),
        ),
        encoding="utf-8",
    )
    modelo_eleito = env.get_template("perfil_eleito.html")
    for e in eleitos:
        (pasta_eleitos / f"{e['sq']}.html").write_text(
            modelo_eleito.render(**comum, raiz="../..", caminho=f"{casa}/eleitos/{e['sq']}.html", e=e), encoding="utf-8"
        )


def construir(
    doc_deputados: dict[str, Any],
    doc_senadores: dict[str, Any],
    doc_congresso: dict[str, Any],
    saida: Path = SAIDA_PADRAO,
    doc_resumos: Optional[dict[str, Any]] = None,
    site_url: Optional[str] = None,
    perfis_ampliados: Any = None,
    metricas: Optional[dict[str, Any]] = None,
    legislatura: Optional[dict[str, Any]] = None,
    arquivo_deputados: Optional[list[dict[str, Any]]] = None,
    pasta_imagens: Optional[Path] = None,
    perfis_senado: Any = None,
    metricas_senado: Optional[dict[str, Any]] = None,
    legislatura_senado: Optional[dict[str, Any]] = None,
    arquivo_senadores: Optional[list[dict[str, Any]]] = None,
    pasta_imagens_senado: Optional[Path] = None,
    historico: Optional[dict[str, Any]] = None,
) -> None:
    env = Environment(
        loader=PackageLoader("monitor_politico", "templates"),
        autoescape=select_autoescape(),
    )
    env.filters["data_br"] = painel.data_br
    for nome in ("numero", "moeda", "milhoes", "percentual", "diferenca", "nome_proprio", "partir"):
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
    dados_inicio = painel.inicio(doc_congresso)
    # Projetos votados desde 2023 (coleta semanal): ganham página, entram na busca e na lista de votações.
    # A coleta diária, mais completa (voto de cada um, orientações), vale quando a mesma proposição está nas duas.
    doc_completo = doc_congresso
    if historico:
        antigas = {k: {**p, "resumo": resumos.get(k)} for k, p in historico["proposicoes"].items()}
        periodo = doc_congresso.get("periodo") or {}
        doc_completo = {
            **doc_congresso,
            "proposicoes": {**antigas, **doc_congresso["proposicoes"]},
            "periodo": {**periodo, "votacoes_desde": historico["desde"], "recentes_desde": periodo.get("votacoes_desde", historico["desde"])},
        }
    dados_votacoes = painel.inicio(doc_completo)
    dados_votacoes["anos_votadas"] = sorted({v["ano"] for v in dados_votacoes["votadas"]}, reverse=True)
    malha = modulo_mapa._malha()
    mapa_estados = [
        {"uf": uf, "slug": uf.lower(), "nome": forma["nome"], "d": forma["d"], "rotulo": forma["rotulo"]}
        for uf, forma in sorted(malha["estados"].items(), key=lambda kv: -len(kv[1]["d"]))
    ]
    (saida / "index.html").write_text(
        env.get_template("inicio.html").render(
            raiz=".", casa="inicio", caminho="index.html", atualizado_congresso=atualizado_congresso, **dados_inicio,
            mapa_estados=mapa_estados, mapa_dim=(malha["largura"], malha["altura"]),
        ),
        encoding="utf-8",
    )
    (saida / "votacoes.html").write_text(
        env.get_template("votacoes.html").render(
            raiz=".", casa=None, caminho="votacoes.html", atualizado_congresso=atualizado_congresso, **dados_votacoes
        ),
        encoding="utf-8",
    )
    (saida / "proposicoes").mkdir()
    modelo = env.get_template("proposicao.html")
    # Quem saiu mantém a página, então o voto continua ligado ao perfil na página da proposição.
    saidas = {d["id"]: d.get("saiu_em") for d in (arquivo_deputados or [])}
    ids_em_exercicio = {d.id for d in deputados}
    anteriores = sorted(
        (Deputado.de_dict({k: v for k, v in d.items() if k != "saiu_em"}) for d in (arquivo_deputados or []) if d["id"] not in ids_em_exercicio),
        key=lambda d: chave_alfabetica(d.nome),
    )
    eleitos = (legislatura or {}).get("eleitos_novos", [])
    situacoes_eleitorais = (legislatura or {}).get("situacoes", {})
    ids_deputados = ids_em_exercicio | {d.id for d in anteriores}
    saidas_senado = {s["id"]: s.get("saiu_em") for s in (arquivo_senadores or [])}
    ids_senado_em_exercicio = {s.id for s in senadores}
    senadores_anteriores = sorted(
        (Senador.de_dict({k: v for k, v in s.items() if k != "saiu_em"}) for s in (arquivo_senadores or []) if s["id"] not in ids_senado_em_exercicio),
        key=lambda s: chave_alfabetica(s.nome),
    )
    eleitos_senado = (legislatura_senado or {}).get("eleitos_novos", [])
    situacoes_senado = (legislatura_senado or {}).get("situacoes", {})
    ids_senadores = ids_senado_em_exercicio | {s.id for s in senadores_anteriores}
    for prop in doc_completo["proposicoes"].values():
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
        json.dumps(indice_de_busca(deputados, senadores, doc_completo["proposicoes"], anteriores, eleitos, senadores_anteriores, eleitos_senado), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    slugs = {p["chave"]: p["slug"] for p in doc_completo["proposicoes"].values()}
    # Deputado sem registro nas métricas é parte da coleta só se ela existir; o template trata a ausência.
    leis_na_lista = {d.id: modulo_metricas.do_deputado(metricas, d.id) for d in deputados} if metricas else None
    _gerar_casa(
        env, saida / "deputados", deputados, "perfil_deputado.html", "d",
        {"raiz": "..", "casa": "camara", "titulo": "Deputados federais", "singular": "deputado", "plural": "deputados",
         "nome_casa": "Câmara dos Deputados", "resumo": resumo.da_camara(deputados, doc_deputados.get("resumo") or {}),
         "atualizado_em": atualizado_camara, "fonte_nome": FONTE_CAMARA[0], "fonte_url": FONTE_CAMARA[1],
         "leis_na_lista": leis_na_lista, "metricas": metricas, "situacoes_eleitorais": situacoes_eleitorais,
         "tem_legislatura": bool(legislatura), "total_anteriores": len(anteriores), "total_eleitos_novos": len(eleitos)},
        perfis_ampliados,
        slugs,
        pasta_imagens,
    )
    if legislatura:
        _gerar_legislatura(
            env, saida / "deputados", anteriores, saidas, legislatura, situacoes_eleitorais,
            {"casa": "camara", "atualizado_em": atualizado_camara, "fonte_nome": FONTE_CAMARA[0], "fonte_url": FONTE_CAMARA[1], "singular": "deputado", "plural": "deputados", "nome_casa": "Câmara dos Deputados"},
            perfis_ampliados, slugs, pasta_imagens,
        )
    _gerar_casa(
        env, saida / "senadores", senadores, "perfil_senador.html", "s",
        {"raiz": "..", "casa": "senado", "titulo": "Senadores", "singular": "senador", "plural": "senadores",
         "nome_casa": "Senado Federal", "resumo": resumo.do_senado(senadores, doc_senadores.get("resumo") or {}),
         "atualizado_em": atualizado_senado, "fonte_nome": FONTE_SENADO[0], "fonte_url": FONTE_SENADO[1],
         "leis_na_lista": {s.id: modulo_metricas.do_deputado(metricas_senado, s.id) for s in senadores} if metricas_senado else None,
         "metricas": metricas_senado, "situacoes_eleitorais": situacoes_senado,
         "tem_legislatura": bool(legislatura_senado), "total_anteriores": len(senadores_anteriores), "total_eleitos_novos": len(eleitos_senado)},
        perfis_senado,
        slugs,
        pasta_imagens_senado,
    )
    (saida / "estados").mkdir()
    modelo_estado = env.get_template("estado.html")
    por_uf = modulo_estados.por_estado(deputados, senadores, metricas, legislatura, metricas_senado, legislatura_senado)
    for uf, contexto_uf in por_uf.items():
        (saida / "estados" / f"{contexto_uf['slug']}.html").write_text(
            modelo_estado.render(
                raiz="..", casa=None, caminho=f"estados/{contexto_uf['slug']}.html", e=contexto_uf,
                atualizado_camara=atualizado_camara, atualizado_senado=atualizado_senado,
                inicio_mandato=(metricas or {}).get("inicio") or modulo_metricas.INICIO_MANDATO,
            ),
            encoding="utf-8",
        )
    if legislatura_senado:
        _gerar_legislatura(
            env, saida / "senadores", senadores_anteriores, saidas_senado, legislatura_senado, situacoes_senado,
            {"casa": "senado", "atualizado_em": atualizado_senado, "fonte_nome": FONTE_SENADO[0], "fonte_url": FONTE_SENADO[1], "singular": "senador", "plural": "senadores", "nome_casa": "Senado Federal"},
            perfis_senado, slugs, pasta_imagens_senado, "perfil_senador.html", "s",
            modulo_legislatura.resumo(legislatura_senado, ("reeleicao", "retorno", "camara", "primeiro"), ROTULOS_ELEITOS_SENADO),
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
    construir(
        doc_dep, doc_sen, doc_con, destino, doc_res, perfis_ampliados=perfis.PerfisEmDisco(PERFIS_PADRAO), pasta_imagens=PERFIS_PADRAO,
        metricas=modulo_metricas.ler(METRICAS_PADRAO),
        legislatura=modulo_legislatura.ler(LEGISLATURA_PADRAO),
        arquivo_deputados=(modulo_legislatura.ler(ARQUIVO_PADRAO) or {}).get("deputados"),
        perfis_senado=perfis.PerfisEmDisco(PERFIS_SENADO_PADRAO), pasta_imagens_senado=PERFIS_SENADO_PADRAO,
        metricas_senado=modulo_metricas.ler(METRICAS_SENADO_PADRAO),
        legislatura_senado=modulo_legislatura.ler(LEGISLATURA_SENADO_PADRAO),
        arquivo_senadores=(modulo_legislatura.ler(ARQUIVO_SENADO_PADRAO) or {}).get("senadores"),
        historico=modulo_legislatura.ler(HISTORICO_PADRAO),
    )
    print(
        f"Site gerado em {destino}/ ({len(doc_dep['deputados'])} deputados, {len(doc_sen['senadores'])} senadores, "
        f"{len(doc_con['proposicoes'])} proposições)"
    )

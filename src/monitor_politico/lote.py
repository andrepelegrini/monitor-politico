"""Coleta do perfil completo de todos os deputados em exercício, numa passada só.

Os arquivos anuais são lidos uma vez e distribuídos entre as pessoas. O que não muda fica em cache e
vai junto no pacote de dados (veja pacote.py): anos passados das páginas oficiais, número de cada lei
e eleições. O CPF liga a Câmara ao TSE e fica só em memória.

Uma falha isolada mantém o dado anterior da pessoa. Falha em massa interrompe a coleta, porque o mais
provável é que uma página oficial tenha mudado de formato, e o site continua com o pacote anterior.

Uso: python -m monitor_politico.lote [--somente 204534,74856]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

from monitor_politico import dinheiro, legislatura, metricas, perfis, plenario, propostas
from monitor_politico.camara import ClienteCamara
from monitor_politico.plenario import RelatorioInvalido

PASTA_PADRAO = Path("data/perfis")
ARQUIVO_CACHE = "_cache/cache.json"
TRABALHADORES = 4
TAMANHO_DO_BLOCO = 200
LIMITE_DE_FALHAS = 0.2  # Fração de pessoas que pode falhar numa etapa antes de abortar a coleta.
ANOS_ELEICOES = perfis.ELEICOES


class ColetaInterrompida(RuntimeError):
    pass


def ler_cache(pasta: Path) -> dict[str, Any]:
    caminho = pasta / ARQUIVO_CACHE
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return {"normas": {}, "presenca": {}, "pagina": {}, "eleicoes": {}}


def salvar_cache(pasta: Path, cache: dict[str, Any]) -> None:
    caminho = pasta / ARQUIVO_CACHE
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporario.replace(caminho)


def em_paralelo(funcao: Callable[[Any], Any], itens: Iterable[Any]) -> list[Any]:
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
        return list(executor.map(funcao, itens))


def dados_da_camara(camara: Any, id_: int, hoje: date) -> dict[str, Any]:
    detalhe = camara._get(f"/deputados/{id_}")["dados"]
    historico = camara._get(f"/deputados/{id_}/historico")["dados"]
    orgaos = list(camara._paginar(f"/deputados/{id_}/orgaos", {"itens": 100, "ordem": "DESC", "ordenarPor": "dataInicio"}))
    return {
        "cpf": detalhe.get("cpf"),
        "nome": (detalhe.get("ultimoStatus") or {}).get("nomeEleitoral") or detalhe.get("nomeCivil") or "",
        "trajetoria": perfis.trajetoria(historico),
        "comissoes": perfis.comissoes_atuais(orgaos, hoje),
    }


def _com_tolerancia(funcao: Callable[[int], Any], ids: list[int], rotulo: str, anteriores: Optional[dict[int, Any]] = None) -> dict[int, Any]:
    """Roda por pessoa. Quem falha fica com o dado anterior; falha demais interrompe tudo."""
    def tentar(id_: int) -> tuple[int, Any, Optional[Exception]]:
        try:
            return id_, funcao(id_), None
        except (httpx.HTTPError, RelatorioInvalido, KeyError, ValueError) as erro:
            return id_, None, erro

    resultado, falhas = {}, []
    for id_, valor, erro in em_paralelo(tentar, ids):
        if erro is None:
            resultado[id_] = valor
        else:
            falhas.append(id_)
            print(f"aviso: {rotulo} de {id_} falhou ({erro})", file=sys.stderr)
            if anteriores and id_ in anteriores:
                resultado[id_] = anteriores[id_]
    if len(falhas) > LIMITE_DE_FALHAS * len(ids):
        raise ColetaInterrompida(f"{rotulo}: {len(falhas)} de {len(ids)} falharam")
    return resultado


def paginas_oficiais(
    financas: Any, arquivos: Any, ids: list[int], anos_por_pessoa: dict[int, list[int]], cache: dict[str, Any], ano_atual: int,
    salvar: Callable[[], None] = lambda: None,
) -> None:
    """Preenche o cache com as páginas da Câmara. Ano passado não muda, então só o ano atual é consultado de novo.

    Ano sem exercício não tem quadro na página: fica registrado como None e não conta como falha.
    """
    pendencias = []
    for id_ in ids:
        chave = str(id_)
        for ano in anos_por_pessoa[id_]:
            if ano == ano_atual or str(ano) not in cache["pagina"].get(chave, {}):
                pendencias.append(("pagina", id_, ano))
            if ano >= anos_por_pessoa[id_][-1] - 7 and (ano == ano_atual or str(ano) not in cache["presenca"].get(chave, {})):
                pendencias.append(("presenca", id_, ano))

    def consultar(pendencia: tuple[str, int, int]) -> tuple[str, int, int, Any, Optional[Exception]]:
        tipo, id_, ano = pendencia
        try:
            if tipo == "presenca":
                try:
                    return tipo, id_, ano, arquivos.relatorio_de_presenca(id_, ano), None
                except RelatorioInvalido:
                    return tipo, id_, ano, None, None
            pagina = financas.pagina_do_deputado(id_, ano)
            valor: dict[str, Any] = {}
            for nome, leitor in (("cota", dinheiro.ler_cota_da_pagina), ("atuacao", plenario.ler_atuacao_da_pagina)):
                try:
                    valor[nome] = leitor(pagina)
                except RelatorioInvalido:
                    valor[nome] = None
            return tipo, id_, ano, valor, None
        except httpx.HTTPError as erro:
            return tipo, id_, ano, None, erro

    falhas = 0
    # Em blocos, guardando o progresso: a primeira carga são milhares de páginas.
    for inicio_bloco in range(0, len(pendencias), TAMANHO_DO_BLOCO):
        for tipo, id_, ano, valor, erro in em_paralelo(consultar, pendencias[inicio_bloco:inicio_bloco + TAMANHO_DO_BLOCO]):
            if erro is not None:
                falhas += 1
                print(f"aviso: {tipo} {id_}/{ano} falhou ({erro})", file=sys.stderr)
                continue
            cache[tipo].setdefault(str(id_), {})[str(ano)] = valor
        salvar()
        print(f"páginas oficiais: {min(inicio_bloco + TAMANHO_DO_BLOCO, len(pendencias))} de {len(pendencias)}", file=sys.stderr, flush=True)
    if pendencias and falhas > LIMITE_DE_FALHAS * len(pendencias):
        raise ColetaInterrompida(f"páginas oficiais: {falhas} de {len(pendencias)} falharam")
    # Quadro ausente para quase todos no ano atual indica mudança de formato, não falta de exercício.
    sem_quadro = sum(1 for id_ in ids if not (cache["pagina"].get(str(id_), {}).get(str(ano_atual)) or {}).get("cota"))
    if len(ids) >= 10 and sem_quadro > 0.5 * len(ids):
        raise ColetaInterrompida(f"página do deputado sem o quadro da cota para {sem_quadro} de {len(ids)}")


def eleicoes_de_todos(tse: Any, cpfs: dict[int, str]) -> dict[int, list[dict[str, Any]]]:
    resultado: dict[int, list[dict[str, Any]]] = {i: [] for i in cpfs}
    por_cpf = {cpf: id_ for id_, cpf in cpfs.items() if cpf}
    for ano in ANOS_ELEICOES:
        candidaturas: dict[str, tuple[int, dict[str, str]]] = {}
        for linha in tse.candidatos(ano):
            id_ = por_cpf.get(linha["NR_CPF_CANDIDATO"])
            if id_ is not None and linha["DS_CARGO"].upper() == perfis.CARGO_DEPUTADO:
                candidaturas[linha["SQ_CANDIDATO"]] = (id_, linha)
        votos = legislatura.votos_por_candidatura(tse.votacao(ano, "BRASIL"), set(candidaturas))
        bens: dict[str, list[dict[str, str]]] = defaultdict(list)
        for linha in tse.bens(ano):
            if linha["SQ_CANDIDATO"] in candidaturas:
                bens[linha["SQ_CANDIDATO"]].append(linha)
        for sq, (id_, linha) in candidaturas.items():
            registro = votos.get(sq, {"votos": 0, "total_municipios": 0, "municipios": []})
            resultado[id_].append({
                "ano": ano,
                "partido": linha["SG_PARTIDO"],
                "uf": linha["SG_UF"],
                "situacao": linha["DS_SIT_TOT_TURNO"],
                "votos": registro["votos"],
                "total_municipios": registro.get("total_municipios", 0),
                "municipios": registro.get("municipios", []),
                "bens": perfis.bens_declarados(bens[sq], sq),
            })
    return resultado


def montar_documentos(
    ids: list[int], pessoas: dict[int, dict[str, Any]], leg: dict[str, Any], cache: dict[str, Any], votos: dict[int, Any], outros: dict[int, dict[int, int]],
    lista_propostas: dict[int, list[dict[str, Any]]], cotas: dict[int, Any], emendas: dict[int, Any], arquivo_emendas: str,
    anos_por_pessoa: dict[int, list[int]], inicios: dict[int, str], anos_mandato: list[int], coletado_em: str,
) -> dict[int, dict[str, Any]]:
    documentos = {}
    for id_ in ids:
        chave = str(id_)
        pessoa = pessoas[id_]
        presencas = []
        for ano in anos_mandato:
            relatorio = cache["presenca"].get(chave, {}).get(str(ano))
            if relatorio:
                presencas.append({"ano": ano, **relatorio, "outros_eventos": outros.get(id_, {}).get(ano, 0)})
        cota = dict(cotas[id_])
        detalhado = cota.pop("detalhado_por_ano")
        por_ano_cota = []
        for ano in anos_mandato:
            oficial = (cache["pagina"].get(chave, {}).get(str(ano)) or {}).get("cota")
            if oficial or detalhado.get(ano):
                por_ano_cota.append({"ano": ano, **(oficial or {"total": detalhado[ano], "percentual": None, "nao_utilizado": None}), "detalhado": detalhado.get(ano, 0)})
        atuacao = []
        for ano in anos_por_pessoa[id_]:
            quadro = (cache["pagina"].get(chave, {}).get(str(ano)) or {}).get("atuacao")
            if quadro:
                atuacao.append({"ano": ano, **quadro})
        documentos[id_] = {
            "id": id_,
            "coletado_em": coletado_em,
            "legislatura_atual": leg,
            "eleicoes": cache["eleicoes"].get(chave, []),
            "trajetoria": pessoa["trajetoria"],
            "comissoes": pessoa["comissoes"],
            "plenario": {"votos": votos[id_], "presenca": {"por_ano": presencas}},
            "propostas": {"inicio": inicios[id_], "por_ano": atuacao, "propostas": lista_propostas[id_]},
            "dinheiro": {"cota": {"por_ano": por_ano_cota, **cota}, "emendas": {**emendas.get(id_, dinheiro.emendas_de_todos([], [], {"": 0}, 0)[0]), "arquivo_em": arquivo_emendas}},
        }
    return documentos


def metricas_dos_documentos(documentos: dict[int, dict[str, Any]], inicio: str, coletado_em: str) -> dict[str, Any]:
    """Os números da lista de deputados. As leis contam pela data em que a norma saiu, com o mesmo critério para todos."""
    por_deputado: dict[str, dict[str, Any]] = {}
    for id_, doc in documentos.items():
        plenario_doc = doc.get("plenario") or {}
        presencas = (plenario_doc.get("presenca") or {}).get("por_ano", [])
        por_deputado[str(id_)] = {
            "principal": 0,
            "coautoria": 0,
            "votos": (plenario_doc.get("votos") or {}).get("votos_registrados", 0),
            "presencas": sum(a["presencas"] for a in presencas),
            "dias": sum(a["dias"] for a in presencas),
            "relatorias": doc["propostas"].get("relatorias_no_mandato", 0),
        }
    normas: dict[str, dict[str, Any]] = {}
    for id_, doc in documentos.items():
        for proposta in doc["propostas"]["propostas"]:
            norma = proposta.get("norma")
            if not norma or norma["data"] < inicio or proposta["participacao"] == "apoio":
                continue
            campo = "principal" if proposta["participacao"] == "primeira" else "coautoria"
            por_deputado[str(id_)][campo] += 1
            registro = normas.setdefault(proposta["id"], {"id": proposta["id"], "sigla": proposta["sigla"], "norma": norma["nome"], "data": norma["data"], "principal": [], "coautoria": []})
            registro[campo].append(str(id_))
    return {
        "coletado_em": coletado_em,
        "inicio": inicio,
        "normas": sorted(normas.values(), key=lambda n: (n["data"], n["id"]), reverse=True),
        "por_deputado": por_deputado,
    }


def coletar(
    ids: list[int], camara: Any, arquivos: Any, financas: Any, tse: Any, pasta: Path, hoje: Optional[date] = None,
    avisar: Callable[[str], None] = lambda msg: print(msg, file=sys.stderr, flush=True),
) -> dict[int, dict[str, Any]]:
    hoje = hoje or date.today()
    pasta.mkdir(parents=True, exist_ok=True)
    cache = ler_cache(pasta)
    coletado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")

    dados = camara._get(f"/legislaturas/{legislatura.LEGISLATURA_ATUAL}")["dados"]
    dados = dados[0] if isinstance(dados, list) else dados
    leg = {"id": dados["id"], "inicio": dados["dataInicio"][:10], "fim": dados["dataFim"][:10]}
    anos_mandato = list(range(int(leg["inicio"][:4]), hoje.year + 1))

    avisar(f"Dados de cada parlamentar na Câmara: {len(ids)}")
    pessoas = _com_tolerancia(lambda i: dados_da_camara(camara, i, hoje), ids, "cadastro")
    ids = [i for i in ids if i in pessoas]
    inicios, anos_por_pessoa = {}, {}
    for id_ in ids:
        posses = [e["data"] for e in pessoas[id_]["trajetoria"] if e["tipo"] == "posse"]
        inicios[id_] = min(posses) if posses else leg["inicio"]
        anos_por_pessoa[id_] = list(range(max(int(inicios[id_][:4]), metricas.ANO_MAIS_ANTIGO), hoje.year + 1))

    avisar("Páginas oficiais da Câmara")
    paginas_oficiais(financas, arquivos, ids, anos_por_pessoa, cache, hoje.year, lambda: salvar_cache(pasta, cache))

    faltam_eleicoes = {i: pessoas[i]["cpf"] for i in ids if str(i) not in cache["eleicoes"]}
    if faltam_eleicoes:
        avisar(f"Eleições no TSE: {len(faltam_eleicoes)}")
        for id_, eleicoes in eleicoes_de_todos(tse, faltam_eleicoes).items():
            cache["eleicoes"][str(id_)] = eleicoes
        salvar_cache(pasta, cache)

    avisar("Votos e presença")
    votos = plenario.votos_de_todos(arquivos, ids, leg["inicio"], anos_mandato)
    outros = plenario.outros_eventos_de_todos(arquivos, ids, leg["inicio"], anos_mandato)

    avisar("Propostas e leis")
    def consultar_norma(id_proposta: str) -> Optional[dict[str, Any]]:
        if id_proposta not in cache["normas"]:
            cache["normas"][id_proposta] = propostas.norma_da_tramitacao(camara._get(f"/proposicoes/{id_proposta}/tramitacoes")["dados"])
        return cache["normas"][id_proposta]
    ano_mais_antigo = min(anos_por_pessoa[i][0] for i in ids)
    relatorias: Counter[int] = Counter()
    lista_propostas = propostas.propostas_de_todos(arquivos, consultar_norma, inicios, range(ano_mais_antigo, hoje.year + 1), relatorias, leg["inicio"])
    salvar_cache(pasta, cache)

    avisar("Cota parlamentar e emendas")
    cotas = dinheiro.cota_de_todos(financas, ids, leg["id"], anos_mandato)
    autores = {dinheiro.nome_de_autor(pessoas[i]["nome"]): i for i in ids}
    emendas = dinheiro.emendas_de_todos(financas.emendas(), financas.favorecidos(), autores, anos_mandato[0])
    sem_emenda = [pessoas[i]["nome"] for i in ids if not emendas[i]["por_ano"]] if len(ids) >= 10 else []
    if sem_emenda:
        avisar(f"Sem emendas encontradas pelo nome: {len(sem_emenda)} ({', '.join(sem_emenda[:25])})")

    documentos = montar_documentos(
        ids, pessoas, leg, cache, votos, outros, lista_propostas, cotas, emendas, financas.data_das_emendas(),
        anos_por_pessoa, inicios, anos_mandato, coletado_em,
    )
    for id_, documento in documentos.items():
        documento["propostas"]["relatorias_no_mandato"] = relatorias[id_]
    for id_, documento in documentos.items():
        (pasta / f"{id_}.json").write_text(json.dumps(documento, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    return documentos


if __name__ == "__main__":
    entrada = argparse.ArgumentParser()
    entrada.add_argument("--somente", help="ids separados por vírgula, para conferência")
    entrada.add_argument("--pasta", default=str(PASTA_PADRAO))
    argumentos = entrada.parse_args()
    if argumentos.somente:
        lista_ids = [int(i) for i in argumentos.somente.split(",")]
    else:
        lista_ids = [d["id"] for d in json.loads(metricas.DEPUTADOS_PADRAO.read_text(encoding="utf-8"))["deputados"]]
    resultado_final = coletar(lista_ids, ClienteCamara(), plenario.ArquivosCamara(), dinheiro.FonteDinheiro(), perfis.FonteTSE(), Path(argumentos.pasta))
    if not argumentos.somente:
        numeros = metricas_dos_documentos(resultado_final, metricas.INICIO_MANDATO, datetime.now(timezone.utc).isoformat(timespec="seconds"))
        metricas.SAIDA_PADRAO.write_text(json.dumps(numeros, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(resultado_final)} perfis em {argumentos.pasta}")

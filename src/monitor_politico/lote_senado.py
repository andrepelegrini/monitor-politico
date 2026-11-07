"""Coleta do perfil completo de todos os senadores em exercício, e de quem chega em 2027.

O Senado publica de outro jeito, então a coleta é própria, mas o resultado segue o formato dos perfis
da Câmara e usa as mesmas páginas. As diferenças aparecem na página:
- Não há relatório de presença por senador. Em seu lugar, a participação nas votações nominais.
- Votação secreta registra só que a pessoa votou. Ela conta na participação, não na lista de votos.
- O Senado não publica a orientação dos partidos.
- A API não traz CPF. A ligação com o TSE é pela data de nascimento e pelo nome, então só afirmamos
  que alguém não foi candidato quando as duas formas de busca concordam.

Uso: python -m monitor_politico.lote_senado
"""

from __future__ import annotations

import csv
import io
import json
import re
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

from monitor_politico import dinheiro, legislatura, metricas, perfis, propostas
from monitor_politico.congresso import _temas_senado, eh_procedimento
from monitor_politico.models import Senador, como_lista
from monitor_politico.plenario import limpar_texto
from monitor_politico.senado import ClienteSenado

PASTA_PADRAO = Path("data/perfis/senado")
METRICAS_PADRAO = Path("data/metricas_senadores.json")
SENADORES_PADRAO = Path("data/senadores.json")
ARQUIVO_PADRAO = Path("data/arquivo_senadores.json")
ELEITOS_PADRAO = Path("data/legislatura_senado.json")
LEGISLATURA_CAMARA_PADRAO = Path("data/legislatura.json")
ARQUIVO_CACHE = "_cache/cache.json"
URL_CEAPS = "https://www.senado.leg.br/transparencia/LAI/verba/despesa_ceaps_{ano}.csv"
URL_MATERIA = "https://www25.senado.leg.br/web/atividade/materias/-/materia/{codigo}"
TRABALHADORES = 4
LIMITE_DE_FALHAS = 0.2
ANOS_ELEICOES = (2018, 2022, 2026)
PRIMEIRA_LEGISLATURA_CONSULTADA = 40
CARGO_SENADOR = "SENADOR"
CARGOS_DO_HISTORICO = (CARGO_SENADOR, perfis.CARGO_DEPUTADO)
TIPOS_DE_RELATORIA = ("PL", "PLP", "PEC", "MPV", "PDL", "PRS")

# Votos em aberto. "Votou" é o registro da votação secreta.
VOTOS_ABERTOS = ("Sim", "Não", "Abstenção")
VOTO_SECRETO = "Votou"
PRESIDENTE = "Presidente (art. 51 RISF)"
PRESENTE_SEM_VOTO = "P-NRV"
AFASTAMENTOS = ("AP", "LS", "LP", "LAP", "MIS")
NAO_COMPARECEU = "NCom"
FORA_DA_CONTA = ("NA",)  # "Dispositivo não citado": o senador não votava naquele destaque.

CATEGORIAS_CEAPS = (
    ("Locomoção", "Locomoção, hospedagem e alimentação"),
    ("Aluguel", "Aluguel de escritório político"),
    ("Passagens", "Passagens"),
    ("Contratação", "Consultorias e assessorias"),
    ("Aquisição", "Material e serviços de escritório"),
    ("Divulgação", "Divulgação da atividade parlamentar"),
    ("Serviços de Segurança", "Segurança privada"),
)
PALAVRAS_VAZIAS = legislatura.PALAVRAS_VAZIAS | {"DR", "DRA", "SENADOR", "SENADORA", "FILHO", "NETO", "JUNIOR", "SOBRINHO", "SEGUNDO"}

ROTULOS_ELEITOS = {"primeiro": "Primeiro mandato no Senado", "retorno": "Retorno ao Senado", "camara": "Chega da Câmara"}


class ColetaInterrompida(RuntimeError):
    pass


def tokens(nome: str) -> set[str]:
    return set(legislatura.normalizar(nome).split()) - PALAVRAS_VAZIAS


def ligar_nomes(pessoas: dict[int, str], nomes_da_fonte: Iterable[str]) -> dict[str, int]:
    """Liga os nomes de uma fonte aos senadores. Nome exato, senão nome contido no outro, desde que sem ambiguidade."""
    exatos = {legislatura.normalizar(nome): id_ for id_, nome in pessoas.items()}
    conjuntos = {id_: tokens(nome) for id_, nome in pessoas.items()}
    ligados = {}
    for original in set(nomes_da_fonte):
        limpo = original.split("(")[0]
        normalizado = legislatura.normalizar(limpo)
        if normalizado in exatos:
            ligados[original] = exatos[normalizado]
            continue
        alvo = tokens(limpo)
        candidatos = [id_ for id_, conjunto in conjuntos.items() if alvo and conjunto and (alvo <= conjunto or conjunto <= alvo)]
        if len(candidatos) == 1:
            ligados[original] = candidatos[0]
    return ligados


def participacao_nas_votacoes(votacoes: Iterable[dict[str, Any]], ids: Iterable[int], inicio: str) -> dict[int, dict[str, Any]]:
    """Por ano e por senador. Só entra no total a votação em que a pessoa aparece na relação oficial."""
    alvo = set(ids)
    por_pessoa: dict[int, dict[str, Counter[str]]] = {i: {} for i in alvo}
    for votacao in votacoes:
        data = votacao["dataSessao"][:10]
        if data < inicio:
            continue
        for voto in votacao.get("votos") or []:
            id_ = voto["codigoParlamentar"]
            sigla = voto["siglaVotoParlamentar"]
            if id_ not in alvo or sigla in FORA_DA_CONTA:
                continue
            contagem = por_pessoa[id_].setdefault(data[:4], Counter())
            contagem["votacoes"] += 1
            if sigla in VOTOS_ABERTOS or sigla in (VOTO_SECRETO, PRESIDENTE):
                contagem["votou"] += 1
            elif sigla == PRESENTE_SEM_VOTO:
                contagem["presente_sem_voto"] += 1
            elif sigla in AFASTAMENTOS:
                contagem["afastamento"] += 1
            elif sigla == NAO_COMPARECEU:
                contagem["nao_compareceu"] += 1
    resultado = {}
    for id_, anos in por_pessoa.items():
        linhas = [{"ano": int(ano), **{c: anos[ano][c] for c in ("votacoes", "votou", "presente_sem_voto", "afastamento", "nao_compareceu")}} for ano in sorted(anos)]
        resultado[id_] = {"por_ano": linhas}
    return resultado


def classe_da_votacao_senado(descricao: str) -> str:
    """Pela descrição oficial: "procedimento", "texto" (principal) ou "ajuste" (emendas, destaques e trechos)."""
    if eh_procedimento(descricao):
        return "procedimento"
    if re.search(r"Votação nominal (d[oa]s? )?(Emendas?|Destaques?|Art\.|art\.|§|expressões|Parágrafo|Inciso|dispositivos)", descricao):
        return "ajuste"
    return "texto"


def votos_em_aberto(votacoes: Iterable[dict[str, Any]], ids: Iterable[int], inicio: str, consultar_temas: Callable[[str], list[str]]) -> dict[int, dict[str, Any]]:
    """Votos abertos de cada senador, com o placar dos demais. Só o voto do próprio parlamentar é guardado."""
    alvo = set(ids)
    registros: dict[int, list[dict[str, Any]]] = {i: [] for i in alvo}
    procedimento: dict[int, Counter[str]] = {i: Counter() for i in alvo}
    total_abertas = 0
    for votacao in votacoes:
        if votacao["dataSessao"][:10] < inicio or votacao.get("votacaoSecreta") == "S":
            continue
        votos = votacao.get("votos") or []
        total_abertas += 1
        placar = Counter(v["siglaVotoParlamentar"] for v in votos if v["siglaVotoParlamentar"] in VOTOS_ABERTOS)
        descricao = limpar_texto(votacao.get("descricaoVotacao"))
        classe = classe_da_votacao_senado(descricao)
        for voto in votos:
            id_, sigla = voto["codigoParlamentar"], voto["siglaVotoParlamentar"]
            if id_ not in alvo or sigla not in VOTOS_ABERTOS:
                continue
            if classe == "procedimento":
                procedimento[id_][sigla] += 1
                continue
            demais = placar.copy()
            demais[sigla] -= 1
            sigla_materia = re.sub(r"\s*\(.*\)$", "", votacao.get("identificacao") or "").strip()
            registros[id_].append({
                "id": f"SF-{votacao['codigoSessaoVotacao']}",
                "data": votacao["dataSessao"][:10],
                "voto": sigla,
                "classe": classe,
                "proposicao_id": str(votacao.get("idProcesso") or ""),
                "url": URL_MATERIA.format(codigo=votacao.get("codigoMateria") or ""),
                "sigla": sigla_materia,
                "ementa": limpar_texto(votacao.get("ementa")),
                "descricao": descricao,
                "sim": demais["Sim"],
                "nao": demais["Não"],
                "outros": demais["Abstenção"],
                "partido": voto.get("siglaPartidoParlamentar") or "",
                "orientacao": None,
                "temas": consultar_temas(str(votacao.get("idProcesso") or "")),
            })
    resultado = {}
    for id_ in alvo:
        registros[id_].sort(key=lambda v: (v["data"], v["id"]), reverse=True)
        resultado[id_] = {
            "inicio": inicio,
            "votacoes_nominais": total_abertas,
            "votos_registrados": len(registros[id_]) + sum(procedimento[id_].values()),
            "procedimento": dict(procedimento[id_]),
            "votos": registros[id_],
        }
    return resultado


def ler_norma(texto: Optional[str], situacao: str) -> Optional[dict[str, Any]]:
    """"Lei nº 15.364 de 26/03/2026" vira nome e data. Sem data no texto, quem chama usa a da situação."""
    if not texto:
        return None
    achado = re.search(r"(\d{2})/(\d{2})/(\d{4})", texto)
    nome = re.sub(r"\s+de\s+\d{2}/\d{2}/\d{4}.*$", "", texto).strip()
    return {
        "nome": nome,
        "data": f"{achado[3]}-{achado[2]}-{achado[1]}" if achado else "",
        "veto_parcial": "veto parcial" in situacao.lower(),
    }


def primeira_assinatura(autoria: str, nome: str) -> bool:
    """A autoria vem como "Senador Fulano (PL/SP), Senadora Beltrana (PT/RJ)". Compara com o primeiro nome da lista."""
    primeiro = re.sub(r"\(.*", "", (autoria or "").split(",")[0])
    alvo, lido = tokens(nome), tokens(primeiro)
    return bool(alvo and lido and (alvo <= lido or lido <= alvo))


def grupo_da_situacao_senado(situacao: str, norma: Optional[dict[str, Any]]) -> str:
    texto = situacao.lower()
    if norma or "norma jurídica" in texto:
        return "norma"
    if not texto:
        return "sem_situacao"
    if propostas.SITUACOES_ENCERRADAS.search(texto) or "encerrada" in texto:
        return "encerrada"
    if "câmara dos deputados" in texto:
        return "senado"  # Na Casa revisora. A página do Senado chama de "Aguardando a Câmara".
    return "tramitacao"


def propostas_do_senador(processos: Iterable[dict[str, Any]], nome: str, consultar_temas: Callable[[str], list[str]]) -> list[dict[str, Any]]:
    por_sigla: dict[str, dict[str, Any]] = {}
    for processo in processos:
        tipo = (processo.get("identificacao") or "").split(" ")[0]
        if tipo not in propostas.TIPOS:
            continue
        # A fonte separa fases do mesmo projeto: "PEC 66/2023" e "PEC 66/2023 (fase 2)" geram a mesma emenda.
        sigla = re.sub(r"\s*\(.*\)$", "", processo["identificacao"]).strip()
        situacao = limpar_texto(processo.get("situacaoAtual"))
        data_situacao = (processo.get("dataSituacaoAtual") or "")[:10]
        norma = ler_norma(processo.get("normaGerada"), situacao)
        grupo = grupo_da_situacao_senado(situacao, norma)
        if grupo == "norma" and norma is None:
            norma = {"nome": propostas.NORMA_SEM_NUMERO, "data": data_situacao, "veto_parcial": "veto parcial" in situacao.lower()}
        if norma and not norma["data"]:
            norma["data"] = data_situacao
        proposta = {
            "id": str(processo["id"]),
            "url": URL_MATERIA.format(codigo=processo.get("codigoMateria") or ""),
            "sigla": sigla,
            "tipo": tipo,
            "data": (processo.get("dataApresentacao") or "")[:10],
            "ementa": limpar_texto(processo.get("ementa")),
            "situacao": situacao.capitalize(),
            "data_situacao": data_situacao,
            "participacao": "primeira" if primeira_assinatura(processo.get("autoria") or "", nome) else "coautoria",
            "grupo": grupo,
            "temas": sorted(consultar_temas(str(processo["id"]))),
            "norma": norma,
        }
        anterior = por_sigla.get(sigla)
        if anterior is None or (proposta["norma"] and not anterior["norma"]) or (bool(proposta["norma"]) == bool(anterior["norma"]) and proposta["data_situacao"] > anterior["data_situacao"]):
            por_sigla[sigla] = proposta
    lista = sorted(por_sigla.values(), key=lambda p: (p["data"], p["id"]), reverse=True)
    return lista


def relatorias_no_mandato(relatorias: Iterable[dict[str, Any]], inicio: str) -> dict[str, int]:
    """Projetos relatados. O Senado informa início e fim: em andamento é a designação sem fim, de quando for."""
    processos, em_andamento = set(), set()
    for relatoria in relatorias:
        tipo = (relatoria.get("identificacaoProcesso") or "").split(" ")[0]
        if tipo not in TIPOS_DE_RELATORIA:
            continue
        if (relatoria.get("dataDesignacao") or "")[:10] >= inicio:
            processos.add(relatoria["idProcesso"])
        if not relatoria.get("dataDestituicao"):
            em_andamento.add(relatoria["idProcesso"])
    return {"total": len(processos), "em_andamento": len(em_andamento)}


def cota_de_todos(linhas_por_ano: dict[int, Iterable[dict[str, str]]], nomes: dict[int, str], inicio: str) -> dict[int, dict[str, Any]]:
    """Mesmo formato da cota da Câmara. O Senado não publica total oficial nem endereço do comprovante."""
    linhas_por_ano = {ano: list(linhas) for ano, linhas in linhas_por_ano.items()}
    ligados = ligar_nomes(nomes, (l["SENADOR"] for linhas in linhas_por_ano.values() for l in linhas))
    ano_inicio, mes_inicio = int(inicio[:4]), int(inicio[5:7])
    categorias: dict[int, Counter[str]] = defaultdict(Counter)
    fornecedores: dict[int, Counter[str]] = defaultdict(Counter)
    nomes_fornecedor: dict[int, dict[str, str]] = defaultdict(dict)
    comprovantes: dict[int, list[dict[str, Any]]] = defaultdict(list)
    detalhado: dict[int, Counter[int]] = defaultdict(Counter)
    for ano, linhas in linhas_por_ano.items():
        for linha in linhas:
            id_ = ligados.get(linha["SENADOR"])
            if id_ is None or (ano, int(linha["MES"])) < (ano_inicio, mes_inicio):
                continue
            valor = float((linha["VALOR_REEMBOLSADO"] or "0").replace(".", "").replace(",", "."))
            tipo = linha["TIPO_DESPESA"]
            categoria = next((nome for prefixo, nome in CATEGORIAS_CEAPS if tipo.startswith(prefixo)), tipo.rstrip(".")[:60])
            nome, chave = dinheiro.fornecedor_publico(linha["FORNECEDOR"], linha["CNPJ_CPF"])
            categorias[id_][categoria] += valor
            detalhado[id_][ano] += valor
            if chave:
                fornecedores[id_][chave] += valor
                nomes_fornecedor[id_][chave] = nome
            comprovantes[id_].append({"mes": f"{ano}-{int(linha['MES']):02d}", "categoria": categoria, "fornecedor": nome, "valor": round(valor, 2), "url": None})
    resultado = {}
    for id_ in nomes:
        comprovantes[id_].sort(key=lambda c: (-c["valor"], c["mes"]))
        por_nome: Counter[str] = Counter()
        exibir: dict[str, str] = {}
        for chave, valor in fornecedores[id_].items():
            normalizado = legislatura.normalizar(nomes_fornecedor[id_][chave])
            por_nome[normalizado] += valor
            exibir[normalizado] = nomes_fornecedor[id_][chave]
        resultado[id_] = {
            "por_ano": [
                {"ano": ano, "total": round(detalhado[id_][ano], 2), "percentual": None, "nao_utilizado": None, "detalhado": round(detalhado[id_][ano], 2)}
                for ano in sorted(linhas_por_ano) if detalhado[id_][ano]
            ],
            "categorias": [[nome, round(valor, 2)] for nome, valor in categorias[id_].most_common()],
            "fornecedores": [[exibir[chave], round(valor, 2)] for chave, valor in por_nome.most_common(10)],
            "total_fornecedores": len(por_nome),
            "comprovantes": comprovantes[id_],
        }
    return resultado


def mesma_pessoa(nome: str, outro: str) -> bool:
    """Nomes civis compatíveis: o primeiro nome e mais um em comum, ou três em comum.

    Um nome só não basta: há muitas candidaturas, e dois "Costa" nascidos no mesmo dia são pessoas diferentes.
    """
    a, b = tokens(nome), tokens(outro)
    comuns = a & b
    if not comuns:
        return False
    if a == b or len(comuns) >= 3:
        return True
    primeiro = lambda texto: (legislatura.normalizar(texto).split() or [""])[0]
    return len(comuns) >= 2 and primeiro(nome) == primeiro(outro)


def candidatura_por_nascimento(linhas: Iterable[dict[str, str]], nome: str, nascimento: str) -> Optional[dict[str, str]]:
    """Mesma data de nascimento e nome compatível. Em segundo turno, vale a linha mais recente."""
    achada = None
    for linha in linhas:
        if legislatura.data_iso(linha["DT_NASCIMENTO"]) == nascimento and mesma_pessoa(nome, linha["NM_CANDIDATO"]):
            if achada is None or linha["NR_TURNO"] > achada["NR_TURNO"]:
                achada = linha
    return achada


def nome_parecido_na_uf(linhas: Iterable[dict[str, str]], nome: str, uf: str) -> bool:
    """Segunda busca, sem a data: alguém na mesma UF com ao menos dois nomes iguais, ou o nome inteiro de urna."""
    alvo = tokens(nome)
    for linha in linhas:
        if linha["SG_UF"] != uf:
            continue
        if len(alvo & tokens(linha["NM_CANDIDATO"])) >= 2 or (alvo and alvo == tokens(linha["NM_URNA_CANDIDATO"])):
            return True
    return False


def situacao_do_senador(candidatura: Optional[dict[str, str]], fim_mandato: str, nome_na_uf: bool) -> Optional[dict[str, Any]]:
    """Badge da eleição de 2026. Sem CPF, sem certeza: quem não dá para confirmar fica sem badge."""
    if candidatura is not None:
        cargo, resultado = candidatura["DS_CARGO"].upper(), candidatura["DS_SIT_TOT_TURNO"]
        if cargo == CARGO_SENADOR:
            if resultado in legislatura.ELEITO:
                return {"chave": "reeleicao", "rotulo": "Reeleição"}
            if resultado == "NÃO ELEITO":
                return {"chave": "nao_reeleito", "rotulo": "Não se reelegeu"}
            return {"chave": "sem_resultado", "rotulo": legislatura.ROTULOS["sem_resultado"]}
        cargos = {**legislatura.NOMES_DOS_CARGOS, perfis.CARGO_DEPUTADO: "a Câmara dos Deputados"}
        nome_do_cargo = cargos.get(cargo, cargo.lower())
        if resultado in legislatura.ELEITO:
            return {"chave": "outro_eleito", "rotulo": f"Eleição para {nome_do_cargo}"}
        return {"chave": "outro_disputou", "rotulo": legislatura.ROTULOS["outro_disputou"], "detalhe": f"Disputou {nome_do_cargo} em {legislatura.ANO_DA_ELEICAO}."}
    if fim_mandato[:4] > str(legislatura.ANO_DA_ELEICAO + 1):
        return {"chave": "continua", "rotulo": f"Mandato até {fim_mandato[:4]}"}
    if nome_na_uf:
        return None
    return {"chave": "sem_candidatura", "rotulo": legislatura.ROTULOS["sem_candidatura"]}


def eleitos_que_chegam(
    candidaturas: Iterable[dict[str, str]], atuais: dict[str, int], ex_senadores: Iterable[dict[str, str]], deputados_para_o_senado: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Quem venceu para o Senado em 2026 e não está lá hoje. `atuais` liga SQ_CANDIDATO a quem já tem mandato."""
    antigos = defaultdict(list)
    for pessoa in ex_senadores:
        antigos[pessoa["uf"]].append(pessoa["nome_completo"])
    deputados = defaultdict(list)
    for deputado in deputados_para_o_senado:
        deputados[deputado["uf"]].append(deputado)
    eleitos = []
    for linha in candidaturas:
        if linha["DS_CARGO"].upper() != CARGO_SENADOR or linha["DS_SIT_TOT_TURNO"] not in legislatura.ELEITO or linha["SQ_CANDIDATO"] in atuais:
            continue
        uf = linha["SG_UF"]
        nome_civil = tokens(linha["NM_CANDIDATO"])
        de_camara = next((d for d in deputados[uf] if tokens(d["nome"]) & nome_civil), None)
        if de_camara:
            chave = "camara"
        elif any(mesma_pessoa(antigo, linha["NM_CANDIDATO"]) for antigo in antigos[uf]):
            chave = "retorno"
        else:
            chave = "primeiro"
        eleitos.append({
            "sq": linha["SQ_CANDIDATO"],
            "nome": linha["NM_URNA_CANDIDATO"],
            "partido": linha["SG_PARTIDO"],
            "uf": uf,
            "chave": chave,
            "rotulo": ROTULOS_ELEITOS[chave],
            "id_deputado": de_camara["id"] if de_camara else None,
        })
    eleitos.sort(key=lambda e: legislatura.normalizar(e["nome"]))
    return eleitos


def numeros_da_lista(documentos: dict[int, dict[str, Any]], inicio: str, coletado_em: str) -> dict[str, Any]:
    """Os números da lista de senadores. `presencas` e `dias` guardam a participação e o total de votações."""
    por_deputado = {}
    for id_, doc in documentos.items():
        principal = coautoria = 0
        for proposta in doc["propostas"]["propostas"]:
            norma = proposta.get("norma")
            if norma and norma["data"] >= inicio:
                if proposta["participacao"] == "primeira":
                    principal += 1
                else:
                    coautoria += 1
        anos = doc["plenario"]["participacao"]["por_ano"]
        por_deputado[str(id_)] = {
            "principal": principal,
            "coautoria": coautoria,
            "votos": doc["plenario"]["votos"]["votos_registrados"],
            "presencas": sum(a["votou"] for a in anos),
            "dias": sum(a["votacoes"] for a in anos),
            "relatorias": doc["propostas"]["relatorias_no_mandato"]["em_andamento"],
        }
    return {"coletado_em": coletado_em, "inicio": inicio, "por_deputado": por_deputado}


# --- Acesso às fontes


class ArquivoCeaps:
    def __init__(self, http: Optional[httpx.Client] = None) -> None:
        self.http = http or httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0 (monitor-politico)"})

    def linhas(self, ano: int) -> list[dict[str, str]]:
        texto = self.http.get(URL_CEAPS.format(ano=ano)).raise_for_status().content.decode("latin-1")
        return list(csv.DictReader(io.StringIO(texto.split("\n", 1)[1], newline=""), delimiter=";"))


def _votacoes_do_periodo(senado: ClienteSenado, inicio: str, hoje: date) -> list[dict[str, Any]]:
    votacoes = []
    for ano in range(int(inicio[:4]), hoje.year + 1):
        comeco = inicio if ano == int(inicio[:4]) else f"{ano}-01-01"
        fim = hoje.isoformat() if ano == hoje.year else f"{ano}-12-31"
        votacoes.extend(senado._get("/votacao", {"dataInicio": comeco, "dataFim": fim}))
    return votacoes


def _dados_do_senador(senado: ClienteSenado, id_: int, hoje: date) -> dict[str, Any]:
    detalhe = senado._get(f"/senador/{id_}.json")["DetalheParlamentar"]["Parlamentar"]
    mandatos = como_lista((senado._get(f"/senador/{id_}/mandatos.json")["MandatoParlamentar"]["Parlamentar"].get("Mandatos") or {}).get("Mandato"))
    comissoes = como_lista((senado._get(f"/senador/{id_}/comissoes.json")["MembroComissaoParlamentar"]["Parlamentar"].get("MembroComissoes") or {}).get("Comissao"))
    filiacoes = como_lista((senado._get(f"/senador/{id_}/filiacoes.json")["FiliacaoParlamentar"]["Parlamentar"].get("Filiacoes") or {}).get("Filiacao"))
    return {
        "nascimento": detalhe["DadosBasicosParlamentar"].get("DataNascimento") or "",
        "nome_completo": detalhe["IdentificacaoParlamentar"].get("NomeCompletoParlamentar") or "",
        "uf": detalhe["IdentificacaoParlamentar"].get("UfParlamentar") or "",
        "mandatos": mandatos,
        "comissoes": comissoes,
        "filiacoes": filiacoes,
        "processos": senado._get("/processo", {"codigoParlamentarAutor": id_}),
        "relatorias": senado._get("/processo/relatoria", {"codigoParlamentar": id_}),
    }


def comissoes_atuais(comissoes: Iterable[dict[str, Any]], hoje: date) -> list[dict[str, str]]:
    atuais = []
    for comissao in comissoes:
        fim = comissao.get("DataFim")
        if fim and fim[:10] < hoje.isoformat():
            continue
        identificacao = comissao["IdentificacaoComissao"]
        atuais.append({"sigla": identificacao.get("SiglaComissao") or "", "nome": identificacao.get("NomeComissao") or "", "funcao": comissao.get("DescricaoParticipacao") or ""})
    ordem = {"Titular": 1, "Suplente": 2}
    return sorted(atuais, key=lambda c: (ordem.get(c["funcao"], 0), c["nome"]))


def mandatos_exercidos(mandatos: Iterable[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Início de cada mandato que a pessoa exerceu, do mais antigo para o mais recente.

    Suplente que nunca assumiu não exerceu o mandato, e quem assumiu começa no primeiro exercício. A fonte
    também traz registros sem código, repetindo um período: valem só com exercício registrado.
    """
    exercidos = {}
    for mandato in mandatos:
        inicial = mandato.get("PrimeiraLegislaturaDoMandato") or {}
        exercicios = [e["DataInicio"][:10] for e in como_lista((mandato.get("Exercicios") or {}).get("Exercicio")) if e.get("DataInicio")]
        titular = "Suplente" not in (mandato.get("DescricaoParticipacao") or "") and mandato.get("CodigoMandato")
        if not inicial.get("DataInicio") or not (exercicios or titular):
            continue
        suplente = "Suplente" in (mandato.get("DescricaoParticipacao") or "")
        inicio = min(exercicios) if suplente and exercicios else inicial["DataInicio"][:10]
        exercidos.setdefault(inicio, mandato)
    return sorted(exercidos.items())


def trajetoria_do_senador(mandatos: Iterable[dict[str, Any]], filiacoes: Iterable[dict[str, Any]], uf: str) -> list[dict[str, Any]]:
    """Mandatos que a pessoa exerceu, e trocas de partido durante eles."""
    eventos = []
    inicios = []
    for inicio, mandato in mandatos_exercidos(mandatos):
        inicios.append(inicio)
        eventos.append({"data": inicio, "legislatura": int(mandato["PrimeiraLegislaturaDoMandato"]["NumeroLegislatura"]), "partido": "", "uf": mandato.get("UfParlamentar") or uf, "tipo": "posse"})
    ordenadas = sorted(filiacoes, key=lambda f: f.get("DataFiliacao") or "")
    primeira_posse = min(inicios) if inicios else ""
    for anterior, atual in zip(ordenadas, ordenadas[1:]):
        data = (atual.get("DataFiliacao") or "")[:10]
        if data and data > primeira_posse:
            eventos.append({"data": data, "legislatura": 0, "partido": atual["Partido"]["SiglaPartido"], "uf": uf, "tipo": "partido", "partido_anterior": anterior["Partido"]["SiglaPartido"]})
    for evento in eventos:
        if evento["tipo"] == "posse":
            vigente = [f for f in ordenadas if (f.get("DataFiliacao") or "")[:10] <= evento["data"]]
            evento["partido"] = (vigente[-1] if vigente else ordenadas[0])["Partido"]["SiglaPartido"] if ordenadas else ""
    return sorted(eventos, key=lambda e: e["data"])


def mandatos_do_senador(mandatos: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    """Do mais antigo para o mais recente. O mandato no Senado dura oito anos, duas legislaturas."""
    resultado = []
    for inicio, mandato in mandatos_exercidos(mandatos):
        inicial = mandato["PrimeiraLegislaturaDoMandato"]
        final = mandato.get("SegundaLegislaturaDoMandato") or inicial
        if final.get("DataFim"):
            resultado.append({"inicio": inicio, "rotulo": f"{inicial['DataInicio'][:4]}–{final['DataFim'][:4]}"})
    return resultado


def suplentes_do_mandato(mandatos: Iterable[dict[str, Any]]) -> list[str]:
    exercidos = mandatos_exercidos(mandatos)
    if not exercidos:
        return []
    lista = como_lista((exercidos[-1][1].get("Suplentes") or {}).get("Suplente"))
    return [f"{s.get('DescricaoParticipacao')}: {s.get('NomeParlamentar')}" for s in lista]


def eleicoes_dos_senadores(tse: Any, pessoas: dict[int, dict[str, Any]], cache: dict[str, Any]) -> dict[int, dict[str, Optional[dict[str, str]]]]:
    """Histórico de candidaturas, por nascimento e nome. Devolve também a candidatura de 2026 de cada um, para o badge."""
    candidaturas_2026: dict[int, Optional[dict[str, str]]] = {}
    for ano in ANOS_ELEICOES:
        linhas = list(tse.candidatos(ano))
        por_nascimento: dict[str, list[dict[str, str]]] = defaultdict(list)
        for linha in linhas:
            por_nascimento[legislatura.data_iso(linha["DT_NASCIMENTO"])].append(linha)
        achadas: dict[str, tuple[int, dict[str, str]]] = {}
        for id_, pessoa in pessoas.items():
            candidatura = candidatura_por_nascimento(por_nascimento.get(pessoa["nascimento"], []), pessoa["nome_completo"], pessoa["nascimento"])
            if ano == legislatura.ANO_DA_ELEICAO:
                candidaturas_2026[id_] = candidatura
            if candidatura is not None and candidatura["DS_CARGO"].upper() in CARGOS_DO_HISTORICO:
                achadas[candidatura["SQ_CANDIDATO"]] = (id_, candidatura)
        pendentes = [id_ for id_ in pessoas if str(id_) not in cache["eleicoes"] or not cache.get("eleicoes_anos", {}).get(f"{id_}-{ano}")]
        if not pendentes:
            continue
        votos = legislatura.votos_por_candidatura(tse.votacao(ano, "BRASIL"), set(achadas))
        bens: dict[str, list[dict[str, str]]] = defaultdict(list)
        for linha in tse.bens(ano):
            if linha["SQ_CANDIDATO"] in achadas:
                bens[linha["SQ_CANDIDATO"]].append(linha)
        for id_ in pendentes:
            cache["eleicoes"].setdefault(str(id_), [])
            cache.setdefault("eleicoes_anos", {})[f"{id_}-{ano}"] = True
        for sq, (id_, linha) in achadas.items():
            if id_ not in pendentes:
                continue
            registro = votos.get(sq, {"votos": 0, "total_municipios": 0, "municipios": []})
            cache["eleicoes"][str(id_)].append({
                "ano": ano,
                "cargo": linha["DS_CARGO"].capitalize(),
                "partido": linha["SG_PARTIDO"],
                "uf": linha["SG_UF"],
                "situacao": linha["DS_SIT_TOT_TURNO"],
                "votos": registro["votos"],
                "total_municipios": registro.get("total_municipios", 0),
                "municipios": registro.get("municipios", []),
                "bens": perfis.bens_declarados(bens[sq], sq),
            })
    return candidaturas_2026


def ler_cache(pasta: Path) -> dict[str, Any]:
    caminho = pasta / ARQUIVO_CACHE
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else {"temas": {}, "eleicoes": {}}


def salvar_cache(pasta: Path, cache: dict[str, Any]) -> None:
    caminho = pasta / ARQUIVO_CACHE
    caminho.parent.mkdir(parents=True, exist_ok=True)
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(cache, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    temporario.replace(caminho)


def coletar(senadores: list[dict[str, Any]], senado: ClienteSenado, ceaps: Any, financas: Any, tse: Any, pasta: Path, hoje: Optional[date] = None) -> dict[int, dict[str, Any]]:
    hoje = hoje or date.today()
    avisar = lambda mensagem: print(mensagem, file=sys.stderr, flush=True)
    pasta.mkdir(parents=True, exist_ok=True)
    cache = ler_cache(pasta)
    coletado_em = datetime.now(timezone.utc).isoformat(timespec="seconds")
    inicio_legislatura, fim_legislatura = "2023-02-01", "2027-01-31"
    ids = [s["id"] for s in senadores]
    nomes = {s["id"]: s["nome"] for s in senadores}

    avisar(f"Dados de cada senador: {len(ids)}")
    def tentar(id_: int) -> tuple[int, Any, Optional[Exception]]:
        try:
            return id_, _dados_do_senador(senado, id_, hoje), None
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as erro:
            return id_, None, erro
    pessoas, falhas = {}, []
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
        for id_, dados, erro in executor.map(tentar, ids):
            if erro is None:
                pessoas[id_] = dados
            else:
                falhas.append(id_)
                avisar(f"aviso: senador {id_} falhou ({erro})")
    if len(falhas) > LIMITE_DE_FALHAS * len(ids):
        raise ColetaInterrompida(f"{len(falhas)} de {len(ids)} senadores falharam")
    ids = [i for i in ids if i in pessoas]

    avisar("Temas das proposições")
    votacoes = _votacoes_do_periodo(senado, inicio_legislatura, hoje)
    necessarios = {str(v["idProcesso"]) for v in votacoes if v.get("idProcesso") and v.get("votacaoSecreta") != "S"}
    for id_ in ids:
        necessarios |= {str(p["id"]) for p in pessoas[id_]["processos"] if (p.get("identificacao") or "").split(" ")[0] in propostas.TIPOS}
    faltam = sorted(n for n in necessarios if n not in cache["temas"])
    def consultar(id_processo: str) -> tuple[str, Optional[list[str]]]:
        try:
            return id_processo, _temas_senado(senado._get(f"/processo/{id_processo}"))
        except (httpx.HTTPError, KeyError, ValueError):
            return id_processo, None
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
        for posicao, (id_processo, temas) in enumerate(executor.map(consultar, faltam), 1):
            if temas is not None:
                cache["temas"][id_processo] = temas
            if posicao % 500 == 0:
                salvar_cache(pasta, cache)
                avisar(f"temas: {posicao} de {len(faltam)}")
    salvar_cache(pasta, cache)
    consultar_temas = lambda id_processo: cache["temas"].get(id_processo, [])

    avisar("Votos e participação")
    votos = votos_em_aberto(votacoes, ids, inicio_legislatura, consultar_temas)
    participacao = participacao_nas_votacoes(votacoes, ids, inicio_legislatura)
    secretas = sum(1 for v in votacoes if v.get("votacaoSecreta") == "S" and v["dataSessao"][:10] >= inicio_legislatura)

    avisar("Cota parlamentar e emendas")
    anos_mandato = list(range(int(inicio_legislatura[:4]), hoje.year + 1))
    cotas = cota_de_todos({ano: ceaps.linhas(ano) for ano in anos_mandato}, {i: nomes[i] for i in ids}, inicio_legislatura)
    linhas_emendas = list(financas.emendas())
    linhas_favorecidos = list(financas.favorecidos())
    autores_ligados = ligar_nomes({i: nomes[i] for i in ids}, (l["Nome do Autor da Emenda"] for l in linhas_emendas if "Individual" in l["Tipo de Emenda"]))
    autores = {dinheiro.nome_de_autor(autor): id_ for autor, id_ in autores_ligados.items()}
    emendas = dinheiro.emendas_de_todos(linhas_emendas, linhas_favorecidos, autores, anos_mandato[0])
    sem_emenda = [nomes[i] for i in ids if i not in emendas or not emendas[i]["por_ano"]]
    sem_cota = [nomes[i] for i in ids if not cotas[i]["por_ano"]]
    avisar(f"Sem emendas pelo nome: {sem_emenda}; sem cota: {sem_cota}")

    avisar("Eleições no TSE")
    candidaturas_2026 = eleicoes_dos_senadores(tse, pessoas, cache)
    salvar_cache(pasta, cache)
    linhas_2026 = list(tse.candidatos(legislatura.ANO_DA_ELEICAO))
    fim_por_id = {s["id"]: s.get("fim_mandato") or "" for s in senadores}
    situacoes, sem_confirmacao = {}, []
    sq_atuais: dict[str, int] = {}
    for id_ in ids:
        candidatura = candidaturas_2026.get(id_)
        if candidatura:
            sq_atuais[candidatura["SQ_CANDIDATO"]] = id_
        nome_na_uf = candidatura is None and nome_parecido_na_uf(linhas_2026, pessoas[id_]["nome_completo"], pessoas[id_]["uf"] or next(s["uf"] for s in senadores if s["id"] == id_))
        situacao = situacao_do_senador(candidatura, fim_por_id[id_], nome_na_uf)
        if situacao is None:
            sem_confirmacao.append(nomes[id_])
        else:
            situacoes[str(id_)] = situacao
    avisar(f"Sem badge por falta de confirmação: {sem_confirmacao}")

    documentos = {}
    for id_ in ids:
        pessoa = pessoas[id_]
        lista = propostas_do_senador(pessoa["processos"], nomes[id_], consultar_temas)
        mandatos = mandatos_do_senador(pessoa["mandatos"])
        fim_mandato = fim_por_id[id_]
        inicio_mandato = mandatos[-1]["inicio"] if mandatos else inicio_legislatura
        cota = cotas[id_]
        emenda = emendas.get(id_) or dinheiro.emendas_de_todos([], [], {"": 0}, 0)[0]
        documentos[id_] = {
            "id": id_,
            "casa": "senado",
            "coletado_em": coletado_em,
            "legislatura_atual": {"id": legislatura.LEGISLATURA_ATUAL, "inicio": inicio_mandato, "fim": fim_mandato or fim_legislatura},
            "eleicoes": cache["eleicoes"].get(str(id_), []),
            "trajetoria": trajetoria_do_senador(pessoa["mandatos"], pessoa["filiacoes"], pessoa["uf"]),
            "mandatos": mandatos,
            "suplentes": suplentes_do_mandato(pessoa["mandatos"]),
            "comissoes": comissoes_atuais(pessoa["comissoes"], hoje),
            "plenario": {"votos": votos[id_], "presenca": {"por_ano": []}, "participacao": {**participacao[id_], "secretas": secretas}},
            "propostas": {
                "inicio": mandatos[0]["inicio"] if mandatos else inicio_legislatura,
                "inicio_comparacao": inicio_legislatura,
                "por_ano": [],
                "propostas": lista,
                "relatorias_no_mandato": relatorias_no_mandato(pessoa["relatorias"], inicio_legislatura),
            },
            "dinheiro": {"cota": cota, "emendas": {**emenda, "arquivo_em": financas.data_das_emendas()}},
        }
        (pasta / f"{id_}.json").write_text(json.dumps(documentos[id_], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    avisar("Quem chega e quem saiu")
    historico = senado._get(f"/senador/lista/legislatura/{PRIMEIRA_LEGISLATURA_CONSULTADA}/{legislatura.LEGISLATURA_ATUAL}")
    ex_senadores = []
    for parlamentar in como_lista(next(iter(historico.values()))["Parlamentares"]["Parlamentar"]):
        identificacao = parlamentar["IdentificacaoParlamentar"]
        if int(identificacao["CodigoParlamentar"]) in pessoas:
            continue
        for mandato in como_lista((parlamentar.get("Mandatos") or {}).get("Mandato")):
            if "Suplente" not in (mandato.get("DescricaoParticipacao") or "") or mandato.get("Exercicios"):
                ex_senadores.append({"nome_completo": identificacao.get("NomeCompletoParlamentar") or "", "uf": mandato.get("UfParlamentar") or ""})
    camara = legislatura.ler(LEGISLATURA_CAMARA_PADRAO) or {"situacoes": {}}
    arquivos_camara = json.loads(Path("data/deputados.json").read_text(encoding="utf-8"))["deputados"]
    arquivo_camara = legislatura.ler(Path("data/arquivo_deputados.json")) or {"deputados": []}
    deputados_nomes = {d["id"]: d for d in arquivos_camara + arquivo_camara["deputados"]}
    para_o_senado = [
        {"id": int(i), "nome": deputados_nomes[int(i)]["nome"], "uf": deputados_nomes[int(i)]["uf"]}
        for i, s in camara["situacoes"].items() if s["rotulo"] == "Eleição para o Senado" and int(i) in deputados_nomes
    ]
    eleitos = eleitos_que_chegam(linhas_2026, sq_atuais, ex_senadores, para_o_senado)
    candidaturas_novas = {e["sq"] for e in eleitos}
    votos_eleitos = legislatura.votos_por_candidatura(tse.votacao(legislatura.ANO_DA_ELEICAO, "BRASIL"), candidaturas_novas)
    bens_eleitos: dict[str, list[dict[str, str]]] = defaultdict(list)
    for linha in tse.bens(legislatura.ANO_DA_ELEICAO):
        if linha["SQ_CANDIDATO"] in candidaturas_novas:
            bens_eleitos[linha["SQ_CANDIDATO"]].append(linha)
    for eleito in eleitos:
        eleito.update(votos_eleitos.get(eleito["sq"], {"votos": 0}))
        eleito["bens"] = perfis.bens_declarados(bens_eleitos[eleito["sq"]], eleito["sq"])
    ELEITOS_PADRAO.write_text(json.dumps({
        "coletado_em": coletado_em, "legislatura_atual": legislatura.LEGISLATURA_ATUAL, "ano_da_eleicao": legislatura.ANO_DA_ELEICAO,
        "posse": legislatura.POSSE, "situacoes": situacoes, "eleitos_novos": eleitos,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    # Primeira carga do arquivo: quem votou nesta legislatura e não está mais em exercício. Depois, a coleta diária cuida disso.
    if not ARQUIVO_PADRAO.exists():
        votaram = {v["codigoParlamentar"] for votacao in votacoes for v in votacao.get("votos") or []} - set(nomes)
        arquivo = []
        for id_ in sorted(votaram):
            try:
                dados = senado._get(f"/senador/{id_}.json")["DetalheParlamentar"]["Parlamentar"]["IdentificacaoParlamentar"]
            except (httpx.HTTPError, KeyError):
                continue
            arquivo.append({
                "id": id_, "nome": dados.get("NomeParlamentar") or "", "partido": dados.get("SiglaPartidoParlamentar") or "", "uf": dados.get("UfParlamentar") or "",
                "url_foto": dados.get("UrlFotoParlamentar"), "condicao": None, "bloco": None, "fim_mandato": None, "email": None, "telefones": [],
                "uri_api": f"https://legis.senado.leg.br/dadosabertos/senador/{id_}", "url_site": f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{id_}", "saiu_em": None,
            })
            time.sleep(0.05)
        ARQUIVO_PADRAO.write_text(json.dumps({"senadores": sorted(arquivo, key=lambda d: legislatura.normalizar(d["nome"]))}, ensure_ascii=False, indent=1), encoding="utf-8")

    numeros = numeros_da_lista(documentos, metricas.INICIO_MANDATO, coletado_em)
    METRICAS_PADRAO.write_text(json.dumps(numeros, ensure_ascii=False, indent=1), encoding="utf-8")
    return documentos


if __name__ == "__main__":
    lista_senadores = json.loads(SENADORES_PADRAO.read_text(encoding="utf-8"))["senadores"]
    resultado = coletar(lista_senadores, ClienteSenado(), ArquivoCeaps(), dinheiro.FonteDinheiro(), perfis.FonteTSE(), PASTA_PADRAO)
    print(f"{len(resultado)} perfis de senadores em {PASTA_PADRAO}")

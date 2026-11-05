"""Atuação em Plenário de um deputado: votos nominais e presença.

Votos e eventos vêm dos arquivos anuais de Dados Abertos da Câmara, porque a API responde devagar e
com erros quando a consulta é grande. A presença vem do relatório oficial de cada ano, o único lugar
que separa as ausências justificadas das não justificadas.
"""

from __future__ import annotations

import csv
import html
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Iterable, Iterator, Optional

import httpx

from monitor_politico.congresso import eh_procedimento

URL_ARQUIVO = "https://dadosabertos.camara.leg.br/arquivos/{tipo}/csv/{tipo}-{ano}.csv"
URL_PRESENCA = "https://www.camara.leg.br/deputados/{id}/presenca-plenario/{ano}"
ORGAO_PLENARIO = "PLEN"
SESSAO_DELIBERATIVA = "Sessão Deliberativa"

TEXTO_PRINCIPAL = re.compile(
    r"emenda (substitutiva|aglutinativa)|subemenda substitutiva|em (primeiro|segundo) turno"
    r"|^(aprovad|rejeitad)\w+ (o|a) (projeto|substitutivo|medida|proposta|parecer)",
    re.IGNORECASE,
)
PREFERENCIA = re.compile(r"prefer[eê]ncia", re.IGNORECASE)
CPF_NO_TEXTO = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-\d{2}\b")
EMENDA_REJEITADA = re.compile(r"^rejeitad\w+ a emenda de plen", re.IGNORECASE)
RELATORIO_PRESENCA = {
    "dias": "Total de dias com sessões deliberativas realizadas no período",
    "presencas": "Total de dias com presença nas sessões deliberativas",
    "justificadas": "Total de dias com ausências justificadas em sessões deliberativas",
    "nao_justificadas": "Total de dias com ausências não justificadas em sessões deliberativas",
}


class RelatorioInvalido(RuntimeError):
    """A página oficial mudou de formato: é melhor falhar do que publicar número errado."""


def classe_da_votacao(descricao: str) -> str:
    """Separa pela descrição oficial: "procedimento", "texto" (principal) ou "ajuste" (emendas, destaques, recursos)."""
    if eh_procedimento(descricao) or PREFERENCIA.search(descricao):
        return "procedimento"
    return "texto" if TEXTO_PRINCIPAL.search(descricao) and not EMENDA_REJEITADA.search(descricao) else "ajuste"


def orientacao_do_partido(bancadas: dict[str, str], partido: str) -> Optional[str]:
    """Orientação do partido ou da federação dele. Os blocos vêm com nome abreviado e não dá para identificá-los."""
    for bancada, orientacao in bancadas.items():
        nome = bancada.casefold()
        if nome == partido.casefold():
            return orientacao
        if nome.startswith("fdr ") and partido.casefold() in re.split(r"[-\s]+", nome):
            return orientacao
    return None


def ler_relatorio_de_presenca(pagina: str) -> dict[str, int]:
    resultado = {}
    for chave, rotulo in RELATORIO_PRESENCA.items():
        achado = re.search(re.escape(rotulo) + r"\s*</b>\s*</td>\s*<td[^>]*>\s*(?:<strong>)?\s*(\d+)", html.unescape(pagina))
        if achado is None:
            raise RelatorioInvalido(f"sem o total: {rotulo}")
        resultado[chave] = int(achado[1])
    if resultado["presencas"] + resultado["justificadas"] + resultado["nao_justificadas"] != resultado["dias"]:
        raise RelatorioInvalido(f"totais não fecham: {resultado}")
    return resultado


def _limpar(texto: Optional[str]) -> str:
    """Normaliza espaços e tira CPF: há ementas oficiais que citam o número de uma pessoa."""
    return CPF_NO_TEXTO.sub("[CPF omitido]", re.sub(r"\s+", " ", texto or "")).strip()


def votos_do_mandato(fonte: Any, id_: int, inicio: str, anos: Iterable[int]) -> dict[str, Any]:
    """Votos do parlamentar nas votações nominais do Plenário desde o início do mandato.

    Só os votos do próprio parlamentar são guardados um a um; o restante vira placar.
    """
    anos = list(anos)
    votacoes = {}
    for ano in anos:
        for v in fonte.linhas("votacoes", ano):
            if v["siglaOrgao"] == ORGAO_PLENARIO and v["data"] >= inicio:
                votacoes[v["id"]] = v

    registrados: dict[str, dict[str, str]] = {}
    placares: dict[str, Counter[str]] = defaultdict(Counter)
    for ano in anos:
        for linha in fonte.linhas("votacoesVotos", ano):
            # Voto em branco no arquivo: a fonte não informa a posição individual nesta votação.
            if linha["idVotacao"] not in votacoes or not linha["voto"]:
                continue
            placares[linha["idVotacao"]][linha["voto"]] += 1
            if linha["deputado_id"] == str(id_):
                registrados[linha["idVotacao"]] = linha

    objetos: dict[str, dict[str, str]] = {}
    orientacoes: dict[str, dict[str, str]] = defaultdict(dict)
    for ano in anos:
        for linha in fonte.linhas("votacoesProposicoes", ano):
            id_votacao = linha["idVotacao"]
            # O id da votação começa com o id da proposição votada; as demais só aparecem como relacionadas.
            if id_votacao in registrados and (id_votacao not in objetos or id_votacao.split("-")[0] == linha["proposicao_id"]):
                objetos[id_votacao] = linha
        for linha in fonte.linhas("votacoesOrientacoes", ano):
            if linha["idVotacao"] in registrados:
                orientacoes[linha["idVotacao"]][linha["siglaBancada"]] = linha["orientacao"]

    temas: dict[str, list[str]] = defaultdict(list)
    for ano in sorted({int(o["proposicao_ano"]) for o in objetos.values() if o["proposicao_ano"].isdigit()}):
        for linha in fonte.linhas("proposicoesTemas", ano):
            id_proposicao = linha["uriProposicao"].rsplit("/", 1)[-1]
            if linha["tema"] not in temas[id_proposicao]:
                temas[id_proposicao].append(linha["tema"])

    votos, procedimento = [], Counter()
    for id_votacao, linha in registrados.items():
        votacao = votacoes[id_votacao]
        descricao = _limpar(votacao["descricao"])
        classe = classe_da_votacao(descricao)
        voto = linha["voto"]
        if classe == "procedimento":
            procedimento[voto] += 1
            continue
        placar = placares[id_votacao].copy()
        placar[linha["voto"]] -= 1  # O placar mostrado é o dos demais votos.
        sim, nao = placar["Sim"], placar["Não"]
        objeto = objetos.get(id_votacao, {})
        id_proposicao = objeto.get("proposicao_id") or id_votacao.split("-")[0]
        votos.append({
            "id": id_votacao,
            "data": votacao["data"],
            "voto": voto,
            "classe": classe,
            "proposicao_id": id_proposicao,
            "sigla": f"{objeto['proposicao_siglaTipo']} {objeto['proposicao_numero']}/{objeto['proposicao_ano']}" if objeto else "",
            "ementa": _limpar(objeto.get("proposicao_ementa")),
            "descricao": descricao,
            "sim": sim,
            "nao": nao,
            "outros": sum(placar.values()) - sim - nao,
            "partido": linha["deputado_siglaPartido"],
            "orientacao": orientacao_do_partido(orientacoes.get(id_votacao, {}), linha["deputado_siglaPartido"]),
            "temas": sorted(temas.get(id_proposicao, [])),
        })
    votos.sort(key=lambda v: (v["data"], v["id"]), reverse=True)
    return {
        "inicio": inicio,
        "votacoes_nominais": len({i for i in votacoes if placares[i]}),
        "votos_registrados": len(registrados),
        "procedimento": dict(procedimento),
        "votos": votos,
    }


def presenca_do_mandato(fonte: Any, id_: int, inicio: str, anos: Iterable[int]) -> dict[str, Any]:
    por_ano = []
    for ano in anos:
        eventos = {e["id"]: e for e in fonte.linhas("eventos", ano)}
        outros = 0
        for linha in fonte.linhas("eventosPresencaDeputados", ano):
            evento = eventos.get(linha["idEvento"])
            if (
                linha["idDeputado"] == str(id_) and evento and evento["situacao"].startswith("Encerrada")
                and evento["descricaoTipo"] != SESSAO_DELIBERATIVA and evento["dataHoraInicio"][:10] >= inicio
            ):
                outros += 1
        por_ano.append({"ano": ano, **fonte.relatorio_de_presenca(id_, ano), "outros_eventos": outros})
    return {"por_ano": por_ano}


class ArquivosCamara:
    def __init__(self, http: Optional[httpx.Client] = None) -> None:
        self.http = http or httpx.Client(timeout=300, follow_redirects=True, headers={"User-Agent": "monitor-politico"})

    def linhas(self, tipo: str, ano: int) -> Iterator[dict[str, str]]:
        """Baixa para um arquivo temporário: há campos com quebra de linha, então o CSV não pode ser lido por linhas da rede."""
        with tempfile.TemporaryFile() as temporario, self.http.stream("GET", URL_ARQUIVO.format(tipo=tipo, ano=ano)) as resposta:
            if resposta.status_code == 404:
                print(f"aviso: sem arquivo {tipo} de {ano}", file=sys.stderr)
                return
            resposta.raise_for_status()
            for trecho in resposta.iter_bytes():
                temporario.write(trecho)
            temporario.seek(0)
            texto = (bruta.decode("utf-8-sig") for bruta in temporario)
            yield from csv.DictReader(texto, delimiter=";")

    def relatorio_de_presenca(self, id_: int, ano: int) -> dict[str, int]:
        resposta = self.http.get(URL_PRESENCA.format(id=id_, ano=ano)).raise_for_status()
        return ler_relatorio_de_presenca(resposta.text)


def coletar(fonte: Any, id_: int, inicio: str, hoje: date) -> dict[str, Any]:
    anos = range(int(inicio[:4]), hoje.year + 1)
    return {"votos": votos_do_mandato(fonte, id_, inicio, anos), "presenca": presenca_do_mandato(fonte, id_, inicio, anos)}


# --- O que a página mostra

ROTULOS_CLASSE = {"texto": "Texto principal", "ajuste": "Emendas, destaques e recursos"}


def contar(votos: Iterable[dict[str, Any]]) -> dict[str, int]:
    contagem = Counter(v["voto"] for v in votos)
    sim, nao = contagem["Sim"], contagem["Não"]
    return {"sim": sim, "nao": nao, "outros": sum(contagem.values()) - sim - nao}


def lado_menos_votado(voto: dict[str, Any]) -> bool:
    """O voto ficou com menos apoio entre os demais votos Sim e Não? Empate e outros registros ficam de fora."""
    if voto["voto"] not in ("Sim", "Não") or voto["sim"] == voto["nao"]:
        return False
    return (voto["voto"] == "Sim") != (voto["sim"] > voto["nao"])


def difere_da_orientacao(voto: dict[str, Any]) -> bool:
    """Só conta orientação de Sim ou Não: "Liberado" ou "Obstrução" não têm com o que comparar."""
    return voto["voto"] in ("Sim", "Não") and voto["orientacao"] in ("Sim", "Não") and voto["voto"] != voto["orientacao"]


def _largura(partes: dict[str, int]) -> dict[str, float]:
    total = sum(partes.values()) or 1
    return {chave: round(valor / total * 100, 2) for chave, valor in partes.items()}


def visao(doc: dict[str, Any], slugs: Optional[dict[str, str]] = None) -> dict[str, Any]:
    slugs = slugs or {}
    dados, presenca = doc["votos"], doc["presenca"]
    votos = []
    for voto in dados["votos"]:
        votos.append({
            **voto,
            "contra": lado_menos_votado(voto),
            "difere": difere_da_orientacao(voto),
            "slug": slugs.get(voto["sigla"]),
            "barra": _largura({"sim": voto["sim"], "nao": voto["nao"], "outros": voto["outros"]}),
        })
    texto = [v for v in votos if v["classe"] == "texto"]
    ajuste = [v for v in votos if v["classe"] == "ajuste"]
    procedimento = sum(dados["procedimento"].values())
    todos = contar(votos)
    for voto_procedimento, quantos in dados["procedimento"].items():
        chave = {"Sim": "sim", "Não": "nao"}.get(voto_procedimento, "outros")
        todos[chave] += quantos
    assuntos = Counter(t for v in texto for t in v["temas"])
    temas = []
    for tema, _ in assuntos.most_common(6):
        contagem = contar(v for v in texto if tema in v["temas"])
        temas.append({"tema": tema, **contagem, "barra": _largura(contagem)})
    com_orientacao = [v for v in texto if v["orientacao"] in ("Sim", "Não") and v["voto"] in ("Sim", "Não")]
    totais_presenca = {
        chave: sum(a[chave] for a in presenca["por_ano"])
        for chave in ("dias", "presencas", "justificadas", "nao_justificadas", "outros_eventos")
    }
    return {
        "votacoes_nominais": dados["votacoes_nominais"],
        "votos_registrados": dados["votos_registrados"],
        "sem_registro": dados["votacoes_nominais"] - dados["votos_registrados"],
        "inicio": dados["inicio"],
        "votos": votos,
        "todos": {**todos, "barra": _largura(todos)},
        "texto": {**contar(texto), "barra": _largura(contar(texto))},
        "total_texto": len(texto),
        "total_ajuste": len(ajuste),
        "total_procedimento": procedimento,
        "contra_texto": sum(v["contra"] for v in texto),
        "difere_texto": sum(v["difere"] for v in texto),
        "com_orientacao": len(com_orientacao),
        "temas": temas,
        "opcoes_temas": sorted({t for v in votos for t in v["temas"]}),
        "rotulos_classe": ROTULOS_CLASSE,
        "presenca": {"por_ano": presenca["por_ano"], "total": totais_presenca},
    }

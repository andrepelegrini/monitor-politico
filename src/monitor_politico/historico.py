"""Projetos votados no Plenário desde o início da legislatura, para além da janela de 30 dias.

Entra a proposição que teve o texto principal votado no Plenário da Câmara ou do Senado desde
01/02/2023 (projetos de lei, de lei complementar, PECs, medidas provisórias, decretos legislativos e
resoluções). A página de cada uma usa o mesmo formato das proposições recentes, montado pelas mesmas
funções de `congresso.py`, só que sem a lista de quem votou como: esse voto já está no perfil de cada
parlamentar, e guardar as listas de todas as votações pesaria demais.

As votações da Câmara vêm dos arquivos abertos anuais (que trazem também as votações simbólicas e o
total de votos das nominais). As do Senado vêm da API, que só publica as nominais.

Uso: python -m monitor_politico.historico [saida.json]   (roda na coleta semanal)
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import httpx

from monitor_politico import congresso
from monitor_politico.camara import ClienteCamara
from monitor_politico.lote_senado import classe_da_votacao_senado
from monitor_politico.plenario import ArquivosCamara, classe_da_votacao
from monitor_politico.senado import ClienteSenado

SAIDA_PADRAO = Path("data/historico.json")
INICIO = "2023-02-01"
TIPOS = ("PL", "PLP", "PEC", "MPV", "PDL", "PRC", "PRS")
TRABALHADORES = 4
LIMITE_FALHAS = 0.1


def _numero(texto: Optional[str]) -> int:
    try:
        return int(texto or 0)
    except ValueError:
        return 0


def votacao_dos_arquivos(linha: dict[str, str]) -> dict[str, Any]:
    """Uma votação do arquivo aberto da Câmara no formato de `congresso.votacao_camara`, sem os votos de cada um."""
    sim, nao, outros = _numero(linha.get("votosSim")), _numero(linha.get("votosNao")), _numero(linha.get("votosOutros"))
    nominal = sim + nao + outros > 0
    aprovacao = (linha.get("aprovacao") or "").strip()
    return {
        "id": linha["id"],
        "casa": "Câmara",
        "data_hora": linha.get("dataHoraRegistro") or linha["data"],
        "descricao": linha["descricao"],
        "resultado": {"1": "aprovada", "0": "rejeitada"}.get(aprovacao),
        "procedimento": congresso.eh_procedimento(linha["descricao"]),
        "nominal": nominal,
        "placar": {"sim": sim, "nao": nao, "abstencao": 0, "outros": [["Outros registros", outros]] if outros else []} if nominal else None,
        "orientacoes": None,
        "votos": [],
    }


def votacoes_da_camara(arquivos: Any, anos: Iterable[int], inicio: str = INICIO) -> dict[str, dict[str, Any]]:
    """Por proposição: o id na Câmara e as votações de Plenário em que ela foi o objeto."""
    por_chave: dict[str, dict[str, Any]] = defaultdict(lambda: {"id_camara": None, "votacoes": {}, "texto": False})
    for ano in anos:
        plenario = {
            linha["id"]: linha for linha in arquivos.linhas("votacoes", ano)
            if linha.get("siglaOrgao") == "PLEN" and (linha.get("data") or "")[:10] >= inicio
        }
        for ligacao in arquivos.linhas("votacoesProposicoes", ano):
            linha = plenario.get(ligacao["idVotacao"])
            if linha is None or ligacao["proposicao_siglaTipo"] not in TIPOS:
                continue
            k = congresso.chave(ligacao["proposicao_siglaTipo"], ligacao["proposicao_numero"], ligacao["proposicao_ano"])
            registro = por_chave[k]
            registro["id_camara"] = int(ligacao["proposicao_id"])
            registro["votacoes"][linha["id"]] = votacao_dos_arquivos(linha)
            registro["texto"] = registro["texto"] or classe_da_votacao(linha["descricao"]) == "texto"
    return {k: {**r, "votacoes": list(r["votacoes"].values())} for k, r in por_chave.items()}


def votacoes_do_senado(brutas: Iterable[dict[str, Any]], inicio: str = INICIO) -> dict[str, dict[str, Any]]:
    """Por proposição, as votações nominais do Senado, só com o placar."""
    por_chave: dict[str, dict[str, Any]] = defaultdict(lambda: {"votacoes": [], "texto": False})
    for bruta in brutas:
        if bruta["dataSessao"][:10] < inicio:
            continue
        partes = congresso.separar_chave(re.sub(r"\s*\(.*\)$", "", bruta.get("identificacao") or ""))
        if not partes or partes[0] not in TIPOS:
            continue
        votacao = {**congresso.votacao_senado(bruta), "votos": []}
        registro = por_chave[congresso.chave(*partes)]
        registro["votacoes"].append(votacao)
        registro["texto"] = registro["texto"] or classe_da_votacao_senado(bruta.get("descricaoVotacao") or "") == "texto"
    return dict(por_chave)


def coletar(
    camara: ClienteCamara,
    senado: ClienteSenado,
    arquivos: Any,
    saida: Path = SAIDA_PADRAO,
    hoje: Optional[date] = None,
    avisar: Callable[[str], None] = lambda msg: print(f"aviso: {msg}", file=sys.stderr),
) -> dict[str, Any]:
    hoje = hoje or date.today()
    anteriores = json.loads(saida.read_text(encoding="utf-8"))["proposicoes"] if saida.exists() else {}
    anos = range(int(INICIO[:4]), hoje.year + 1)

    da_camara = votacoes_da_camara(arquivos, anos)
    brutas_senado = []
    for ano in anos:
        comeco = INICIO if ano == int(INICIO[:4]) else f"{ano}-01-01"
        fim = hoje.isoformat() if ano == hoje.year else f"{ano}-12-31"
        brutas_senado += senado._get("/votacao", {"dataInicio": comeco, "dataFim": fim})
    do_senado = votacoes_do_senado(brutas_senado)

    # Só entra quem teve o texto principal votado em alguma das duas Casas.
    chaves = sorted(k for k in set(da_camara) | set(do_senado) if (da_camara.get(k) or {}).get("texto") or (do_senado.get(k) or {}).get("texto"))
    avisar(f"{len(chaves)} proposições com o texto votado no Plenário desde {INICIO}")

    def montar(k: str) -> tuple[str, Optional[dict[str, Any]], Optional[Exception]]:
        votacoes = (da_camara.get(k) or {}).get("votacoes", []) + (do_senado.get(k) or {}).get("votacoes", [])
        try:
            return k, congresso.montar_proposicao(k, camara, senado, (da_camara.get(k) or {}).get("id_camara"), votacoes), None
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as erro:
            return k, None, erro

    proposicoes, falhas = {}, []
    with ThreadPoolExecutor(max_workers=TRABALHADORES) as executor:
        for k, proposicao, erro in executor.map(montar, chaves):
            if proposicao is not None:
                proposicoes[k] = proposicao
                continue
            falhas.append(k)
            avisar(f"{k} falhou ({erro})")
            if k in anteriores:
                proposicoes[k] = anteriores[k]
    if len(falhas) > LIMITE_FALHAS * max(len(chaves), 1):
        raise congresso.ColetaIncompleta(f"{len(falhas)} de {len(chaves)} proposições falharam")

    doc = {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "desde": INICIO,
        "proposicoes": dict(sorted(proposicoes.items())),
    }
    saida.parent.mkdir(parents=True, exist_ok=True)
    # Uma linha por campo: muda pouco de uma semana para outra, e o Git guarda só a diferença.
    saida.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    return doc


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    resultado = coletar(ClienteCamara(), ClienteSenado(), ArquivosCamara(), destino)
    print(f"{len(resultado['proposicoes'])} proposições em {destino}")

"""Métrica comparável de todos os deputados: leis sancionadas no mandato atual, por tipo de autoria.

O critério é o mesmo para todos: conta a data em que a norma saiu, e não a data do projeto, para não
favorecer quem está há mais tempo na Câmara nem esquecer projetos apresentados em mandatos anteriores.

A coleta é manual: baixa muitos arquivos anuais da Câmara e consulta a tramitação de cada candidato.
Uso: python -m monitor_politico.metricas [saida.json]
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from monitor_politico import plenario
from monitor_politico.camara import ClienteCamara
from monitor_politico.propostas import TIPOS, grupo_da_situacao, norma_da_tramitacao, participacao

SAIDA_PADRAO = Path("data/metricas_deputados.json")
DEPUTADOS_PADRAO = Path("data/deputados.json")
INICIO_MANDATO = "2023-02-01"  # Trocar na posse da nova legislatura, em 01/02/2027.
ANO_MAIS_ANTIGO = 1995  # Primeiro ano conferido nos arquivos. Lei recente de projeto mais antigo é improvável.


def leis_por_deputado(fonte: Any, camara: Any, ids: Iterable[int], inicio: str, anos: Iterable[int]) -> dict[str, Any]:
    alvo = {str(i) for i in ids}
    anos = list(anos)
    assinaturas: dict[str, dict[str, str]] = defaultdict(dict)
    for ano in anos:
        for linha in fonte.linhas("proposicoesAutores", ano):
            if linha["idDeputadoAutor"] in alvo:
                assinaturas[linha["idProposicao"]][linha["idDeputadoAutor"]] = participacao(linha)

    candidatas = []
    for ano in anos:
        for proposta in fonte.linhas("proposicoes", ano):
            if (
                proposta["id"] in assinaturas and proposta["siglaTipo"] in TIPOS
                and grupo_da_situacao(proposta["ultimoStatus_descricaoSituacao"]) == "norma"
            ):
                candidatas.append(proposta)

    por_deputado: dict[str, dict[str, Any]] = {i: {"principal": 0, "coautoria": 0} for i in sorted(alvo, key=int)}
    normas = []
    sem_norma = []
    for proposta in candidatas:
        # Uma falha aqui interrompe a coleta de propósito: uma lei a menos seria um número errado sem aviso.
        norma = norma_da_tramitacao(camara._get(f"/proposicoes/{proposta['id']}/tramitacoes")["dados"])
        sigla = f"{proposta['siglaTipo']} {proposta['numero']}/{proposta['ano']}"
        if norma is None:
            sem_norma.append(sigla)
            continue
        if norma["data"] < inicio:
            continue
        autores: dict[str, list[str]] = {"principal": [], "coautoria": []}
        for id_deputado, tipo in assinaturas[proposta["id"]].items():
            if tipo == "primeira":
                autores["principal"].append(id_deputado)
                por_deputado[id_deputado]["principal"] += 1
            elif tipo == "coautoria":
                autores["coautoria"].append(id_deputado)
                por_deputado[id_deputado]["coautoria"] += 1
        if autores["principal"] or autores["coautoria"]:
            normas.append({"id": proposta["id"], "sigla": sigla, "norma": norma["nome"], "data": norma["data"], **autores})
    normas.sort(key=lambda n: (n["data"], n["id"]), reverse=True)
    return {
        "inicio": inicio,
        "ano_mais_antigo": anos[0] if anos else None,
        "candidatas": len(candidatas),
        "sem_norma_identificada": sem_norma,
        "normas": normas,
        "por_deputado": por_deputado,
    }


def coletar(fonte: Any, camara: Any, ids: Iterable[int], hoje: Optional[date] = None, inicio: str = INICIO_MANDATO) -> dict[str, Any]:
    hoje = hoje or date.today()
    return {
        "coletado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **leis_por_deputado(fonte, camara, ids, inicio, range(ANO_MAIS_ANTIGO, hoje.year + 1)),
    }


def ler(caminho: Path) -> Optional[dict[str, Any]]:
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None


def do_deputado(metricas: Optional[dict[str, Any]], id_: int) -> dict[str, int]:
    return (metricas or {}).get("por_deputado", {}).get(str(id_), {"principal": 0, "coautoria": 0})


if __name__ == "__main__":
    destino = Path(sys.argv[1]) if len(sys.argv) > 1 else SAIDA_PADRAO
    deputados = json.loads(DEPUTADOS_PADRAO.read_text(encoding="utf-8"))["deputados"]
    resultado = coletar(plenario.ArquivosCamara(), ClienteCamara(), [d["id"] for d in deputados])
    destino.write_text(json.dumps(resultado, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(resultado['normas'])} leis desde {resultado['inicio']}; {resultado['candidatas']} candidatas; sem norma: {resultado['sem_norma_identificada']}")

"""Pacote com os perfis completos, guardado como anexo de uma release do GitHub.

São centenas de MB que mudam toda semana, o que incharia o histórico do Git. O repositório guarda só
data/perfis_versao.json, com o nome e o checksum do pacote. O build baixa exatamente essa versão: se o
download falhar ou o checksum não bater, o build falha e o site publicado continua como está.

Uso:
  python -m monitor_politico.pacote empacotar   gera o pacote e atualiza data/perfis_versao.json
  python -m monitor_politico.pacote baixar      baixa e extrai a versão indicada (usado no build)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import httpx

PASTA_PERFIS = Path("data/perfis")
VERSAO = Path("data/perfis_versao.json")
RELEASE = "dados-perfis"
URL_DOWNLOAD = "https://github.com/andrepelegrini/monitor-politico/releases/download/" + RELEASE + "/{nome}"


class PacoteInvalido(RuntimeError):
    pass


CPF_FORMATADO = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
CPF_EM_NOME = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
CHAVES_PROIBIDAS = {"cpf", "datanascimento", "nomecivil", "txtpassageiro", "txttrecho", "ds_bem_candidato", "ds_email", "nr_cpf_candidato"}


def dados_pessoais_no_documento(documento: Any) -> list[str]:
    """Última barreira antes de publicar: CPF em qualquer texto, em nome de fornecedor ou campo que nunca deveria estar aqui."""
    achados: list[str] = []

    def percorrer(valor: Any, chave: str = "") -> None:
        if isinstance(valor, dict):
            for nome, item in valor.items():
                if nome.lower() in CHAVES_PROIBIDAS:
                    achados.append(f"campo {nome}")
                percorrer(item, nome)
        elif isinstance(valor, list):
            for item in valor:
                percorrer(item, chave)
        elif isinstance(valor, str):
            if CPF_FORMATADO.search(valor) or (chave in ("fornecedor", "fornecedores", "nome") and CPF_EM_NOME.search(valor)):
                achados.append(f"CPF em {chave or 'texto'}")

    percorrer(documento)
    return achados


def verificar_privacidade(pasta: Path) -> None:
    for caminho in sorted(pasta.glob("*.json")):
        achados = dados_pessoais_no_documento(json.loads(caminho.read_text(encoding="utf-8")))
        if achados:
            raise PacoteInvalido(f"dados pessoais em {caminho.name}: {sorted(set(achados))[:5]}")


def checksum(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for trecho in iter(lambda: arquivo.read(1 << 20), b""):
            resumo.update(trecho)
    return resumo.hexdigest()


def empacotar(pasta: Path = PASTA_PERFIS, versao: Path = VERSAO, destino: Optional[Path] = None, agora: Optional[datetime] = None) -> Path:
    verificar_privacidade(pasta)
    agora = agora or datetime.now(timezone.utc)
    nome = f"perfis-{agora:%Y%m%d-%H%M}.tar.gz"
    arquivo = (destino or Path(tempfile.gettempdir())) / nome
    arquivos = sorted(c for c in pasta.rglob("*") if c.is_file())
    if not arquivos:
        raise PacoteInvalido(f"nada para empacotar em {pasta}")
    with tarfile.open(arquivo, "w:gz", compresslevel=6) as tar:
        for caminho in arquivos:
            tar.add(caminho, arcname=str(caminho.relative_to(pasta)))
    versao.write_text(json.dumps({"nome": nome, "sha256": checksum(arquivo), "perfis": sum(c.suffix == ".json" and c.parent == pasta for c in arquivos)}, indent=1) + "\n", encoding="utf-8")
    return arquivo


def extrair(arquivo: Path, pasta: Path) -> None:
    pasta.mkdir(parents=True, exist_ok=True)
    with tarfile.open(arquivo, "r:gz") as tar:
        for membro in tar.getmembers():
            if not (membro.isfile() or membro.isdir()) or membro.name.startswith("/") or ".." in Path(membro.name).parts:
                raise PacoteInvalido(f"item inesperado no pacote: {membro.name}")
        tar.extractall(pasta)


def baixar(pasta: Path = PASTA_PERFIS, versao: Path = VERSAO, http: Optional[httpx.Client] = None) -> dict[str, Any]:
    info = json.loads(versao.read_text(encoding="utf-8"))
    cliente = http or httpx.Client(timeout=300, follow_redirects=True)
    with tempfile.TemporaryDirectory() as temporaria:
        arquivo = Path(temporaria) / info["nome"]
        with cliente.stream("GET", URL_DOWNLOAD.format(nome=info["nome"])) as resposta:
            resposta.raise_for_status()
            with arquivo.open("wb") as saida:
                for trecho in resposta.iter_bytes():
                    saida.write(trecho)
        if checksum(arquivo) != info["sha256"]:
            raise PacoteInvalido(f"checksum diferente em {info['nome']}")
        extrair(arquivo, pasta)
    return info


if __name__ == "__main__":
    comando = sys.argv[1] if len(sys.argv) > 1 else ""
    if comando == "empacotar":
        print(empacotar())
    elif comando == "baixar":
        dados = baixar()
        print(f"Pacote {dados['nome']}: {dados['perfis']} perfis")
    else:
        sys.exit("use: empacotar | baixar")

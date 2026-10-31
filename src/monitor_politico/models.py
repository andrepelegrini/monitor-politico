"""Modelo de dados persistido.

Whitelist explícita: só os campos declarados aqui saem da API e chegam ao
JSON/site. Campos como CPF, data de nascimento e redes sociais, presentes na
resposta da Câmara, são descartados por construção.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional

URL_SITE_CAMARA = "https://www.camara.leg.br/deputados/{id}"


@dataclass(frozen=True)
class Gabinete:
    predio: Optional[str]
    sala: Optional[str]
    andar: Optional[str]
    telefone: Optional[str]
    email: Optional[str]


@dataclass(frozen=True)
class Deputado:
    id: int
    nome: str
    partido: str
    uf: str
    url_foto: Optional[str]
    situacao: Optional[str]
    condicao_eleitoral: Optional[str]
    gabinete: Gabinete
    uri_api: str
    url_site: str

    @classmethod
    def da_api(cls, dados: dict[str, Any]) -> "Deputado":
        """Constrói a partir do `dados` de GET /deputados/{id}."""
        status = dados["ultimoStatus"]
        gab = status.get("gabinete") or {}
        return cls(
            id=dados["id"],
            nome=status.get("nomeEleitoral") or status["nome"],
            partido=status["siglaPartido"],
            uf=status["siglaUf"],
            url_foto=status.get("urlFoto"),
            situacao=status.get("situacao"),
            condicao_eleitoral=status.get("condicaoEleitoral"),
            gabinete=Gabinete(
                predio=gab.get("predio"),
                sala=gab.get("sala"),
                andar=gab.get("andar"),
                telefone=gab.get("telefone"),
                email=gab.get("email"),
            ),
            uri_api=dados["uri"],
            url_site=URL_SITE_CAMARA.format(id=dados["id"]),
        )

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Deputado":
        return cls(**{**d, "gabinete": Gabinete(**d["gabinete"])})

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

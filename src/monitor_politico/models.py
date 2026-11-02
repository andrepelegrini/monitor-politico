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


URL_SITE_SENADO = "https://www25.senado.leg.br/web/senadores/senador/-/perfil/{id}"
URI_API_SENADO = "https://legis.senado.leg.br/dadosabertos/senador/{id}"


def como_lista(valor: Any) -> list[Any]:
    """O JSON do Senado é convertido de XML: um único item vem sem lista."""
    if valor is None:
        return []
    return valor if isinstance(valor, list) else [valor]


def _formatar_telefone(numero: str) -> str:
    """"33036333" -> "3303-6333", no mesmo formato da Câmara (DDD 61 no template)."""
    return f"{numero[:-4]}-{numero[-4:]}" if len(numero) == 8 else numero


@dataclass(frozen=True)
class Senador:
    id: int
    nome: str
    partido: str
    uf: str
    url_foto: Optional[str]
    condicao: Optional[str]
    bloco: Optional[str]
    fim_mandato: Optional[str]
    email: Optional[str]
    telefones: tuple[str, ...]
    uri_api: str
    url_site: str

    @classmethod
    def da_api(cls, parlamentar: dict[str, Any]) -> "Senador":
        """Constrói a partir de um item de GET /senador/lista/atual."""
        ident = parlamentar["IdentificacaoParlamentar"]
        mandato = parlamentar.get("Mandato") or {}
        legislatura = mandato.get("SegundaLegislaturaDoMandato") or mandato.get("PrimeiraLegislaturaDoMandato") or {}
        telefones = sorted(como_lista((ident.get("Telefones") or {}).get("Telefone")), key=lambda t: int(t.get("OrdemPublicacao", 0)))
        foto = ident.get("UrlFotoParlamentar")
        id_ = int(ident["CodigoParlamentar"])
        return cls(
            id=id_,
            nome=ident["NomeParlamentar"],
            partido=ident["SiglaPartidoParlamentar"],
            uf=ident["UfParlamentar"],
            url_foto=foto.replace("http://", "https://", 1) if foto else None,
            condicao=mandato.get("DescricaoParticipacao"),
            bloco=(ident.get("Bloco") or {}).get("NomeBloco"),
            fim_mandato=legislatura.get("DataFim"),
            email=ident.get("EmailParlamentar"),
            telefones=tuple(_formatar_telefone(t["NumeroTelefone"]) for t in telefones),
            uri_api=URI_API_SENADO.format(id=id_),
            url_site=URL_SITE_SENADO.format(id=id_),
        )

    @classmethod
    def de_dict(cls, d: dict[str, Any]) -> "Senador":
        return cls(**{**d, "telefones": tuple(d["telefones"])})

    def para_dict(self) -> dict[str, Any]:
        return asdict(self)

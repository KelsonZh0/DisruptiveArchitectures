"""Pydantic contracts for requests and grounded model output."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class HistoryMessage(BaseModel):
    papel: Literal["user", "assistant"]
    conteudo: str = Field(min_length=1, max_length=4000)


class AskRequest(BaseModel):
    pergunta: str = Field(min_length=1, max_length=10000)
    historico: list[HistoryMessage] = Field(default_factory=list, max_length=40)
    conversa_id: str | None = None
    conversa_token: str | None = Field(default=None, max_length=256)


class Source(BaseModel):
    titulo: str
    url: HttpUrl


class AskResponse(BaseModel):
    resposta: str
    fontes: list[Source] = Field(default_factory=list)
    conversa_id: str | None = None
    conversa_token: str | None = None


class ModelAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resposta: str = Field(min_length=1, max_length=12000)
    ids_trechos_usados: list[str] = Field(default_factory=list, max_length=20)
    encontrou_no_material: bool


class Chunk(BaseModel):
    id: str
    titulo: str
    secao: str = ""
    url: str
    texto: str
    score: float = 0
    ranks: dict[str, int] = Field(default_factory=dict)

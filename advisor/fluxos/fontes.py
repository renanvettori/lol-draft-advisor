"""Interfaces esperadas pelos fluxos para coletar dados externos."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from advisor.domain.comparacoes import RunaStat
from advisor.domain.draft import Draft
from advisor.domain.modelos import (
    CatalogoJogo,
    DadosDeBuild,
    PaginaRunas,
    PaginasDoDraft,
)


@dataclass(frozen=True)
class RecortesColeta:
    pagina_base_elo: str
    pagina_base_janela: str
    matchups_elo: str
    matchups_janela: str
    referencia_elo: str


@dataclass(frozen=True)
class FalhaColeta:
    etapa: str
    resumo: str
    detalhe_tecnico: str


@dataclass(frozen=True)
class ColetaDoDraft:
    pagina_base: DadosDeBuild
    paginas_do_draft: PaginasDoDraft | None = None
    comparacao_elo_alto: tuple[str, PaginaRunas] | None = None
    estatisticas_de_runa: tuple[RunaStat, ...] = ()
    falhas: tuple[FalhaColeta, ...] = ()


class FonteDeDados(Protocol):
    def coletar_draft(
        self,
        draft: Draft,
        recortes: RecortesColeta,
        catalogo: CatalogoJogo,
        relevancia: dict[str, float],
    ) -> ColetaDoDraft: ...

    def coletar_paginas(
        self,
        draft: Draft,
        *,
        elo: str,
        janela: str,
        catalogo: CatalogoJogo,
        relevancia: dict[str, float],
    ) -> PaginasDoDraft: ...


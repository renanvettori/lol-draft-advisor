"""Fluxo opcional de análise estatística, separado da recomendação acionável."""

from __future__ import annotations

from dataclasses import dataclass
import traceback

from advisor.domain.modelos import Champion, PaginasDoDraft
from advisor.domain import analise
from advisor.fluxos.execucao import ContextoExecucao
from advisor.domain.draft import Draft


@dataclass(frozen=True)
class ResultadoAnalise:
    paginas: PaginasDoDraft | None = None
    scores: dict[str, list[analise.Score]] | None = None
    usados: tuple[Champion, ...] = ()
    deslocamento: float = 0.0
    falha: "FalhaExecucao | None" = None


def executar(draft: Draft, contexto: ContextoExecucao) -> ResultadoAnalise | None:
    cfg, static = contexto.config, contexto.dados_estaticos
    if not cfg.analise_habilitada or not draft.enemies:
        return None
    try:
        if contexto.fonte is None:
            raise RuntimeError("nenhuma fonte de dados foi fornecida")
        paginas = contexto.fonte.coletar_paginas(
            draft, elo=cfg.analise_elo, janela=cfg.analise_janela_dias,
            catalogo=static, relevancia=cfg.relevancia)
        scores, usados, deslocamento = analise.analisar(
            paginas, validos=static.itens_finais)
        return ResultadoAnalise(paginas, scores, tuple(usados), deslocamento)
    except Exception:  # noqa: BLE001 — investigação não derruba recomendação
        from advisor.fluxos.execucao import FalhaExecucao
        return ResultadoAnalise(falha=FalhaExecucao(
            "analise_estatistica", "não consegui executar a análise estatística",
            traceback.format_exc()))


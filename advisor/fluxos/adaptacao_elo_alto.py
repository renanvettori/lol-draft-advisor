"""Carrega o recorte configurado para o motor experimental."""

from __future__ import annotations

from advisor import config
from advisor.domain import adaptacao
from advisor.domain.draft import Draft
from advisor.domain.modelos import CatalogoJogo
from advisor.fluxos.fontes import FonteDeDados


def _suficiente(paginas, cfg: config.Config, inimigos: int) -> bool:
    if paginas.base is None or paginas.ausentes or len(paginas.paginas) != inimigos:
        return False
    jogos = [p.build.games for p in paginas.paginas]
    return bool(
        jogos
        and sum(jogos) >= cfg.adaptacao_jogos_totais_minimos
        and min(jogos) >= cfg.adaptacao_jogos_por_matchup_minimos
    )


def executar(
    draft: Draft,
    fonte: FonteDeDados,
    catalogo: CatalogoJogo,
    cfg: config.Config,
) -> adaptacao.ResultadoAdaptacao:
    tentados: list[str] = []
    ultima_falha = "nenhum recorte teve volume suficiente"
    ultima_pagina = None
    ultimo_elo = ""
    for elo in cfg.adaptacao_elos:
        tentados.append(elo)
        try:
            paginas = fonte.coletar_paginas(
                draft, elo=elo, janela=cfg.adaptacao_janela_dias,
                catalogo=catalogo, relevancia=cfg.relevancia)
        except Exception as exc:  # noqa: BLE001 — registra falha da fonte
            ultima_falha = f"{elo}: {exc}"
            continue
        if paginas.base is not None:
            ultima_pagina = paginas
            ultimo_elo = elo
        if not _suficiente(paginas, cfg, len(draft.enemies)):
            ultima_falha = f"{elo}: amostra insuficiente para adaptação"
            continue
        return adaptacao.calcular(
            paginas, elo=elo,
            criterios=adaptacao.CriteriosAdaptacao(
                z_principal=cfg.adaptacao_z_principal,
                z_alternativa=cfg.adaptacao_z_alternativa,
                corrigir_multiplos_itens=(
                    cfg.adaptacao_corrigir_multiplos_itens),
                fdr_botas=cfg.adaptacao_fdr_botas,
                deflator_sobreposicao=(
                    cfg.adaptacao_deflator_sobreposicao),
                max_alternativas=cfg.adaptacao_max_alternativas,
            ),
            validos=catalogo.itens_finais,
            elos_tentados=tuple(tentados),
            lane=getattr(draft, "lane", ""),
        )
    if ultima_pagina is not None:
        return adaptacao.build_popular(
            ultima_pagina,
            elo=ultimo_elo,
            validos=catalogo.itens_finais,
            lane=getattr(draft, "lane", ""),
            elos_tentados=tuple(tentados),
            motivo=(f"{ultima_falha}; usando a build popular "
                    "sem adaptação"),
        )
    return adaptacao.indisponivel(tentados, ultima_falha)


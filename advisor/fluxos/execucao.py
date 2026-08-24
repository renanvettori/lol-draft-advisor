"""Executa um snapshot do Draft atrás de uma interface pequena.

Este módulo concentra coleta, decisão e aplicação, mas não imprime e não
controla o ciclo do champ select. A apresentação e o vigia são callers.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, replace

from advisor import config
from advisor.client import lcu, perks
from advisor.domain import adaptacao, comparacoes, recomendador
from advisor.domain.draft import Draft
from advisor.domain.modelos import CatalogoJogo, DadosDeBuild, PaginaRunas, PaginasDoDraft
from advisor.domain.recomendador import RecomendacaoDoDraft
from advisor.fluxos.fontes import FonteDeDados, RecortesColeta
from advisor.fluxos import adaptacao_elo_alto


@dataclass(frozen=True)
class FalhaExecucao:
    etapa: str
    resumo: str
    detalhe_tecnico: str


@dataclass
class ContextoExecucao:
    config: config.Config
    dados_estaticos: CatalogoJogo
    client: lcu.LCU | None = None
    fonte: FonteDeDados | None = None


@dataclass(frozen=True)
class ResultadoDoDraft:
    draft: Draft
    pagina_base: DadosDeBuild
    paginas_do_draft: PaginasDoDraft | None
    recomendacao: RecomendacaoDoDraft
    comparacao_elo_alto: tuple[str, PaginaRunas] | None = None
    estatisticas_de_runa: tuple[comparacoes.RunaStat, ...] = ()
    falhas: tuple[FalhaExecucao, ...] = ()
    adaptacao_elo_alto: adaptacao.ResultadoAdaptacao | None = None


@dataclass(frozen=True)
class ResultadoAplicacao:
    estados: dict[str, str]
    pagina: perks.Resultado | None = None
    ordem_feiticos: tuple[int, ...] | None = None
    falhas: tuple[FalhaExecucao, ...] = ()


def janela_consulta(valor: str) -> str | None:
    return None if valor == "patch_atual" else valor


def resolver_elos(contexto: ContextoExecucao) -> None:
    """Resolve ``meu_elo`` uma vez, usando o client já fornecido."""
    cfg = contexto.config
    detectado = None
    precisa = {cfg.pagina_base_elo, cfg.matchups_elo} & {"", "meu_elo"}
    if precisa and contexto.client is not None:
        try:
            detectado = lcu.ranked_tier(contexto.client)
        except Exception:  # noqa: BLE001 — usa fallback documentado
            pass
    elo_real = detectado[0] if detectado else "emerald_plus"
    if cfg.pagina_base_elo in {"", "meu_elo"}:
        cfg.pagina_base_elo = elo_real
        cfg.tier_label = (f"{detectado[1]} (seu elo)" if detectado
                          else "emerald_plus (padrão)")
    else:
        cfg.tier_label = cfg.pagina_base_elo
    if cfg.matchups_elo in {"", "meu_elo"}:
        cfg.matchups_elo = elo_real


def _falha(etapa: str, resumo: str) -> FalhaExecucao:
    return FalhaExecucao(etapa, resumo, traceback.format_exc())


def executar_draft(draft: Draft, contexto: ContextoExecucao) -> ResultadoDoDraft:
    """Coleta e decide um Draft; só a ausência da página base levanta erro."""
    cfg, static = contexto.config, contexto.dados_estaticos
    resolver_elos(contexto)
    if contexto.fonte is None:
        raise RuntimeError("nenhuma fonte de dados foi fornecida")
    coleta = contexto.fonte.coletar_draft(
        draft,
        RecortesColeta(
            cfg.pagina_base_elo, cfg.pagina_base_janela,
            cfg.matchups_elo, cfg.matchups_janela_dias,
            cfg.referencia_elo),
        static, cfg.relevancia)
    build = coleta.pagina_base
    paginas = coleta.paginas_do_draft
    falhas = [FalhaExecucao(f.etapa, f.resumo, f.detalhe_tecnico)
              for f in coleta.falhas]

    rec = recomendador.recomendar(recomendador.EntradaRecomendacao(
        pagina_base=build,
        paginas_do_draft=paginas,
        dados_estaticos=static,
        criterios=recomendador.CriteriosRecomendacao(
            z_minimo=cfg.z_minimo, jogos_minimos=cfg.jogos_minimos),
        recorte_pagina_base=recomendador.Recorte(
            cfg.pagina_base_elo, cfg.pagina_base_janela),
        recorte_matchups=recomendador.Recorte(
            cfg.matchups_elo, f"{cfg.matchups_janela_dias} dias"),
    ))

    return ResultadoDoDraft(
        draft, build, paginas, rec, coleta.comparacao_elo_alto,
        coleta.estatisticas_de_runa, tuple(falhas),
    )


def recalcular_itens_confirmados(
    anterior: ResultadoDoDraft,
    draft_confirmado: Draft,
    contexto: ContextoExecucao,
) -> ResultadoDoDraft:
    """Troca somente a Sequência usando as rotas oficiais da partida.

    Runas e Feitiços permanecem exatamente como foram decididos no champ select:
    quando a porta 2999 aparece, essas escolhas já estão bloqueadas no client.
    """
    if not draft_confirmado.rotas_confirmadas:
        raise ValueError("o recálculo final exige rotas confirmadas")
    if contexto.fonte is None:
        raise RuntimeError("nenhuma fonte de dados foi fornecida")
    cfg, static = contexto.config, contexto.dados_estaticos
    paginas = contexto.fonte.coletar_paginas(
        draft_confirmado, elo=cfg.matchups_elo,
        janela=cfg.matchups_janela_dias, catalogo=static,
        relevancia=cfg.relevancia)
    # Itens são a única parte recalculada depois das rotas confirmadas.
    # Runas e feitiços permanecem bloqueados desde o champ select.
    recomendacao_final = anterior.recomendacao
    resultado_adaptacao = anterior.adaptacao_elo_alto
    if cfg.adaptacao_habilitada:
        try:
            resultado_adaptacao = adaptacao_elo_alto.executar(
                draft_confirmado, contexto.fonte, static, cfg)
        except Exception:  # noqa: BLE001 — o motor principal continua válido
            resultado_adaptacao = adaptacao.ResultadoAdaptacao(
                adaptacao.EstadoAdaptacao.ERRO,
                falha="não foi possível calcular a adaptação de elo alto")
    return replace(
        anterior, draft=draft_confirmado, paginas_do_draft=paginas,
        recomendacao=recomendacao_final,
        adaptacao_elo_alto=resultado_adaptacao)


def aplicar_recomendacao(
    resultado: ResultadoDoDraft,
    contexto: ContextoExecucao,
) -> ResultadoAplicacao:
    """Aplica categorias independentes da recomendação no client fornecido."""
    cfg, static, api = contexto.config, contexto.dados_estaticos, contexto.client
    rec = resultado.recomendacao
    estados = {"runas": "nao_solicitada", "feiticos": "nao_solicitada"}
    falhas: list[FalhaExecucao] = []
    pagina_aplicada = None
    ordem = None

    pagina_runa = rec.runas.recomendado
    quer_runas = cfg.aplicar_runas and pagina_runa is not None
    quer_feiticos = (cfg.aplicar_feiticos and rec.feiticos.aplicavel
                     and len(rec.feiticos.recomendado or ()) == 2)
    if api is None:
        if quer_runas:
            estados["runas"] = "erro_client"
        if quer_feiticos:
            estados["feiticos"] = "erro_client"
        if quer_runas or quer_feiticos:
            falhas.append(FalhaExecucao(
                "client", "League Client indisponível", "client não fornecido"))
        return ResultadoAplicacao(estados, falhas=tuple(falhas))

    if cfg.aplicar_runas and pagina_runa is not None:
        try:
            pagina_aplicada = perks.aplicar(
                api, pagina_runa, resultado.draft.champion.name, static,
                sobrescrever_id=cfg.pagina_runas or None)
            estados["runas"] = pagina_aplicada.acao
        except perks.SemEspaco as exc:
            estados["runas"] = "sem_espaco"
            falhas.append(FalhaExecucao("runas", str(exc), traceback.format_exc()))
        except Exception:  # noqa: BLE001 — feitiços ainda podem ser aplicados
            estados["runas"] = "erro"
            falhas.append(_falha("runas", "não consegui aplicar as runas"))

    if quer_feiticos:
        try:
            aplicada = perks.aplicar_feiticos(
                api, list(rec.feiticos.recomendado or ()),
                flash_no_d=cfg.flash_no_d)
            ordem = tuple(aplicada)
            estados["feiticos"] = "aplicados"
        except Exception:  # noqa: BLE001
            estados["feiticos"] = "erro"
            falhas.append(_falha("feiticos", "não consegui aplicar os feitiços"))

    return ResultadoAplicacao(
        estados, pagina_aplicada, ordem, tuple(falhas))


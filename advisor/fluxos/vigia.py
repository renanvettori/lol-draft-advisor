"""Ciclo de vida do champ select: recalcular, aplicar, descartar ou registrar."""

from __future__ import annotations

import time
from dataclasses import replace

from advisor import observabilidade
from advisor.apresentacao import html, terminal
from advisor.client import game_client, lcu
from advisor.domain.draft import Draft
from advisor.fluxos import execucao, investigacao


def assinatura(draft: Draft) -> tuple:
    return (
        draft.champion.cid,
        draft.lane,
        tuple(sorted(c.cid for c in draft.enemies)),
        draft.opponent.cid if draft.opponent else 0,
    )


def _processar(
    draft: Draft,
    contexto: execucao.ContextoExecucao,
    *,
    aplicar: bool,
) -> tuple[execucao.ResultadoDoDraft, execucao.ResultadoAplicacao]:
    resultado = execucao.executar_draft(draft, contexto)
    contexto_aplicacao = contexto
    if not aplicar:
        cfg = replace(contexto.config, aplicar_runas=False, aplicar_feiticos=False)
        contexto_aplicacao = execucao.ContextoExecucao(
            cfg, contexto.dados_estaticos, contexto.client, contexto.fonte)
    aplicacao = execucao.aplicar_recomendacao(resultado, contexto_aplicacao)
    analise = investigacao.executar(draft, contexto)
    terminal.apresentar(resultado, contexto, aplicacao, analise)
    observabilidade.registrar_falhas(resultado.recomendacao)
    falhas = [*resultado.falhas, *aplicacao.falhas]
    if analise is not None and analise.falha:
        falhas.append(analise.falha)
    observabilidade.registrar_falhas_tecnicas(falhas)
    return resultado, aplicacao


def executar_uma_vez(contexto: execucao.ContextoExecucao) -> None:
    api = contexto.client
    if api is None:
        raise lcu.LCUError("League Client indisponível")
    session = api.champ_select()
    if not session:
        raise lcu.LCUError(
            f"não está em champ select (fase atual: {api.phase()})")
    draft = lcu.read_draft(session, contexto.dados_estaticos)
    if draft is None:
        raise lcu.LCUError("você ainda não escolheu campeão")
    _processar(draft, contexto, aplicar=True)


def observar(contexto: execucao.ContextoExecucao) -> None:
    api = contexto.client
    if api is None:
        raise lcu.LCUError("League Client indisponível")

    terminal.status_vigia("observando o client — Ctrl+C para sair")
    ultima_assinatura = None
    notificou_espera = False
    ja_aplicou = False
    ultimo_resultado = None
    ultima_aplicacao = None
    notificou_confirmacao = False

    while True:
        try:
            session = api.champ_select()
            if not session:
                fase = api.phase()
                if fase == "InProgress" and ultimo_resultado and ultima_aplicacao:
                    draft_confirmado = game_client.confirmar_rotas(
                        ultimo_resultado.draft, contexto.dados_estaticos)
                    if draft_confirmado is None:
                        if not notificou_confirmacao:
                            terminal.status_vigia(
                                "aguardando posições confirmadas da partida…")
                            notificou_confirmacao = True
                        time.sleep(contexto.config.intervalo)
                        continue
                    terminal.status_vigia(
                        "posições confirmadas — recalculando a ordem de itens…")
                    try:
                        ultimo_resultado = execucao.recalcular_itens_confirmados(
                            ultimo_resultado, draft_confirmado, contexto)
                    except Exception as exc:  # noqa: BLE001 — tenta no próximo ciclo
                        observabilidade.LOGGER.exception(
                            "não consegui recalcular os itens confirmados")
                        terminal.erro_vigia(
                            f"falha ao recalcular itens; vou tentar novamente: {exc}")
                        time.sleep(contexto.config.intervalo)
                        continue
                    observabilidade.registrar_final(
                        observabilidade.ExecucaoRecomendacao(
                            ultimo_resultado.recomendacao,
                            ultima_aplicacao.estados,
                            ultimo_resultado.adaptacao_elo_alto),
                        ultimo_resultado.draft,
                    )
                    if contexto.config.html_habilitado:
                        try:
                            caminho = html.gerar(
                                ultimo_resultado, contexto, ultima_aplicacao)
                            terminal.status_vigia(
                                f"recomendação final salva em {caminho}")
                            if contexto.config.html_abrir_automaticamente:
                                html.abrir(caminho)
                        except Exception as exc:  # noqa: BLE001 — vigia continua
                            observabilidade.LOGGER.exception(
                                "não consegui gerar o relatório HTML")
                            terminal.erro_vigia(
                                f"não consegui gerar o relatório HTML: {exc}")
                    ultimo_resultado = ultima_aplicacao = None
                    notificou_confirmacao = False
                elif fase in {None, "None", "Lobby"}:
                    # Dodge: nenhum histórico é criado.
                    ultimo_resultado = ultima_aplicacao = None
                    notificou_confirmacao = False
                if not notificou_espera:
                    terminal.status_vigia("aguardando champ select…")
                    notificou_espera = True
                ultima_assinatura = None
                ja_aplicou = False
            else:
                notificou_espera = False
                notificou_confirmacao = False
                draft = lcu.read_draft(session, contexto.dados_estaticos)
                if draft is not None and assinatura(draft) != ultima_assinatura:
                    ultima_assinatura = assinatura(draft)
                    deve_aplicar = (contexto.config.reaplicar_a_cada_mudanca
                                    or not ja_aplicou)
                    ja_aplicou = ja_aplicou or deve_aplicar
                    try:
                        ultimo_resultado, ultima_aplicacao = _processar(
                            draft, contexto, aplicar=deve_aplicar)
                    except Exception as exc:  # noqa: BLE001 — vigia continua
                        ultima_assinatura = None
                        observabilidade.LOGGER.exception(
                            "não consegui montar a recomendação")
                        terminal.erro_vigia(
                            f"não consegui montar a recomendação: {exc}")
        except lcu.LCUError as exc:
            terminal.erro_vigia(f"client indisponível: {exc}")
            return
        except KeyboardInterrupt:
            return
        try:
            time.sleep(contexto.config.intervalo)
        except KeyboardInterrupt:
            return


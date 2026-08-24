"""Posições confirmadas pelo cliente da partida, na porta local 2999."""

from __future__ import annotations

from dataclasses import replace

import requests
import urllib3

from advisor.domain.draft import Draft
from advisor.domain.modelos import CatalogoJogo

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

POSICOES = {
    "TOP": "top", "JUNGLE": "jungle", "MIDDLE": "middle",
    "BOTTOM": "bottom", "UTILITY": "support", "SUPPORT": "support",
}
URL = "https://127.0.0.1:2999/liveclientdata/playerlist"


def confirmar_rotas(
    draft: Draft,
    catalogo: CatalogoJogo,
    *,
    buscar=requests.get,
) -> Draft | None:
    """Devolve o mesmo Draft com as cinco rotas oficiais, ou ``None``.

    ``None`` significa apenas que a partida ainda não expôs uma lista completa;
    o caller pode tentar novamente sem interpretar isso como falha definitiva.
    """
    try:
        resposta = buscar(URL, timeout=1.5, verify=False)
        resposta.raise_for_status()
        jogadores = resposta.json()
    except (requests.RequestException, ValueError, TypeError):
        return None
    if not isinstance(jogadores, list) or len(jogadores) < 10:
        return None

    resolvidos = []
    for jogador in jogadores:
        nome = jogador.get("championName", "")
        if not nome:
            nome = str(jogador.get("rawChampionName", "")).removeprefix(
                "game_character_displayname_")
        campeao = catalogo.champion(nome)
        rota = POSICOES.get(str(jogador.get("position", "")).upper())
        time = jogador.get("team")
        if campeao is not None and rota and time:
            resolvidos.append((campeao, rota, time))

    eu = next((x for x in resolvidos if x[0].cid == draft.champion.cid), None)
    if eu is None:
        return None
    inimigos = [x for x in resolvidos if x[2] != eu[2]]
    esperados = {c.cid for c in draft.enemies}
    if len(inimigos) != 5 or {c.cid for c, _, _ in inimigos} != esperados:
        return None

    rotas = {campeao.cid: rota for campeao, rota, _ in inimigos}
    if set(rotas.values()) != {"top", "jungle", "middle", "bottom", "support"}:
        return None
    opponent = next(
        (campeao for campeao, rota, _ in inimigos if rota == draft.lane), None)
    return replace(draft, opponent=opponent, rotas_inimigas=rotas,
                   rotas_confirmadas=True)


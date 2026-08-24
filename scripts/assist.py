"""Espera o draft fechar, imprime uma recomendação e encerra."""

from __future__ import annotations

import argparse
import time

from advisor import config
from advisor import cli
from advisor.client import lcu
from advisor.data import ddragon

TIMEOUT_SECONDS = 45 * 60
JANELA_PICKS = 150


def main() -> int:
    cfg = config.aplicar_argumentos(config.carregar(), argparse.Namespace())
    static = ddragon.load()
    try:
        api = lcu.LCU()
    except lcu.LCUError as exc:
        print(f"sem client: {exc}")
        return 2

    print(f"aguardando champ select (limite de {TIMEOUT_SECONDS // 60} min)…", flush=True)
    limite = time.time() + TIMEOUT_SECONDS
    prazo_picks = limite
    ultima_fase = None
    cs_visto = False
    anunciado = False
    ultimo_draft = None

    while time.time() < limite:
        try:
            session = api.champ_select()
        except lcu.LCUError as exc:
            print(f"client sumiu: {exc}")
            return 2

        if session:
            if not cs_visto:
                cs_visto = True
                prazo_picks = time.time() + JANELA_PICKS
                print("champ select aberto", flush=True)

            draft = lcu.read_draft(session, static)
            if draft is not None:
                ultimo_draft = draft
                if not anunciado:
                    print(f"você está de {draft.champion.name}"
                          f"{' no ' + draft.lane if draft.lane else ''}", flush=True)
                    anunciado = True
                # Aguarda os cinco inimigos ou o prazo dos picks.
                if len(draft.enemies) >= 5 or time.time() >= prazo_picks:
                    cli.report(draft, static, cfg)
                    return 0

        elif cs_visto:
            # Usa o último estado se o champ select terminar antes do relatório.
            if ultimo_draft is not None:
                print("champ select encerrou — relatório com o que foi visto:")
                cli.report(ultimo_draft, static, cfg)
                return 0
            print("champ select encerrou sem campeão escolhido")
            return 1

        else:
            try:
                fase = api.phase()
            except lcu.LCUError:
                fase = "?"
            if fase != ultima_fase:
                print(f"fase: {fase}", flush=True)
                ultima_fase = fase

        time.sleep(cfg.intervalo)

    print("tempo esgotado sem champ select")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())


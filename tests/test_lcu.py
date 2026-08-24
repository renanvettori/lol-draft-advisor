"""Testes da leitura do champ select, com sessões sintéticas no formato da LCU.

Permite validar o parsing sem estar em partida. Para conferir contra uma sessão
de verdade: entre em champ select e importe ``advisor.client.lcu``.
"""

import sys
from pathlib import Path

# O projeto é plano; os testes vivem numa subpasta.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advisor.client import lcu  # noqa: E402
from advisor.data import ddragon  # noqa: E402

static = ddragon.load()

# Ashe (22) no bottom. Inimigos: Caitlyn (51) no bottom, Leona (89) de suporte,
# Viego (234), K'Sante (897) e Hwei (910).
SESSION = {
    "localPlayerCellId": 0,
    "myTeam": [
        {"cellId": 0, "championId": 22, "championPickIntent": 0, "assignedPosition": "bottom"},
        {"cellId": 1, "championId": 412, "championPickIntent": 0, "assignedPosition": "utility"},
        {"cellId": 2, "championId": 64, "championPickIntent": 0, "assignedPosition": "jungle"},
        {"cellId": 3, "championId": 103, "championPickIntent": 0, "assignedPosition": "middle"},
        {"cellId": 4, "championId": 86, "championPickIntent": 0, "assignedPosition": "top"},
    ],
    "theirTeam": [
        {"cellId": 5, "championId": 51, "championPickIntent": 0, "assignedPosition": "bottom"},
        {"cellId": 6, "championId": 89, "championPickIntent": 0, "assignedPosition": "utility"},
        {"cellId": 7, "championId": 234, "championPickIntent": 0, "assignedPosition": "jungle"},
        {"cellId": 8, "championId": 897, "championPickIntent": 0, "assignedPosition": "top"},
    ],
    # Hwei aparece só na lista de ações — caso real em que o theirTeam ainda não
    # refletiu o pick travado.
    "actions": [[
        {"actorCellId": 9, "championId": 910, "completed": True,
         "isAllyAction": False, "type": "pick"},
        {"actorCellId": 0, "championId": 22, "completed": True,
         "isAllyAction": True, "type": "pick"},
        {"actorCellId": 5, "championId": 99, "completed": True,
         "isAllyAction": False, "type": "ban"},
    ]],
}


def test_draft_completo():
    draft = lcu.read_draft(SESSION, static)
    assert draft is not None
    assert draft.champion.name == "Ashe"
    assert draft.lane == "bottom"
    assert draft.opponent is not None and draft.opponent.name == "Caitlyn"

    nomes = sorted(c.name for c in draft.enemies)
    assert nomes == sorted(["Caitlyn", "Leona", "Viego", "K'Sante", "Hwei"]), nomes
    # Lux foi banida, não escolhida: não pode entrar como inimiga.
    assert "Lux" not in nomes
    assert len(draft.allies) == 4


def test_hover_conta_como_pick():
    """Campeão só com o mouse em cima (intent) já deve gerar recomendação."""
    session = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 0, "championPickIntent": 22,
                    "assignedPosition": "bottom"}],
        "theirTeam": [],
        "actions": [],
    }
    draft = lcu.read_draft(session, static)
    assert draft is not None and draft.champion.name == "Ashe"


def test_sem_campeao_ainda():
    session = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 0, "championPickIntent": 0,
                    "assignedPosition": "bottom"}],
        "theirTeam": [], "actions": [],
    }
    assert lcu.read_draft(session, static) is None


def test_sem_posicao_nao_chuta_oponente():
    """Em filas sem posição atribuída, o oponente direto deve ficar vazio."""
    session = {
        "localPlayerCellId": 0,
        "myTeam": [{"cellId": 0, "championId": 22, "championPickIntent": 0,
                    "assignedPosition": ""}],
        "theirTeam": [{"cellId": 5, "championId": 51, "championPickIntent": 0,
                       "assignedPosition": ""}],
        "actions": [],
    }
    draft = lcu.read_draft(session, static)
    assert draft is not None
    assert draft.lane == ""
    assert draft.opponent is None
    assert [c.name for c in draft.enemies] == ["Caitlyn"]


if __name__ == "__main__":
    falhas = 0
    for nome, func in sorted(globals().items()):
        if nome.startswith("test_"):
            try:
                func()
                print(f"OK   {nome}")
            except AssertionError as exc:
                falhas += 1
                print(f"FALHOU {nome}: {exc}")
    raise SystemExit(1 if falhas else 0)


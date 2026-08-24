from __future__ import annotations

import math

from advisor.domain.comparacoes import (
    ObservacaoPareada,
    combinar_pareadas,
    variancia_wr,
)


def test_combina_por_variancia_e_relevancia():
    resultado = combinar_pareadas([
        ObservacaoPareada(delta=2.0, variancia=4.0, peso=2.0, jogos=100),
        ObservacaoPareada(delta=-1.0, variancia=1.0, peso=1.0, jogos=200),
    ])

    assert resultado is not None
    assert math.isclose(resultado.delta, 0.0)
    assert math.isclose(resultado.erro, math.sqrt(2 / 3))
    assert resultado.jogos == 300
    assert resultado.matchups == 2


def test_ignora_observacao_sem_peso():
    resultado = combinar_pareadas([
        ObservacaoPareada(delta=99.0, variancia=1.0, peso=0.0, jogos=999),
        ObservacaoPareada(delta=1.5, variancia=2.0, peso=1.0, jogos=50),
    ])

    assert resultado is not None
    assert resultado.delta == 1.5
    assert resultado.jogos == 50
    assert resultado.matchups == 1


def test_sem_contribuinte_devolve_none():
    assert combinar_pareadas([]) is None
    assert combinar_pareadas([
        ObservacaoPareada(delta=1.0, variancia=1.0, peso=0.0, jogos=10),
    ]) is None


def test_variancia_wr_permanece_em_pontos_percentuais():
    assert math.isclose(variancia_wr(50.0, 100), 25.0)


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


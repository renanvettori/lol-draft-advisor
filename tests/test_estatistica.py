from __future__ import annotations

import math
from statistics import NormalDist
from types import SimpleNamespace

import pytest

from advisor.domain.comparacoes import (
    ObservacaoPareada,
    combinar_pareadas,
    variancia_wr,
)
from advisor.domain.estatistica import (
    EfeitoPareado,
    combinar_efeitos_aleatorios,
    combinar_efeitos_pareados,
    corrigir_fdr,
    intervalo_win_rate,
    p_valor_bilateral,
    variancia_win_rate,
)


def _corrigir_fdr_anterior(
    scores: list[SimpleNamespace],
    alpha: float = 0.05,
) -> list[SimpleNamespace]:
    """Implementação anterior mantida como referência de paridade."""
    normal = NormalDist()
    ordenados = sorted(
        ((2 * (1 - normal.cdf(abs(score.z))), score) for score in scores),
        key=lambda par: par[0],
    )
    sobreviventes: list[SimpleNamespace] = []
    for indice, (p_valor, _) in enumerate(ordenados, start=1):
        if p_valor <= alpha * indice / len(ordenados):
            sobreviventes = [score for _, score in ordenados[:indice]]
    return sobreviventes


def _efeitos_aleatorios_anterior(
    efeitos: list[float],
    variancias: list[float],
    prior_sd: float,
) -> tuple[float, float, float]:
    """Cálculo anterior mantido como referência de paridade."""
    pesos = [1.0 / variancia for variancia in variancias]
    fixo = sum(peso * efeito for peso, efeito in zip(pesos, efeitos)) / sum(pesos)
    q = sum(peso * (efeito - fixo) ** 2
            for peso, efeito in zip(pesos, efeitos))
    c = sum(pesos) - sum(peso * peso for peso in pesos) / sum(pesos)
    tau2 = max(0.0, (q - (len(efeitos) - 1)) / c) if c > 0 else 0.0
    ajustados = [1.0 / (variancia + tau2)
                 for variancia in variancias]
    soma_pesos = sum(ajustados)
    efeito_bruto = sum(peso * efeito
                       for peso, efeito in zip(ajustados, efeitos))
    precisao = soma_pesos + 1.0 / (prior_sd * prior_sd)
    return (
        efeito_bruto / precisao,
        math.sqrt(1.0 / precisao),
        tau2,
    )


def test_variancia_nova_mantem_paridade_com_calculo_atual() -> None:
    for wr, jogos in ((50.0, 100), (62.5, 320), (100.0, 20), (0.0, 20)):
        assert variancia_win_rate(wr, jogos) == variancia_wr(wr, jogos)
    assert variancia_win_rate(50.0, 200) < variancia_win_rate(50.0, 100)


def test_combinacao_nova_mantem_paridade_com_calculo_atual() -> None:
    observacoes = [
        ObservacaoPareada(delta=2.0, variancia=4.0, peso=2.0, jogos=100),
        ObservacaoPareada(delta=-1.0, variancia=1.0, peso=1.0, jogos=200),
    ]
    efeitos = [
        EfeitoPareado(
            delta=obs.delta,
            variancia=obs.variancia,
            peso=obs.peso,
            jogos=obs.jogos,
            detalhe=obs.detalhe,
        )
        for obs in observacoes
    ]

    atual = combinar_pareadas(observacoes)
    novo = combinar_efeitos_pareados(efeitos)

    assert atual is not None
    assert novo is not None
    assert math.isclose(novo.delta, atual.delta)
    assert math.isclose(novo.erro, atual.erro)
    assert novo.jogos == atual.jogos
    assert novo.matchups == atual.matchups


def test_efeitos_aleatorios_mantem_paridade_com_calculo_atual() -> None:
    efeitos = [-1.0, 1.5, 3.0]
    variancias = [0.5, 1.0, 2.0]
    antigo = _efeitos_aleatorios_anterior(efeitos, variancias, 3.0)
    novo = combinar_efeitos_aleatorios(
        efeitos,
        variancias,
        prior_sd=3.0,
    )

    assert math.isclose(novo.efeito, antigo[0])
    assert math.isclose(novo.erro, antigo[1])
    assert math.isclose(novo.tau2, antigo[2])


def test_prior_contrai_efeito_heterogeneo_em_direcao_a_zero() -> None:
    sem_prior = combinar_efeitos_aleatorios(
        [1.0, 2.0, 3.0],
        [0.5, 0.5, 0.5],
    )
    com_prior = combinar_efeitos_aleatorios(
        [1.0, 2.0, 3.0],
        [0.5, 0.5, 0.5],
        prior_sd=1.0,
    )

    assert abs(com_prior.efeito) < abs(sem_prior.efeito)
    assert com_prior.erro < sem_prior.erro


def test_intervalo_de_win_rate_usa_percentuais() -> None:
    intervalo = intervalo_win_rate(50, 100)

    assert intervalo.estimativa == 50.0
    assert 35.0 < intervalo.inferior < 45.0
    assert 55.0 < intervalo.superior < 65.0


def test_intervalo_rejeita_amostra_invalida() -> None:
    with pytest.raises(ValueError, match="jogos"):
        intervalo_win_rate(1, 0)
    with pytest.raises(ValueError, match="vitorias"):
        intervalo_win_rate(11, 10)


def test_p_valor_bilateral_e_fdr_preservam_ordem() -> None:
    scores = [SimpleNamespace(z=z) for z in (3.0, 1.0, 0.2, 2.0)]
    p_valores = [p_valor_bilateral(score.z) for score in scores]
    resultado = corrigir_fdr(p_valores)
    atual = _corrigir_fdr_anterior(scores)

    assert len(resultado.rejeitadas) == 4
    assert len(resultado.p_valores_ajustados) == 4
    assert resultado.rejeitadas[0] is True
    assert resultado.rejeitadas == tuple(score in atual for score in scores)
    assert resultado.rejeitadas[2] is False
    assert resultado.p_valores_ajustados[0] < resultado.p_valores_ajustados[1]


def test_fdr_mantem_p_valores_ajustados_monotonicos() -> None:
    resultado = corrigir_fdr([0.001, 0.01, 0.20, 0.80])

    assert list(resultado.p_valores_ajustados) == sorted(
        resultado.p_valores_ajustados
    )


"""Primitivas estatísticas usadas pelo domínio do advisor.

Este módulo concentra as bibliotecas estatísticas para que o restante do
domínio trabalhe com contratos simples, sem depender diretamente de SciPy ou
statsmodels.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import sqrt
from warnings import catch_warnings, simplefilter

import numpy as np
from scipy.stats import binomtest, norm
from statsmodels.stats.meta_analysis import combine_effects
from statsmodels.stats.multitest import multipletests


@dataclass(frozen=True, slots=True)
class EfeitoPareado:
    """Uma diferença observada em um matchup, com sua incerteza e peso."""

    delta: float
    variancia: float
    peso: float
    jogos: int
    detalhe: tuple[str, float, int] | None = None


@dataclass(frozen=True, slots=True)
class ResultadoCombinado:
    """Resultado da combinação ponderada de vários efeitos pareados."""

    delta: float
    erro: float
    jogos: int
    matchups: int
    detalhe: tuple[tuple[str, float, int], ...] = ()

    @property
    def z(self) -> float:
        """Retorna o efeito combinado em unidades de erro padrão."""
        return self.delta / self.erro if self.erro else 0.0


@dataclass(frozen=True, slots=True)
class IntervaloProporcao:
    """Estimativa percentual e intervalo de confiança de uma proporção."""

    estimativa: float
    inferior: float
    superior: float


@dataclass(frozen=True, slots=True)
class ResultadoFdr:
    """Decisão e p-valores ajustados na mesma ordem da entrada."""

    rejeitadas: tuple[bool, ...]
    p_valores_ajustados: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class ResultadoEfeitosAleatorios:
    """Efeito combinado com variância entre matchups e contração opcional."""

    efeito: float
    erro: float
    tau2: float
    heterogeneidade: float


def variancia_win_rate(wr: float, jogos: int) -> float:
    """Calcula a variância de um win rate expresso em pontos percentuais.

    O limite da proporção mantém a convenção usada pelo cálculo anterior para
    evitar variância nula em amostras com 0% ou 100% de vitórias.
    """
    proporcao = min(max(wr / 100.0, 0.001), 0.999)
    return 10000.0 * proporcao * (1 - proporcao) / max(jogos, 1)


def combinar_efeitos_pareados(
    efeitos: Iterable[EfeitoPareado],
) -> ResultadoCombinado | None:
    """Combina efeitos por precisão e relevância, ignorando pesos inválidos."""
    soma_pesos = 0.0
    soma_efeitos = 0.0
    jogos = 0
    detalhes: list[tuple[str, float, int]] = []
    matchups = 0

    for efeito in efeitos:
        if efeito.peso <= 0:
            continue

        peso_precisao = efeito.peso / max(efeito.variancia, 1e-9)
        soma_pesos += peso_precisao
        soma_efeitos += peso_precisao * efeito.delta
        jogos += efeito.jogos
        matchups += 1
        if efeito.detalhe is not None:
            detalhes.append(efeito.detalhe)

    if soma_pesos <= 0:
        return None

    return ResultadoCombinado(
        delta=soma_efeitos / soma_pesos,
        erro=sqrt(1.0 / soma_pesos),
        jogos=jogos,
        matchups=matchups,
        detalhe=tuple(sorted(detalhes, key=lambda detalhe: -detalhe[1])),
    )


def combinar_efeitos_aleatorios(
    efeitos: Sequence[float],
    variancias: Sequence[float],
    *,
    prior_sd: float | None = None,
) -> ResultadoEfeitosAleatorios:
    """Combina efeitos heterogêneos usando DerSimonian-Laird.

    ``statsmodels`` estima a variância entre estudos. A contração opcional
    para zero preserva o prior usado pelo motor experimental atual.
    """
    if len(efeitos) != len(variancias):
        raise ValueError("efeitos e variancias devem ter o mesmo tamanho")
    if not efeitos:
        raise ValueError("é necessário informar ao menos um efeito")
    if any(variancia <= 0 for variancia in variancias):
        raise ValueError("as variâncias devem ser maiores que zero")
    if prior_sd is not None and prior_sd <= 0:
        raise ValueError("prior_sd deve ser maior que zero")

    valores = np.asarray(efeitos, dtype=float)
    variancias_array = np.asarray(variancias, dtype=float)
    if len(valores) == 1:
        tau2 = 0.0
        heterogeneidade = 0.0
    else:
        # A versão atual do statsmodels pode emitir um aviso quando o
        # estimador DL encontra tau² negativo; o domínio o limita a zero.
        with catch_warnings():
            simplefilter("ignore", RuntimeWarning)
            combinado = combine_effects(
                valores,
                variancias_array,
                method_re="dl",
            )
        tau2 = max(0.0, float(combinado.tau2))
        heterogeneidade = max(0.0, float(combinado.i2))

    pesos = 1.0 / (variancias_array + tau2)
    soma_pesos = float(np.sum(pesos))
    efeito_bruto = float(np.sum(pesos * valores) / soma_pesos)
    erro_bruto = sqrt(1.0 / soma_pesos)

    if prior_sd is None:
        return ResultadoEfeitosAleatorios(
            efeito=efeito_bruto,
            erro=erro_bruto,
            tau2=tau2,
            heterogeneidade=heterogeneidade,
        )

    precisao = soma_pesos + 1.0 / (prior_sd * prior_sd)
    return ResultadoEfeitosAleatorios(
        efeito=efeito_bruto * soma_pesos / precisao,
        erro=sqrt(1.0 / precisao),
        tau2=tau2,
        heterogeneidade=heterogeneidade,
    )


def intervalo_win_rate(
    vitorias: int,
    jogos: int,
    *,
    nivel: float = 0.95,
) -> IntervaloProporcao:
    """Calcula intervalo exato de confiança para win rate percentual."""
    if jogos <= 0:
        raise ValueError("jogos deve ser maior que zero")
    if not 0 <= vitorias <= jogos:
        raise ValueError("vitorias deve estar entre zero e jogos")
    if not 0 < nivel < 1:
        raise ValueError("nivel deve estar entre zero e um")

    teste = binomtest(vitorias, jogos)
    intervalo = teste.proportion_ci(confidence_level=nivel, method="exact")
    return IntervaloProporcao(
        estimativa=100.0 * vitorias / jogos,
        inferior=float(100.0 * intervalo.low),
        superior=float(100.0 * intervalo.high),
    )


def p_valor_bilateral(z: float) -> float:
    """Calcula o p-valor bilateral de um z-score normal."""
    return float(2.0 * norm.sf(abs(z)))


def corrigir_fdr(
    p_valores: Sequence[float],
    *,
    alpha: float = 0.05,
) -> ResultadoFdr:
    """Aplica Benjamini-Hochberg e preserva a ordem dos p-valores."""
    if not 0 < alpha < 1:
        raise ValueError("alpha deve estar entre zero e um")
    if not p_valores:
        return ResultadoFdr((), ())
    if any(not 0 <= valor <= 1 for valor in p_valores):
        raise ValueError("p-valores devem estar entre zero e um")

    rejeitadas, ajustados, _, _ = multipletests(
        p_valores,
        alpha=alpha,
        method="fdr_bh",
    )
    return ResultadoFdr(
        rejeitadas=tuple(bool(valor) for valor in rejeitadas),
        p_valores_ajustados=tuple(float(valor) for valor in ajustados),
    )


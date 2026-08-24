"""Combina comparações pareadas dentro de cada matchup."""

from __future__ import annotations

from dataclasses import dataclass, field

from advisor.domain import estatistica


@dataclass(frozen=True)
class ObservacaoPareada:
    delta: float
    variancia: float
    peso: float
    jogos: int
    detalhe: tuple[str, float, int] | None = None


@dataclass(frozen=True)
class ResultadoPareado:
    delta: float
    erro: float
    jogos: int
    matchups: int
    detalhe: list[tuple[str, float, int]] = field(default_factory=list)

    @property
    def z(self) -> float:
        return self.delta / self.erro if self.erro else 0.0


def variancia_wr(wr: float, jogos: int) -> float:
    """Variância de um win rate expresso em pontos percentuais."""
    return estatistica.variancia_win_rate(wr, jogos)


def combinar_pareadas(
    observacoes: list[ObservacaoPareada],
) -> ResultadoPareado | None:
    """Combina diferenças pareadas por precisão e relevância do matchup."""
    resultado = estatistica.combinar_efeitos_pareados(
        estatistica.EfeitoPareado(
            delta=obs.delta,
            variancia=obs.variancia,
            peso=obs.peso,
            jogos=obs.jogos,
            detalhe=obs.detalhe,
        )
        for obs in observacoes
    )
    if resultado is None:
        return None

    return ResultadoPareado(
        delta=resultado.delta,
        erro=resultado.erro,
        jogos=resultado.jogos,
        matchups=resultado.matchups,
        detalhe=list(resultado.detalhe),
    )


@dataclass(frozen=True)
class RunaStat:
    keystone: int
    wr: float
    games: int
    share: float
    delta: float
    erro: float

    @property
    def z(self) -> float:
        return self.delta / self.erro if self.erro else 0.0


def comparar_estatisticas_runas(
    crus: dict[int, tuple[float, int]],
) -> list[RunaStat]:
    """Compara estatísticas já coletadas, sem conhecer sua fonte."""
    if not crus:
        return []

    total = sum(n for _, n in crus.values()) or 1
    padrao = max(crus, key=lambda k: crus[k][1])
    wr_p, n_p = crus[padrao]

    saida = []
    for k, (wr, n) in crus.items():
        erro = (variancia_wr(wr, n) + variancia_wr(wr_p, n_p)) ** 0.5
        saida.append(RunaStat(keystone=k, wr=wr, games=n,
                              share=n / total * 100,
                              delta=wr - wr_p, erro=erro))
    saida.sort(key=lambda r: -r.games)
    return saida


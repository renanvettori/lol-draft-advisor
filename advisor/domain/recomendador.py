"""Combina os matchups do draft e monta runas, feitiços e itens."""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Generic, TypeVar

from advisor.domain import modelos as M
from advisor.domain.comparacoes import (
    ObservacaoPareada,
    RunaStat,
    combinar_pareadas,
    variancia_wr,
)
from advisor.domain.modelos import (
    CatalogoJogo,
    PaginasDoDraft,
    pagina_mais_escolhida,
)

T = TypeVar("T")


class EstadoDecisao(StrEnum):
    PERSONALIZADA = "personalizada"
    SEM_EVIDENCIA = "sem_evidencia"
    FALTA_DADOS = "falta_dados"
    ERRO = "erro"


@dataclass(frozen=True)
class FalhaDecisao:
    codigo: str
    resumo: str
    detalhe_tecnico: str | None = None


@dataclass(frozen=True)
class Decisao(Generic[T]):
    estado: EstadoDecisao
    recomendado: T | None
    base: T | None
    trocas: tuple[Any, ...] = ()
    falha: FalhaDecisao | None = None

    @property
    def aplicavel(self) -> bool:
        return self.recomendado is not None


@dataclass(frozen=True)
class Recorte:
    elo: str
    janela: str


@dataclass(frozen=True)
class CriteriosRecomendacao:
    z_minimo: float
    jogos_minimos: int
    jogos_minimos_runa: int = 100


@dataclass(frozen=True)
class EntradaRecomendacao:
    pagina_base: M.Build
    paginas_do_draft: PaginasDoDraft | None
    dados_estaticos: CatalogoJogo
    criterios: CriteriosRecomendacao
    recorte_pagina_base: Recorte
    recorte_matchups: Recorte


@dataclass(frozen=True)
class RecomendacaoDoDraft:
    runas: Decisao[M.RunePage]
    feiticos: Decisao[tuple[int, ...]]
    sequencia: Decisao[tuple[tuple[str, int], ...]]
    recorte_pagina_base: Recorte
    recorte_matchups: Recorte


# Nos feitiços, a ausência de uma opção no site significa falta de dado, não
# evidência contra ela.

@dataclass
class Candidato:
    ids: tuple[int, ...]
    delta: float
    erro: float
    jogos: int
    matchups: int
    total_paginas: int
    detalhe: list[tuple[str, float, int]] = field(default_factory=list)
    referencia: int | None = None

    @property
    def z(self) -> float:
        return self.delta / self.erro if self.erro else 0.0


@dataclass
class _AcumuladoRuna:
    """Observações e referências reunidas para uma runa candidata."""

    observacoes: list[ObservacaoPareada] = field(default_factory=list)
    referencias: set[int] = field(default_factory=set)


def _avaliar_feiticos(
    paginas: PaginasDoDraft,
) -> tuple[tuple[int, ...] | None, list[Candidato]]:
    """Devolve o par mais comum e os candidatos ordenados pelo z-score."""
    dados = paginas.feiticos()
    if not dados:
        return None, []

    # O padrão é o par mais usado no conjunto dos matchups.
    contagem: dict[tuple[int, ...], int] = {}
    for _, spells, _ in dados:
        for sp in spells:
            chave = tuple(sorted(sp.ids))
            contagem[chave] = contagem.get(chave, 0) + sp.games
    padrao = max(contagem, key=lambda k: contagem[k])

    acumulado: dict[tuple[int, ...], list[ObservacaoPareada]] = {}
    for enemy, spells, peso in dados:
        por_chave = {tuple(sorted(sp.ids)): sp for sp in spells}
        base_sp = por_chave.get(padrao)
        if base_sp is None:
            continue
        for chave, sp in por_chave.items():
            if chave == padrao:
                continue
            delta = sp.wr - base_sp.wr
            variancia = (variancia_wr(sp.wr, sp.games)
                         + variancia_wr(base_sp.wr, base_sp.games))
            acumulado.setdefault(chave, []).append(ObservacaoPareada(
                delta, variancia, peso, sp.games,
                (enemy.name, delta, sp.games),
            ))

    candidatos = []
    for chave, observacoes in acumulado.items():
        resultado = combinar_pareadas(observacoes)
        if resultado is None:
            continue
        candidatos.append(Candidato(
            ids=chave, delta=resultado.delta, erro=resultado.erro,
            jogos=resultado.jogos, matchups=resultado.matchups,
            total_paginas=len(dados), detalhe=resultado.detalhe,
        ))
    candidatos.sort(key=lambda c: -c.z)
    return padrao, candidatos


avaliar_feiticos = _avaliar_feiticos


# Cada runa compete apenas com alternativas da mesma vaga. A comparação é
# pareada por matchup e ponderada por amostra e relevância.

def _avaliar_runas(
    paginas: PaginasDoDraft,
    static: CatalogoJogo,
    *,
    min_jogos: int = 100,
) -> list[Candidato]:
    """Compara alternativas com a runa mais escolhida em cada vaga."""
    dados = paginas.runas()
    if not dados:
        return []

    acumulado: dict[int, _AcumuladoRuna] = {}
    for enemy, stats, peso in dados:
        # Em cada matchup, usamos como referência a runa mais escolhida da vaga.
        por_vaga: dict[tuple[int, int], list[M.EstatisticaRuna]] = {}
        for rid, st in stats.items():
            vaga = static.vaga_da_runa(rid)
            if vaga is None or st.games < min_jogos:
                continue
            por_vaga.setdefault(vaga, []).append(st)

        for vaga, concorrentes in por_vaga.items():
            if len(concorrentes) < 2:
                continue
            referencia = max(concorrentes, key=lambda x: x.pr)
            for st in concorrentes:
                if st.rune_id == referencia.rune_id:
                    continue
                delta = st.wr - referencia.wr
                variancia = (variancia_wr(st.wr, st.games)
                             + variancia_wr(referencia.wr, referencia.games))
                dado = acumulado.setdefault(st.rune_id, _AcumuladoRuna())
                dado.observacoes.append(ObservacaoPareada(
                    delta, variancia, peso, st.games,
                    (enemy.name, delta, st.games),
                ))
                dado.referencias.add(referencia.rune_id)

    saida: list[Candidato] = []
    for rid, dado in acumulado.items():
        resultado = combinar_pareadas(dado.observacoes)
        if resultado is None:
            continue
        cand = Candidato(
            ids=(rid,), delta=resultado.delta, erro=resultado.erro,
            jogos=resultado.jogos, matchups=resultado.matchups,
            total_paginas=len(dados), detalhe=resultado.detalhe,
            referencia=min(dado.referencias, default=None),
        )
        saida.append(cand)
    saida.sort(key=lambda c: -c.z)
    return saida


avaliar_runas = _avaliar_runas


# A página mais usada é a base. Uma runa só muda quando outra opção da mesma vaga
# passa os cortes de evidência e amostra.

Z_MINIMO = 2.0
JOGOS_MINIMOS = 500


@dataclass
class Troca:
    saiu: int
    entrou: int
    delta: float
    erro: float
    jogos: int
    matchups: int
    detalhe: tuple[tuple[str, float, int], ...] = ()


def _montar_runas(
    pagina_base: M.RunePage,
    candidatos: list[Candidato],
    static: CatalogoJogo,
    *,
    z_minimo: float = Z_MINIMO,
    jogos_minimos: int = JOGOS_MINIMOS,
) -> tuple[M.RunePage, list[Troca]]:
    """Aplica à página base as trocas que passam pelos cortes."""
    por_vaga: dict[tuple, Candidato] = {}
    for cand in candidatos:
        rid = cand.ids[0]
        vaga = static.vaga_da_runa(rid)
        if vaga is None:
            continue
        if cand.z < z_minimo or cand.jogos < jogos_minimos:
            continue
        # Só a candidata mais forte de cada vaga pode entrar.
        atual = por_vaga.get(vaga)
        if atual is None or cand.z > atual.z:
            por_vaga[vaga] = cand

    trocas: list[Troca] = []

    def trocar(lista: list[int]) -> list[int]:
        saida = []
        for rid in lista:
            vaga = static.vaga_da_runa(rid)
            cand = por_vaga.get(vaga) if vaga else None
            if cand is not None and cand.ids[0] != rid:
                trocas.append(Troca(saiu=rid, entrou=cand.ids[0], delta=cand.delta,
                                    erro=cand.erro, jogos=cand.jogos,
                                    matchups=cand.matchups,
                                    detalhe=tuple(cand.detalhe)))
                saida.append(cand.ids[0])
            else:
                saida.append(rid)
        return saida

    nova = M.RunePage(
        primary=trocar(list(pagina_base.primary)),
        secondary=trocar(list(pagina_base.secondary)),
        mods=list(pagina_base.mods),
        wr=pagina_base.wr,
        games=pagina_base.games,
    )
    return nova, trocas


montar_runas = _montar_runas


def _montar_feiticos(
    build_base: M.Build,
    padrao: tuple[int, ...] | None,
    candidatos: list[Candidato],
    *,
    z_minimo: float = Z_MINIMO,
    jogos_minimos: int = JOGOS_MINIMOS,
) -> tuple[list[int], Candidato | None]:
    """Mantém o par padrão, a menos que um candidato passe pelos cortes."""
    if padrao is None:
        mais = max(build_base.spells, key=lambda s: s.games, default=None)
        padrao = tuple(sorted(mais.ids)) if mais else ()
    for cand in candidatos:
        if cand.z >= z_minimo and cand.jogos >= jogos_minimos:
            return list(cand.ids), cand
    return list(padrao), None


montar_feiticos = _montar_feiticos


def _sequencia_popular(
    build: M.Build,
    *,
    validos: set[int],
    item6: bool,
) -> tuple[tuple[str, int], ...]:
    """Monta a sequência popular do recorte, sem usar win rate de item."""
    slots = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")
    permitidos = validos or {
        row.item_id for slot in slots for row in build.tables.get(slot, ())
    }
    usados: set[int] = set()
    sequencia: list[tuple[str, int]] = []
    for slot in slots:
        for row in sorted(build.tables.get(slot, ()), key=lambda item: -item.pr):
            if row.item_id in permitidos and row.item_id not in usados:
                usados.add(row.item_id)
                sequencia.append((slot, row.item_id))
                break
    if item6:
        for row in sorted(build.tables.get("Item 5", ()), key=lambda item: -item.pr):
            if row.item_id in permitidos and row.item_id not in usados:
                sequencia.append(("Item 6", row.item_id))
                break
    return tuple(sequencia)


def _erro(codigo: str, resumo: str, base: T | None = None) -> Decisao[T]:
    return Decisao(
        EstadoDecisao.ERRO, base, base,
        falha=FalhaDecisao(codigo, resumo, traceback.format_exc()),
    )


def recomendar(entrada: EntradaRecomendacao) -> RecomendacaoDoDraft:
    """Calcula runas e feitiços; itens começam pela build popular do recorte."""
    if entrada.criterios.z_minimo < 0 or entrada.criterios.jogos_minimos < 0:
        raise ValueError("os critérios da recomendação não podem ser negativos")

    build = entrada.pagina_base
    paginas = entrada.paginas_do_draft
    static = entrada.dados_estaticos
    corte = entrada.criterios

    base_runa = pagina_mais_escolhida(build)
    if base_runa is None:
        runas = Decisao(
            EstadoDecisao.FALTA_DADOS, None, None,
            falha=FalhaDecisao("runa_base_ausente",
                               "a página base não trouxe Runas"),
        )
    elif paginas is None or not paginas.paginas:
        runas = Decisao(
            EstadoDecisao.FALTA_DADOS, base_runa, base_runa,
            falha=FalhaDecisao("matchups_indisponiveis",
                               "Runas mantidas pela página base; matchups indisponíveis"),
        )
    else:
        try:
            candidatas = _avaliar_runas(
                paginas, static, min_jogos=corte.jogos_minimos_runa)
            recomendada, trocas = _montar_runas(
                base_runa, candidatas, static,
                z_minimo=corte.z_minimo, jogos_minimos=corte.jogos_minimos,
            )
            estado = (EstadoDecisao.PERSONALIZADA if trocas
                      else EstadoDecisao.SEM_EVIDENCIA)
            runas = Decisao(estado, recomendada, base_runa, tuple(trocas))
        except Exception:  # noqa: BLE001 — falha isolada por decisão
            runas = _erro("erro_runas", "não foi possível calcular Runas",
                          base_runa)

    escolha_base = max(build.spells, key=lambda s: s.games, default=None)
    base_feiticos = (tuple(sorted(escolha_base.ids)) if escolha_base else None)
    if paginas is None or not paginas.paginas:
        feiticos = Decisao(
            EstadoDecisao.FALTA_DADOS, base_feiticos, base_feiticos,
            falha=FalhaDecisao("matchups_indisponiveis",
                               "Feitiços mantidos pela página base; matchups indisponíveis"),
        )
    else:
        try:
            base_matchups, candidatas = _avaliar_feiticos(paginas)
            recomendado, troca = _montar_feiticos(
                build, base_matchups, candidatas,
                z_minimo=corte.z_minimo, jogos_minimos=corte.jogos_minimos,
            )
            base_escolhida = base_matchups or base_feiticos
            estado = (EstadoDecisao.PERSONALIZADA if troca
                      else EstadoDecisao.SEM_EVIDENCIA)
            feiticos = Decisao(
                estado, tuple(recomendado) if recomendado else None, base_escolhida,
                (troca,) if troca else (),
            )
        except Exception:  # noqa: BLE001
            feiticos = _erro("erro_feiticos",
                             "não foi possível calcular Feitiços",
                             base_feiticos)

    build_popular = paginas.base if paginas and paginas.base else build
    lane = paginas.lane if paginas else ""
    popular = _sequencia_popular(
        build_popular,
        validos=static.itens_finais,
        item6=lane == "bottom",
    )
    if popular:
        sequencia = Decisao(
            EstadoDecisao.SEM_EVIDENCIA, popular, popular,
        )
    else:
        sequencia = Decisao(
            EstadoDecisao.FALTA_DADOS, None, None,
            falha=FalhaDecisao(
                "build_popular_ausente",
                "a página base não trouxe uma sequência popular completa",
            ),
        )

    return RecomendacaoDoDraft(
        runas=runas,
        feiticos=feiticos,
        sequencia=sequencia,
        recorte_pagina_base=entrada.recorte_pagina_base,
        recorte_matchups=entrada.recorte_matchups,
    )


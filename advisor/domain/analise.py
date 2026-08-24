"""Combina os matchups para encontrar itens favorecidos pela composição."""

from __future__ import annotations

from dataclasses import dataclass, field

from advisor.domain import estatistica
from advisor.domain import modelos as M
from advisor.domain.modelos import Champion, PaginasDoDraft

TAU = 3.0
MIN_JOGOS = 30
OVERLAP_DEFLATOR = 1.2


@dataclass
class Observacao:
    enemy: Champion
    wr: float
    games: int
    lift: float
    peso: float


@dataclass
class Score:
    item_id: int
    lift: float
    sd: float
    base_wr: float
    base_games: int
    jogos_comp: int
    obs: list[Observacao] = field(default_factory=list)
    efeito: float = 0.0
    tau2: float = 0.0

    @property
    def z(self) -> float:
        """Significância do efeito específico do item, não do lift bruto."""
        return self.efeito / self.sd if self.sd else 0.0


def analisar(
    paginas: PaginasDoDraft,
    *,
    validos: set[int] | None = None,
    slots: tuple[str, ...] = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5"),
) -> tuple[dict[str, list[Score]], list[Champion], float]:
    """Ordena itens por efeito e informa quais matchups contribuíram."""
    base_tables = paginas.base.tables if paginas.base else {}
    base_por_slot: dict[str, dict[int, M.ItemRow]] = {
        slot: {r.item_id: r for r in (base_tables.get(slot) or [])} for slot in slots
    }

    usados = [p.enemy for p in paginas.paginas
              if any(p.build.tables.get(s) for s in slots)]
    if not usados:
        return {}, [], 0.0

    relevancias = paginas.pesos

    # Compensa parcialmente partidas presentes em mais de uma página.
    deflator = OVERLAP_DEFLATOR

    # Efeitos brutos por matchup.
    cru: dict[str, dict[int, list[Observacao]]] = {slot: {} for slot in slots}
    referencia: dict[str, dict[int, M.ItemRow]] = {slot: {} for slot in slots}
    # O filtro também remove linhas agregadas sem item real.
    for slot in slots:
        for item_id, obs in paginas.linhas(slot, validos=validos).items():
            ref = base_por_slot[slot].get(item_id)
            if ref is None or ref.games < MIN_JOGOS:
                continue
            for o in obs:
                if o.row.games < MIN_JOGOS:
                    continue
                peso = 1.0 / ((
                    estatistica.variancia_win_rate(o.row.wr, o.row.games)
                    + estatistica.variancia_win_rate(ref.wr, ref.games)
                ) * deflator)
                cru[slot].setdefault(item_id, []).append(
                    Observacao(o.enemy, o.row.wr, o.row.games,
                               o.row.wr - ref.wr, peso)
                )
                referencia[slot][item_id] = ref

    # Centraliza cada página para remover o efeito geral do confronto.
    por_inimigo: dict[int, list[Observacao]] = {}
    for slot in slots:
        for obs_list in cru[slot].values():
            for o in obs_list:
                por_inimigo.setdefault(o.enemy.cid, []).append(o)

    media_inimigo: dict[int, float] = {}
    for cid, observacoes in por_inimigo.items():
        total = sum(o.games for o in observacoes)
        media_inimigo[cid] = (
            sum(o.lift * o.games for o in observacoes) / total if total else 0.0
        )

    for observacoes in por_inimigo.values():
        for o in observacoes:
            o.lift -= media_inimigo[o.enemy.cid]

    # Reescala pela relevância no draft, sem deixar popularidade definir o peso.
    if relevancias:
        alvo = {cid: relevancias.get(cid, 1.0) for cid in por_inimigo}
        soma_cotas = sum(alvo.values())
        peso_atual = {cid: sum(o.peso for o in obs) for cid, obs in por_inimigo.items()}
        total_peso = sum(peso_atual.values())
        for cid, observacoes in por_inimigo.items():
            if peso_atual[cid] <= 0:
                continue
            fator = (alvo[cid] / soma_cotas * total_peso) / peso_atual[cid]
            for o in observacoes:
                o.peso *= fator

    # Efeito geral da composição, usado na apresentação.
    peso_comp = {cid: sum(o.games for o in obs) for cid, obs in por_inimigo.items()}
    total_comp = sum(peso_comp.values())
    deslocamento = (
        sum(media_inimigo[c] * peso_comp[c] for c in media_inimigo) / total_comp
        if total_comp else 0.0
    )

    # Combina os efeitos centralizados.
    saida: dict[str, list[Score]] = {}
    for slot in slots:
        finais: list[Score] = []
        for item_id, observacoes in cru[slot].items():
            ref = referencia[slot][item_id]
            score = Score(item_id=item_id, lift=0.0, sd=0.0, base_wr=ref.wr,
                          base_games=ref.games,
                          jogos_comp=sum(o.games for o in observacoes),
                          obs=observacoes)

            pesos = [o.peso for o in observacoes]
            lifts = [o.lift for o in observacoes]
            combinado = estatistica.combinar_efeitos_aleatorios(
                lifts,
                [1.0 / peso for peso in pesos],
                prior_sd=TAU,
            )
            score.tau2 = combinado.tau2
            score.lift = combinado.efeito
            score.sd = combinado.erro
            score.efeito = score.lift
            finais.append(score)
        saida[slot] = finais

    for scores in saida.values():
        scores.sort(key=lambda s: -s.efeito)

    return saida, usados, deslocamento


def corrigir_fdr(scores: list["Score"], alpha: float = 0.05) -> list["Score"]:
    """Aplica Benjamini-Hochberg aos efeitos avaliados."""
    p_valores = [estatistica.p_valor_bilateral(score.z) for score in scores]
    resultado = estatistica.corrigir_fdr(p_valores, alpha=alpha)
    return [
        score
        for score, rejeitada in zip(scores, resultado.rejeitadas)
        if rejeitada
    ]


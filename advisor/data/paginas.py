"""Busca uma vez as páginas do draft e resolve rotas e pesos."""

from __future__ import annotations

from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

from advisor.data import lolalytics as L
from advisor.data.ddragon import Champion, Static
from advisor.domain import draft as draft_mod
from advisor.domain.draft import Draft

# As tabelas do site separam botas dos cinco slots de item.
SLOTS_ITEM = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")


@dataclass
class Linha:
    """Item observado em um matchup, com seu peso."""

    enemy: Champion
    row: L.ItemRow
    peso: float


@dataclass
class Pagina:
    enemy: Champion
    build: L.Build
    peso: float


@dataclass
class PaginasDoDraft:
    """Páginas de matchup com rotas e pesos resolvidos."""

    paginas: list[Pagina] = field(default_factory=list)
    ausentes: list[Champion] = field(default_factory=list)
    rotas: dict[int, str] = field(default_factory=dict)
    counters: dict[int, L.Matchup] = field(default_factory=dict)
    relevancias: dict[int, tuple[float, list[str]]] = field(default_factory=dict)
    base: L.Build | None = None
    janela: str = "30"
    lane: str = ""
    tier: str = ""
    opponent: Champion | None = None
    opponent_inferido: bool = False

    @property
    def usados(self) -> list[Champion]:
        """Inimigos cuja página foi baixada."""
        return [p.enemy for p in self.paginas]

    @property
    def pesos(self) -> dict[int, float]:
        """Retorna os pesos sem os motivos da decisão."""
        return {cid: peso for cid, (peso, _) in self.relevancias.items()}

    def peso(self, cid: int) -> float:
        return self.relevancias.get(cid, (1.0, []))[0]

    def peso_total(self, *slots: str) -> float:
        """Soma os pesos das páginas que têm algum dos slots."""
        alvo = slots or SLOTS_ITEM
        return sum(p.peso for p in self.paginas
                   if any(p.build.tables.get(s) for s in alvo))

    def linhas(self, slot: str, *,
               validos: set[int] | None = None) -> dict[int, list[Linha]]:
        """Agrupa as linhas do slot por item e aplica o filtro opcional."""
        fora: dict[int, list[Linha]] = {}
        for pagina in self.paginas:
            for row in pagina.build.tables.get(slot) or []:
                if validos is not None and row.item_id not in validos:
                    continue
                fora.setdefault(row.item_id, []).append(
                    Linha(pagina.enemy, row, pagina.peso))
        return fora

    def feiticos(self) -> list[tuple[Champion, list[L.SpellChoice], float]]:
        """Pares de feitiço de cada página que os traz."""
        return [(p.enemy, p.build.spells, p.peso)
                for p in self.paginas if p.build.spells]

    def runas(self) -> list[tuple[Champion, dict[int, L.RuneStat], float]]:
        """Retorna as estatísticas de runa disponíveis por matchup."""
        return [(p.enemy, p.build.rune_stats, p.peso)
                for p in self.paginas if p.build.rune_stats]

    def paginas_de_runa(self) -> list[tuple[Champion, L.RunePage]]:
        """A página de runa mais escolhida em cada matchup."""
        return [(p.enemy, p.build.rune_pages[0])
                for p in self.paginas if p.build.rune_pages]


def _inferir_oponente(draft: Draft,
                      rotas: dict[int, str]) -> tuple[Champion | None, bool]:
    """Infere o oponente apenas quando há um único candidato na rota."""
    if draft.opponent is not None:
        return draft.opponent, False
    if not draft.lane:
        return None, False
    candidatos = [e for e in draft.enemies if rotas.get(e.cid) == draft.lane]
    if len(candidatos) == 1:
        return candidatos[0], True
    return None, False


def _rota_do_inimigo(lane: str | None, opponent: Champion | None,
                     rotas: dict[int, str], enemy: Champion) -> str | None:
    """Retorna a rota do inimigo usada em ``vslane``."""
    if opponent is not None and enemy.cid == opponent.cid:
        return lane or None
    return rotas.get(enemy.cid) or None


def carregar(
    draft: Draft,
    static: Static,
    *,
    tier: str,
    patch: str = "30",
    pesos: dict[str, float],
    fonte=L,
) -> PaginasDoDraft:
    """Busca as páginas e resolve o contexto necessário para combiná-las."""
    lane = draft.lane or None

    if draft.rotas_confirmadas:
        # Rotas confirmadas pelo cliente vencem qualquer inferência.
        counters = {}
        rotas = dict(draft.rotas_inimigas)
    else:
        # No champ select, counters dão uma inferência parcial das rotas.
        try:
            counters = fonte.get_counters(draft.champion.slug)
        except Exception:  # noqa: BLE001
            counters = {}
        rotas = {cid: m.lane for cid, m in counters.items() if m.lane}

    # Pesos e URLs dependem do oponente direto.
    opponent, inferido = _inferir_oponente(draft, rotas)

    relevancias = draft_mod.relevancia(
        draft.enemies, minha_rota=draft.lane or "",
        opponent=opponent, rotas=rotas, pesos=pesos,
    )

    fora = PaginasDoDraft(
        rotas=rotas, counters=counters, relevancias=relevancias,
        janela=patch, lane=draft.lane or "", tier=tier,
        opponent=opponent, opponent_inferido=inferido,
    )

    # Base e matchups precisam usar o mesmo recorte.
    try:
        fora.base = fonte.get_build(draft.champion.slug, lane=lane,
                                    tier=tier, patch=patch)
    except Exception:  # noqa: BLE001
        fora.base = None

    def buscar(enemy):
        try:
            vs = fonte.get_build(
                draft.champion.slug, versus=enemy.slug, lane=lane,
                vs_lane=_rota_do_inimigo(draft.lane, opponent, rotas, enemy),
                tier=tier, patch=patch,
            )
        except Exception:  # noqa: BLE001
            return enemy, None
        return enemy, vs

    # ``map`` paraleliza as buscas e preserva a ordem do draft.
    with ThreadPoolExecutor(max_workers=max(1, len(draft.enemies))) as executor:
        resultados = list(executor.map(buscar, draft.enemies))
    for enemy, vs in resultados:
        if vs is None:
            fora.ausentes.append(enemy)
        else:
            fora.paginas.append(Pagina(enemy, vs, fora.peso(enemy.cid)))

    return fora


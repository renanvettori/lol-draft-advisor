"""Modelos neutros usados pelo domínio, independentes das fontes externas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Champion:
    cid: int
    key: str
    name: str
    slug: str


@dataclass(frozen=True)
class Item:
    item_id: int
    wr: float
    pr: float
    games: int
    minute: int


@dataclass(frozen=True)
class PaginaRunas:
    primary: list[int]
    secondary: list[int]
    mods: list[int]
    wr: float
    games: int


@dataclass(frozen=True)
class Feiticos:
    ids: list[int]
    wr: float
    games: int
    pr: float = 0.0


@dataclass(frozen=True)
class EstatisticaRuna:
    rune_id: int
    pr: float
    wr: float
    games: int


@dataclass(frozen=True)
class ConjuntoItens:
    items: list[int]
    wr: float
    games: int


@dataclass
class DadosDeBuild:
    """Escolhas e estatísticas de um campeão em determinado recorte."""

    origem: str = ""
    patch: str = ""
    cid: int = 0
    lane: str = ""
    wr: float = 0.0
    pr: float = 0.0
    games: int = 0
    tier: str = ""
    rank: int = 0
    rank_total: int = 0
    skill_priority: str = ""
    skill_order: list[str] = field(default_factory=list)
    rune_pages: list[PaginaRunas] = field(default_factory=list)
    spells: list[Feiticos] = field(default_factory=list)
    starting_items: ConjuntoItens | None = None
    starting_sets: list[ConjuntoItens] = field(default_factory=list)
    core_build: ConjuntoItens | None = None
    tables: dict[str, list[Item]] = field(default_factory=dict)
    rune_stats: dict[int, EstatisticaRuna] = field(default_factory=dict)
    cache_em: str | None = None
    cache_fallback: bool = False

    def pagina_mais_escolhida(self) -> PaginaRunas | None:
        """Encontra a página mais usada pela adesão das runas."""
        def adesao(pagina: PaginaRunas) -> float:
            stats = [self.rune_stats.get(rid) for rid in pagina.primary]
            stats_validos = [stat for stat in stats if stat is not None]
            return sum(stat.pr for stat in stats_validos) / len(stats_validos) if stats_validos else 0.0

        return max(self.rune_pages, key=adesao, default=None)


def pagina_mais_escolhida(build: DadosDeBuild) -> PaginaRunas | None:
    """Encontra a página mais usada pela adesão das runas."""
    return build.pagina_mais_escolhida()


@dataclass(frozen=True)
class Confronto:
    cid: int
    vs_wr: float
    delta: float
    games: int
    lane: str


@dataclass(frozen=True)
class Linha:
    enemy: Champion
    row: Item
    peso: float


@dataclass(frozen=True)
class PaginaMatchup:
    enemy: Champion
    build: DadosDeBuild
    peso: float


SLOTS_ITEM = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")


@dataclass
class PaginasDoDraft:
    paginas: list[PaginaMatchup] = field(default_factory=list)
    ausentes: list[Champion] = field(default_factory=list)
    rotas: dict[int, str] = field(default_factory=dict)
    counters: dict[int, Confronto] = field(default_factory=dict)
    relevancias: dict[int, tuple[float, list[str]]] = field(default_factory=dict)
    base: DadosDeBuild | None = None
    janela: str = "30"
    lane: str = ""
    tier: str = ""
    opponent: Champion | None = None
    opponent_inferido: bool = False

    @property
    def usados(self) -> list[Champion]:
        return [p.enemy for p in self.paginas]

    @property
    def pesos(self) -> dict[int, float]:
        return {cid: peso for cid, (peso, _) in self.relevancias.items()}

    def peso(self, cid: int) -> float:
        return self.relevancias.get(cid, (1.0, []))[0]

    def peso_total(self, *slots: str) -> float:
        alvo = slots or SLOTS_ITEM
        return sum(p.peso for p in self.paginas
                   if any(p.build.tables.get(s) for s in alvo))

    def linhas(self, slot: str, *,
               validos: set[int] | None = None) -> dict[int, list[Linha]]:
        fora: dict[int, list[Linha]] = {}
        for pagina in self.paginas:
            for row in pagina.build.tables.get(slot) or []:
                if validos is not None and row.item_id not in validos:
                    continue
                fora.setdefault(row.item_id, []).append(
                    Linha(pagina.enemy, row, pagina.peso))
        return fora

    def feiticos(self) -> list[tuple[Champion, list[Feiticos], float]]:
        return [(p.enemy, p.build.spells, p.peso)
                for p in self.paginas if p.build.spells]

    def runas(self) -> list[tuple[Champion, dict[int, EstatisticaRuna], float]]:
        return [(p.enemy, p.build.rune_stats, p.peso)
                for p in self.paginas if p.build.rune_stats]

    def paginas_de_runa(self) -> list[tuple[Champion, PaginaRunas]]:
        return [(p.enemy, p.build.rune_pages[0])
                for p in self.paginas if p.build.rune_pages]


class CatalogoJogo(Protocol):
    itens_finais: set[int]

    def champion(self, ref: int | str) -> Champion | None: ...
    def item(self, iid: int) -> str: ...
    def rune(self, rid: int) -> str: ...
    def style(self, sid: int) -> str: ...
    def spell(self, sid: int) -> str: ...
    def info_campeao(self, key: str) -> dict: ...
    def estilo_da_runa(self, rid: int) -> int | None: ...
    def vaga_da_runa(self, rid: int) -> tuple[int, int] | None: ...
    def item_icon(self, iid: int) -> str: ...
    def rune_icon(self, rid: int) -> str: ...
    def spell_icon(self, sid: int) -> str: ...
    def champion_icon(self, key: str) -> str: ...
    def champion_splash(self, key: str) -> str: ...


# Aliases neutros preservam o vocabulário das fórmulas durante a migração.
ItemRow = Item
RunePage = PaginaRunas
SpellChoice = Feiticos
RuneStat = EstatisticaRuna
ItemSet = ConjuntoItens
Build = DadosDeBuild


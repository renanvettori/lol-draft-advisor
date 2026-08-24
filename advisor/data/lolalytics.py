"""Busca, cacheia e interpreta páginas do Lolalytics."""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

from advisor.data import qwik
from advisor.data.cache import pasta

BASE = "https://lolalytics.com"
CACHE_DIR = pasta("pages")
CACHE_TTL = 12 * 3600
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

SKILL_LETTERS = {1: "Q", 2: "W", 3: "E", 4: "R"}


class LolalyticsError(RuntimeError):
    pass


@dataclass
class ItemRow:
    item_id: int
    wr: float
    pr: float
    games: int
    minute: int


@dataclass
class RunePage:
    primary: list[int]
    secondary: list[int]
    mods: list[int]
    wr: float
    games: int


@dataclass
class SpellChoice:
    ids: list[int]
    wr: float
    games: int
    pr: float = 0.0


@dataclass
class RuneStat:
    """Estatísticas de uma runa individual."""

    rune_id: int
    pr: float
    wr: float
    games: int


@dataclass
class ItemSet:
    items: list[int]
    wr: float
    games: int


@dataclass
class Build:
    """Dados estruturados de uma página de build."""

    url: str
    patch: str = ""
    cid: int = 0
    lane: str = ""
    wr: float = 0.0
    pr: float = 0.0
    games: int = 0
    tier: str = ""
    rank: int = 0
    rank_total: int = 0
    strong_against: list[int] = field(default_factory=list)
    weak_against: list[int] = field(default_factory=list)
    skill_priority: str = ""
    skill_order: list[str] = field(default_factory=list)
    rune_pages: list[RunePage] = field(default_factory=list)
    spells: list[SpellChoice] = field(default_factory=list)
    starting_items: ItemSet | None = None
    starting_sets: list[ItemSet] = field(default_factory=list)
    core_build: ItemSet | None = None
    tables: dict[str, list[ItemRow]] = field(default_factory=dict)
    rune_stats: dict[int, RuneStat] = field(default_factory=dict)
    cache_em: str | None = None
    cache_fallback: bool = False


def build_url(
    champion: str,
    versus: str | None = None,
    lane: str | None = None,
    vs_lane: str | None = None,
    tier: str | None = None,
    patch: str | None = None,
    keystone: int | None = None,
) -> str:
    path = f"/lol/{champion}/vs/{versus}/build/" if versus else f"/lol/{champion}/build/"
    # O filtro keystone expõe a amostra da runa principal.
    params = {
        key: val
        for key, val in (
            ("lane", lane), ("vslane", vs_lane), ("tier", tier), ("patch", patch),
            ("keystone", keystone),
        )
        if val
    }
    return BASE + path + (f"?{urlencode(params)}" if params else "")


def fetch(url: str, *, ttl: int = CACHE_TTL, session: requests.Session | None = None) -> str:
    """Baixa a página, servindo do cache em disco quando ainda estiver fresca."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
        return path.read_text(encoding="utf-8", errors="replace")

    getter = session.get if session else requests.get
    try:
        resp = getter(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code == 404:
            raise LolalyticsError(f"página não existe: {url}")
        resp.raise_for_status()
    except requests.RequestException:
        meta = path.with_suffix(".meta.json")
        if path.exists() and meta.exists():
            try:
                from advisor.data import ddragon
                salvo = json.loads(meta.read_text(encoding="utf-8"))
                if salvo.get("ddragon_version") == ddragon.load().version:
                    return path.read_text(encoding="utf-8", errors="replace")
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        raise
    path.write_text(resp.text, encoding="utf-8")
    try:
        from advisor.data import ddragon
        path.with_suffix(".meta.json").write_text(json.dumps({
            "ddragon_version": ddragon.load().version,
            "salvo_em": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
    except (OSError, requests.RequestException):
        pass
    return resp.text


def _unique(objects) -> list:
    """Remove objetos repetidos pelo pool do Qwik."""
    seen, out = set(), []
    for obj in objects:
        marker = json.dumps(obj, sort_keys=True, default=str)
        if marker not in seen:
            seen.add(marker)
            out.append(obj)
    return out


def _table_label(table: dict) -> str:
    kind, n = table.get("type"), table.get("n")
    if kind == "boots":
        return "Botas"
    if kind == "itemItem" and n:
        return f"Item {n}"
    title = table.get("title")
    parts = title.get("title", []) if isinstance(title, dict) else []
    words = [p for p in parts if isinstance(p, str)]
    return " ".join(words) or str(kind)


def _ler_runas(build: "Build", tabela: dict) -> None:
    """Lê estatísticas indexadas pelo id da runa, inclusive ids com sufixo."""
    for chave, entradas in tabela.items():
        match = re.match(r"(\d+)", str(chave))
        if not match or not isinstance(entradas, list):
            continue
        rune_id = int(match.group(1))
        total_n = pr = soma_wr = 0
        for entrada in entradas:
            if not isinstance(entrada, list) or len(entrada) < 3:
                continue
            pr += entrada[0]
            soma_wr += entrada[1] * entrada[2]
            total_n += entrada[2]
        if total_n <= 0:
            continue
        novo = RuneStat(rune_id, pr, soma_wr / total_n, total_n)
        atual = build.rune_stats.get(rune_id)
        if atual is None or novo.games > atual.games:
            build.rune_stats[rune_id] = novo


def parse(html: str, url: str = "") -> Build:
    payload = qwik.extract(html)
    build = Build(url=url)

    # Páginas de campeão e matchup têm assinaturas diferentes.
    roots = _unique(qwik.find_objects(payload, {"patch", "cid", "lane", "counters", "wr"}))
    if not roots:
        roots = _unique(qwik.find_objects(
            payload, {"patch", "cid", "lane", "wr", "n", "vs", "vsWinRate"}))
    if roots:
        root = roots[0]
        build.patch = root.get("patch", "")
        build.cid = root.get("cid", 0)
        build.lane = root.get("lane", "")
        build.wr = root.get("wr", 0.0)
        build.pr = root.get("pr", 0.0)
        build.games = root.get("n", 0)
        build.tier = root.get("tier", "")
        build.rank = root.get("rank", 0)
        build.rank_total = root.get("rankTotal", 0)
        counters = root.get("counters") or {}
        build.strong_against = counters.get("strong") or []
        build.weak_against = counters.get("weak") or []
    else:
        state = next(qwik.find_objects(payload, {"champName", "vsName", "cid", "patch"}), None)
        if state is None:
            raise LolalyticsError(
                "não achei nem o bloco de estatísticas nem o estado da página — "
                "o formato do lolalytics provavelmente mudou"
            )
        build.patch = state.get("patch", "")
        build.cid = state.get("cid", 0)
        build.lane = state.get("vsLane") or state.get("lane", "")

    # O container mestre reúne feitiços, itens e runas. Linhas de item usam
    # [id, win rate, pick rate, jogos, minuto].
    mestre = next(qwik.find_objects(
        payload, {"spells", "startSet", "boots", "item1", "popularItem"}), None)

    if mestre is not None:
        for linha in mestre.get("spells") or []:
            if not isinstance(linha, list) or len(linha) < 4:
                continue
            ids = [int(x) for x in str(linha[0]).split("_") if x.isdigit()]
            build.spells.append(
                SpellChoice(ids=ids, wr=linha[1], games=linha[3], pr=linha[2]))

        for linha in mestre.get("startSet") or []:
            if not isinstance(linha, list) or len(linha) < 4:
                continue
            itens = [int(x) for x in str(linha[0]).split("_") if x.isdigit()]
            build.starting_sets.append(
                ItemSet(items=itens, wr=linha[1], games=linha[3]))
        if build.starting_sets:
            build.starting_items = build.starting_sets[0]

        for chave, rotulo in (("boots", "Botas"), ("item1", "Item 1"),
                              ("item2", "Item 2"), ("item3", "Item 3"),
                              ("item4", "Item 4"), ("item5", "Item 5"),
                              ("popularItem", "Populares"),
                              ("winningItem", "Vencedores"),
                              ("item", "Todos")):
            linhas = mestre.get(chave) or []
            tabela = [
                ItemRow(int(r[0]), r[1], r[2], int(r[3]),
                        int(r[4]) if len(r) > 4 else 0)
                for r in linhas
                if isinstance(r, list) and len(r) >= 4
            ]
            if tabela:
                build.tables[rotulo] = tabela

        estatisticas = (mestre.get("runes") or {}).get("stats")
        if isinstance(estatisticas, dict):
            _ler_runas(build, estatisticas)

    for page in _unique(qwik.find_objects(payload, {"wr", "n", "page", "set"})):
        chosen = page.get("set") or {}
        build.rune_pages.append(
            RunePage(
                primary=chosen.get("pri") or [],
                secondary=chosen.get("sec") or [],
                mods=chosen.get("mod") or [],
                wr=page.get("wr", 0.0),
                games=page.get("n", 0),
            )
        )

    # Fallback parcial para payloads sem o container mestre.
    if mestre is None:
        for bloco in _unique(qwik.find_objects(payload, {"stats"})):
            tabela = bloco.get("stats")
            if isinstance(tabela, dict):
                _ler_runas(build, tabela)

        for spell in _unique(qwik.find_objects(payload, {"ids", "n", "wr"})):
            build.spells.append(
                SpellChoice(ids=spell.get("ids") or [],
                            wr=spell.get("wr", 0.0), games=spell.get("n", 0))
            )

    for entry in _unique(qwik.find_objects(payload, {"id", "n", "wr"})):
        ident = entry.get("id")
        if isinstance(ident, str) and set(ident) <= set("QWER") and not build.skill_priority:
            build.skill_priority = ident
        elif isinstance(ident, int) and len(str(ident)) >= 10 and not build.skill_order:
            build.skill_order = [SKILL_LETTERS.get(int(d), "?") for d in str(ident)]

    if mestre is None:
        for start in _unique(qwik.find_objects(
                payload, {"n", "wr", "set", "setUnique", "count"})):
            build.starting_items = ItemSet(
                items=start.get("set") or [], wr=start.get("wr", 0.0),
                games=start.get("n", 0)
            )
            break

        for table in _unique(qwik.find_objects(payload, {"data", "title", "type"})):
            rows = table.get("data")
            if not isinstance(rows, list):
                continue
            parsed = [
                ItemRow(r[0], r[1], r[2], r[3], r[4] if len(r) > 4 else 0)
                for r in rows
                if isinstance(r, list) and len(r) >= 4
            ]
            if parsed:
                build.tables[_table_label(table)] = parsed

    # O núcleo de três itens fica fora do container mestre.
    for core in _unique(qwik.find_objects(payload, {"set", "wr", "n"})):
        if set(core.keys()) == {"set", "wr", "n"} and isinstance(core["set"], list):
            build.core_build = ItemSet(
                items=core["set"], wr=core.get("wr", 0.0), games=core.get("n", 0)
            )
            break

    return build


def get_build(champion: str, **kwargs) -> Build:
    """Atalho: monta a URL, busca e interpreta."""
    ttl = kwargs.pop("ttl", CACHE_TTL)
    session = kwargs.pop("session", None)
    url = build_url(champion, **kwargs)
    corpo = fetch(url, ttl=ttl, session=session)
    build = parse(corpo, url)
    path = CACHE_DIR / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if path.exists() and time.time() - path.stat().st_mtime >= ttl:
        build.cache_fallback = True
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text(
                encoding="utf-8"))
            build.cache_em = meta.get("salvo_em")
        except (OSError, ValueError, json.JSONDecodeError):
            build.cache_em = datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc).isoformat()
    return build


@dataclass
class Matchup:
    cid: int
    vs_wr: float  # win rate do seu campeão nesse confronto
    delta: float  # quanto o confronto desvia do normal, em pontos percentuais
    games: int
    lane: str


def get_counters(champion: str, *, ttl: int = CACHE_TTL,
                 session: requests.Session | None = None) -> dict[int, Matchup]:
    """Retorna os confrontos publicados, indexados pelo id do oponente."""
    url = f"{BASE}/lol/{champion}/counters/"
    payload = qwik.extract(fetch(url, ttl=ttl, session=session))
    out: dict[int, Matchup] = {}
    for row in qwik.find_objects(payload, {"cid", "vsWr", "n", "d1", "d2", "allWr"}):
        cid = row["cid"]
        if cid not in out:
            out[cid] = Matchup(
                cid=cid, vs_wr=row["vsWr"], delta=row["d2"],
                games=row["n"], lane=row.get("defaultLane", ""),
            )
    return out


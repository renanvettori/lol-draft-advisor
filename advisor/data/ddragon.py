"""Carrega e cacheia os dados estáticos do Data Dragon."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
import requests

from advisor.data.cache import pasta
from advisor.domain.modelos import Champion

BASE = "https://ddragon.leagueoflegends.com"
CACHE_DIR = pasta("ddragon")
LANG = "pt_BR"

# Os fragmentos de atributo não existem no runesReforged.json.
STAT_MODS = {
    5001: "Vida por nível",
    5002: "Armadura",
    5003: "Resistência Mágica",
    5005: "Velocidade de Ataque",
    5007: "Aceleração de Habilidade",
    5008: "Força Adaptável",
    5010: "Velocidade de Movimento",
    5011: "Vida",
    5013: "Tenacidade",
}

STAT_MOD_ICONS = {
    5001: "StatModsHealthScalingIcon.png", 5002: "StatModsArmorIcon.png",
    5003: "StatModsMagicResIcon.png", 5005: "StatModsAttackSpeedIcon.png",
    5007: "StatModsCDRScalingIcon.png", 5008: "StatModsAdaptiveForceIcon.png",
    5010: "StatModsMovementSpeedIcon.png", 5011: "StatModsHealthPlusIcon.png",
    5013: "StatModsTenacityIcon.png",
}

# O único campeão cujo slug no lolalytics não é o id do Data Dragon.
SLUG_OVERRIDES = {"monkeyking": "wukong"}


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


@dataclass
class Static:
    version: str
    champions: dict[int, Champion] = field(default_factory=dict)
    items: dict[int, str] = field(default_factory=dict)
    runes: dict[int, str] = field(default_factory=dict)
    styles: dict[int, str] = field(default_factory=dict)
    rune_style: dict[int, int] = field(default_factory=dict)
    rune_slot: dict[int, tuple[int, int]] = field(default_factory=dict)
    spells: dict[int, str] = field(default_factory=dict)
    rune_icons: dict[int, str] = field(default_factory=dict)
    spell_icons: dict[int, str] = field(default_factory=dict)
    raw_champions: dict[str, dict] = field(default_factory=dict)  # tags e atributos
    itens_finais: set[int] = field(default_factory=set)  # exclui componentes

    def champion(self, ref: int | str) -> Champion | None:
        """Busca campeão por id numérico, slug ou nome (tolerante a acento/caixa)."""
        if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
            return self.champions.get(int(ref))
        wanted = _slugify(ref)
        for champ in self.champions.values():
            if wanted in (champ.slug, _slugify(champ.name), _slugify(champ.key)):
                return champ
        return None

    def item(self, iid: int) -> str:
        return self.items.get(iid, f"Item {iid}")

    def rune(self, rid: int) -> str:
        return self.runes.get(rid) or STAT_MODS.get(rid) or f"Runa {rid}"

    def style(self, sid: int) -> str:
        return self.styles.get(sid, f"Estilo {sid}")

    def spell(self, sid: int) -> str:
        return self.spells.get(sid, f"Feitiço {sid}")

    def info_campeao(self, key: str) -> dict:
        return self.raw_champions.get(key, {})

    def estilo_da_runa(self, rid: int) -> int | None:
        return self.rune_style.get(rid)

    def vaga_da_runa(self, rid: int) -> tuple[int, int] | None:
        return self.rune_slot.get(rid)

    def item_icon(self, iid: int) -> str:
        return f"{BASE}/cdn/{self.version}/img/item/{iid}.png"

    def rune_icon(self, rid: int) -> str:
        caminho = self.rune_icons.get(rid, "")
        if caminho:
            return f"{BASE}/cdn/img/{caminho}"
        fragmento = STAT_MOD_ICONS.get(rid)
        return (f"{BASE}/cdn/img/perk-images/StatMods/{fragmento}"
                if fragmento else "")

    def spell_icon(self, sid: int) -> str:
        arquivo = self.spell_icons.get(sid, "")
        return f"{BASE}/cdn/{self.version}/img/spell/{arquivo}" if arquivo else ""

    def champion_icon(self, key: str) -> str:
        return f"{BASE}/cdn/{self.version}/img/champion/{key}.png"

    def champion_splash(self, key: str) -> str:
        return f"{BASE}/cdn/img/champion/splash/{key}_0.jpg"


def _get_json(url: str, cache_name: str, version: str | None) -> dict:
    folder = CACHE_DIR / (version or "meta")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / cache_name
    # Arquivos de uma versão são imutáveis; só a lista de versões expira.
    fresco = (version is not None or
              (path.exists() and time.time() - path.stat().st_mtime < 43_200))
    if path.exists() and fresco:
        return json.loads(path.read_text(encoding="utf-8"))
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        raise
    path.write_text(resp.text, encoding="utf-8")
    return resp.json()


def load(version: str | None = None) -> Static:
    """Carrega (e cacheia) os dados estáticos da versão indicada, ou da mais recente."""
    if version is None:
        version = _get_json(f"{BASE}/api/versions.json", "versions.json", None)[0]

    static = Static(version=version)
    cdn = f"{BASE}/cdn/{version}/data/{LANG}"

    for entry in _get_json(f"{cdn}/champion.json", "champion.json", version)["data"].values():
        cid = int(entry["key"])
        key = entry["id"]
        slug = SLUG_OVERRIDES.get(_slugify(key), _slugify(key))
        static.champions[cid] = Champion(cid, key, entry["name"], slug)
        static.raw_champions[key] = entry

    for iid, entry in _get_json(f"{cdn}/item.json", "item.json", version)["data"].items():
        static.items[int(iid)] = entry["name"]
        # Combina preço e número de evoluções para separar itens de componentes.
        ouro = (entry.get("gold") or {}).get("total", 0)
        if ouro >= 1000 and len(entry.get("into") or []) <= 2:
            static.itens_finais.add(int(iid))

    for entry in _get_json(f"{cdn}/summoner.json", "summoner.json", version)["data"].values():
        sid = int(entry["key"])
        static.spells[sid] = entry["name"]
        static.spell_icons[sid] = entry.get("image", {}).get("full", "")

    for style in _get_json(f"{cdn}/runesReforged.json", "runes.json", version):
        static.styles[style["id"]] = style["name"]
        for indice, slot in enumerate(style["slots"]):
            for rune in slot["runes"]:
                static.runes[rune["id"]] = rune["name"]
                static.rune_icons[rune["id"]] = rune.get("icon", "")
                static.rune_style[rune["id"]] = style["id"]
                # Runas só competem com outras da mesma vaga.
                static.rune_slot[rune["id"]] = (style["id"], indice)

    return static


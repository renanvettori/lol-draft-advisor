"""Adapter que converte Lolalytics em modelos neutros do domínio."""

from __future__ import annotations

import hashlib
import json
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from advisor.data import lolalytics as L, paginas as P
from advisor.data.cache import pasta
from advisor.domain.comparacoes import comparar_estatisticas_runas
from advisor.domain.draft import Draft
from advisor.domain.modelos import (
    CatalogoJogo,
    Confronto,
    ConjuntoItens,
    DadosDeBuild,
    EstatisticaRuna,
    Feiticos,
    Item,
    PaginaMatchup,
    PaginaRunas,
    PaginasDoDraft,
    pagina_mais_escolhida,
)
from advisor.fluxos.fontes import (
    ColetaDoDraft,
    FalhaColeta,
    RecortesColeta,
)

CACHE_BUILD = pasta("builds")
SLOTS_COMPLETOS = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")


def converter_build(build: L.Build) -> DadosDeBuild:
    def conjunto(valor: L.ItemSet | None) -> ConjuntoItens | None:
        return (ConjuntoItens(list(valor.items), valor.wr, valor.games)
                if valor else None)

    return DadosDeBuild(
        origem=build.url, patch=build.patch, cid=build.cid, lane=build.lane,
        wr=build.wr, pr=build.pr, games=build.games, tier=build.tier,
        rank=build.rank, rank_total=build.rank_total,
        skill_priority=build.skill_priority, skill_order=list(build.skill_order),
        rune_pages=[PaginaRunas(list(p.primary), list(p.secondary), list(p.mods),
                                p.wr, p.games) for p in build.rune_pages],
        spells=[Feiticos(list(s.ids), s.wr, s.games, s.pr)
                for s in build.spells],
        starting_items=conjunto(build.starting_items),
        starting_sets=[conjunto(s) for s in build.starting_sets],
        core_build=conjunto(build.core_build),
        tables={slot: [Item(r.item_id, r.wr, r.pr, r.games, r.minute)
                       for r in rows]
                for slot, rows in build.tables.items()},
        rune_stats={rid: EstatisticaRuna(s.rune_id, s.pr, s.wr, s.games)
                    for rid, s in build.rune_stats.items()},
        cache_em=build.cache_em, cache_fallback=build.cache_fallback,
    )


def _completa(build: DadosDeBuild) -> bool:
    return bool(
        build.patch and build.games > 0
        and build.rune_pages and build.rune_stats and build.spells
        and build.starting_sets and build.starting_items and build.core_build
        and build.skill_priority and build.skill_order
        and all(build.tables.get(slot) for slot in SLOTS_COMPLETOS)
    )


def _chave(champion: str, lane: str | None, elo: str, janela: str) -> Path:
    identidade = json.dumps(
        [champion, lane or "", elo, janela], ensure_ascii=False,
        separators=(",", ":"))
    nome = hashlib.sha256(identidade.encode()).hexdigest() + ".json"
    return CACHE_BUILD / nome


def _salvar(build: DadosDeBuild, caminho: Path) -> None:
    CACHE_BUILD.mkdir(parents=True, exist_ok=True)
    corpo = {
        "salvo_em": datetime.now(timezone.utc).isoformat(),
        "build": asdict(build),
    }
    temporario = caminho.with_suffix(".tmp")
    temporario.write_text(json.dumps(corpo, ensure_ascii=False), encoding="utf-8")
    temporario.replace(caminho)


def _carregar(caminho: Path) -> DadosDeBuild | None:
    try:
        corpo = json.loads(caminho.read_text(encoding="utf-8"))
        d = corpo["build"]
        build = DadosDeBuild(
            origem=d["origem"], patch=d["patch"], cid=d["cid"], lane=d["lane"],
            wr=d["wr"], pr=d["pr"], games=d["games"], tier=d["tier"],
            rank=d["rank"], rank_total=d["rank_total"],
            skill_priority=d["skill_priority"], skill_order=d["skill_order"],
            rune_pages=[PaginaRunas(**p) for p in d["rune_pages"]],
            spells=[Feiticos(**s) for s in d["spells"]],
            starting_items=(ConjuntoItens(**d["starting_items"])
                            if d["starting_items"] else None),
            starting_sets=[ConjuntoItens(**s) for s in d["starting_sets"]],
            core_build=(ConjuntoItens(**d["core_build"])
                        if d["core_build"] else None),
            tables={slot: [Item(**r) for r in rows]
                    for slot, rows in d["tables"].items()},
            rune_stats={int(rid): EstatisticaRuna(**s)
                        for rid, s in d["rune_stats"].items()},
            cache_em=corpo["salvo_em"], cache_fallback=True,
        )
        return build if _completa(build) else None
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _converter_paginas(valor: P.PaginasDoDraft) -> PaginasDoDraft:
    return PaginasDoDraft(
        paginas=[PaginaMatchup(p.enemy, converter_build(p.build), p.peso)
                 for p in valor.paginas],
        ausentes=list(valor.ausentes), rotas=dict(valor.rotas),
        counters={cid: Confronto(m.cid, m.vs_wr, m.delta, m.games, m.lane)
                  for cid, m in valor.counters.items()},
        relevancias=dict(valor.relevancias),
        base=converter_build(valor.base) if valor.base else None,
        janela=valor.janela, lane=valor.lane, tier=valor.tier,
        opponent=valor.opponent, opponent_inferido=valor.opponent_inferido,
    )


class FonteLolalytics:
    """Fonte profunda: uma chamada materializa todo o snapshot disponível."""

    def coletar_paginas(
        self, draft: Draft, *, elo: str, janela: str,
        catalogo: CatalogoJogo, relevancia: dict[str, float],
    ) -> PaginasDoDraft:
        return _converter_paginas(P.carregar(
            draft, catalogo, tier=elo, patch=janela, pesos=relevancia))

    def coletar_draft(
        self,
        draft: Draft,
        recortes: RecortesColeta,
        catalogo: CatalogoJogo,
        relevancia: dict[str, float],
    ) -> ColetaDoDraft:
        falhas: list[FalhaColeta] = []
        lane = draft.lane or None
        caminho = _chave(
            draft.champion.slug, lane, recortes.pagina_base_elo,
            recortes.pagina_base_janela)
        patch_base = (None if recortes.pagina_base_janela == "patch_atual"
                      else recortes.pagina_base_janela)
        try:
            bruto = L.get_build(
                draft.champion.slug, lane=lane,
                tier=recortes.pagina_base_elo, patch=patch_base)
            pagina_base = converter_build(bruto)
        except Exception:  # noqa: BLE001 — tenta último dado completo
            pagina_base = _carregar(caminho)
            if pagina_base is None:
                raise
            salvo = datetime.fromisoformat(pagina_base.cache_em).astimezone()
            falhas.append(FalhaColeta(
                "pagina_base_cache",
                "fonte indisponível; usando build base armazenada em "
                f"{salvo:%d/%m/%Y %H:%M}, patch {pagina_base.patch}",
                traceback.format_exc()))
        else:
            if _completa(pagina_base):
                try:
                    _salvar(pagina_base, caminho)
                except OSError:
                    falhas.append(FalhaColeta(
                        "cache_pagina_base",
                        "não consegui atualizar o cache da página base",
                        traceback.format_exc()))

        paginas = None
        if draft.enemies:
            try:
                paginas = self.coletar_paginas(
                    draft, elo=recortes.matchups_elo,
                    janela=recortes.matchups_janela,
                    catalogo=catalogo, relevancia=relevancia)
                if paginas.ausentes:
                    falhas.append(FalhaColeta(
                        "matchups_parciais",
                        "algumas páginas de matchup não estavam disponíveis",
                        ", ".join(c.name for c in paginas.ausentes)))
            except Exception:  # noqa: BLE001
                falhas.append(FalhaColeta(
                    "matchups", "não consegui buscar as páginas de matchup",
                    traceback.format_exc()))

        referencia = None
        if recortes.referencia_elo != recortes.pagina_base_elo:
            try:
                ref = converter_build(L.get_build(
                    draft.champion.slug, lane=lane,
                    tier=recortes.referencia_elo, patch=patch_base))
                pagina_ref = pagina_mais_escolhida(ref)
                if pagina_ref:
                    referencia = (recortes.referencia_elo, pagina_ref)
            except Exception:  # noqa: BLE001
                falhas.append(FalhaColeta(
                    "referencia_elo", "não consegui consultar o elo de referência",
                    traceback.format_exc()))

        estatisticas = ()
        try:
            candidatas = sorted({
                pg.primary[0] for pg in pagina_base.rune_pages if pg.primary
            } | {8008, 8005, 8021, 9923, 8010, 8112, 8214, 8229, 8437, 8351})
            crus = {}
            for keystone in candidatas:
                try:
                    dado = L.get_build(
                        draft.champion.slug, lane=lane,
                        tier=recortes.pagina_base_elo, keystone=keystone)
                    if dado.games > 0:
                        crus[keystone] = (dado.wr, dado.games)
                except Exception:  # noqa: BLE001 — candidato isolado
                    continue
            estatisticas = tuple(comparar_estatisticas_runas(crus))
        except Exception:  # noqa: BLE001
            falhas.append(FalhaColeta(
                "estatisticas_runa", "não consegui consultar estatísticas de runa",
                traceback.format_exc()))

        return ColetaDoDraft(
            pagina_base, paginas, referencia, estatisticas, tuple(falhas))


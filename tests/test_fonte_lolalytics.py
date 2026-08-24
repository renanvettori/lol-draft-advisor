from types import SimpleNamespace

import pytest

from advisor.data import fonte_lolalytics as fonte_mod
from advisor.data import lolalytics as L
from advisor.domain.draft import Draft
from advisor.domain.modelos import Champion
from advisor.fluxos.fontes import RecortesColeta


ASHE = Champion(22, "Ashe", "Ashe", "ashe")
RECORTES = RecortesColeta(
    "platinum", "patch_atual", "platinum", "30", "platinum")


def build_completa(patch="16.16"):
    pagina = L.RunePage([8008, 1, 2, 3], [4, 5], [5005, 5008, 5001], 51, 1000)
    conjunto = L.ItemSet([1055, 2003], 51, 1000)
    build = L.Build(
        url="https://fonte/base", patch=patch, cid=22, lane="bottom",
        games=1000, skill_priority="W > Q > E", skill_order=["W", "Q", "E"],
        rune_pages=[pagina], rune_stats={
            8008: L.RuneStat(8008, 60, 51, 1000)},
        spells=[L.SpellChoice([4, 7], 51, 1000, 60)],
        starting_items=conjunto, starting_sets=[conjunto], core_build=conjunto,
    )
    for slot in fonte_mod.SLOTS_COMPLETOS:
        build.tables[slot] = [L.ItemRow(3006, 51, 60, 1000, 10)]
    return build


def contexto_coleta(fonte):
    return fonte.coletar_draft(
        Draft(ASHE, "bottom"), RECORTES,
        SimpleNamespace(), {})


def test_fallback_usa_ultima_pagina_base_completa(monkeypatch, tmp_path):
    monkeypatch.setattr(fonte_mod, "CACHE_BUILD", tmp_path)
    monkeypatch.setattr(fonte_mod.L, "get_build", lambda *a, **k: build_completa())
    fonte = fonte_mod.FonteLolalytics()
    primeira = contexto_coleta(fonte)
    assert primeira.pagina_base.cache_fallback is False

    monkeypatch.setattr(fonte_mod.L, "get_build", lambda *a, **k: (_ for _ in ()).throw(
        OSError("site fora")))
    fallback = contexto_coleta(fonte)

    assert fallback.pagina_base.cache_fallback is True
    assert fallback.pagina_base.patch == "16.16"
    assert fallback.pagina_base.cache_em
    assert fallback.falhas[0].etapa == "pagina_base_cache"


def test_resposta_incompleta_nao_substitui_cache_valido(monkeypatch, tmp_path):
    monkeypatch.setattr(fonte_mod, "CACHE_BUILD", tmp_path)
    respostas = iter([build_completa("16.15"), L.Build(url="vazia", patch="16.16")])
    def responder(*args, **kwargs):
        return L.Build(url="runa") if kwargs.get("keystone") else next(respostas)
    monkeypatch.setattr(fonte_mod.L, "get_build", responder)
    fonte = fonte_mod.FonteLolalytics()
    contexto_coleta(fonte)
    contexto_coleta(fonte)  # utilizável agora, mas não pode sobrescrever o cache

    monkeypatch.setattr(fonte_mod.L, "get_build", lambda *a, **k: (_ for _ in ()).throw(
        OSError("site fora")))
    fallback = contexto_coleta(fonte)

    assert fallback.pagina_base.patch == "16.15"


def test_cache_nao_cruza_recortes(monkeypatch, tmp_path):
    monkeypatch.setattr(fonte_mod, "CACHE_BUILD", tmp_path)
    monkeypatch.setattr(fonte_mod.L, "get_build", lambda *a, **k: build_completa())
    contexto_coleta(fonte_mod.FonteLolalytics())

    monkeypatch.setattr(fonte_mod.L, "get_build", lambda *a, **k: (_ for _ in ()).throw(
        OSError("site fora")))
    outro = RecortesColeta("diamond", "patch_atual", "diamond", "30", "diamond")
    with pytest.raises(OSError):
        fonte_mod.FonteLolalytics().coletar_draft(
            Draft(ASHE, "bottom"), outro, SimpleNamespace(), {})


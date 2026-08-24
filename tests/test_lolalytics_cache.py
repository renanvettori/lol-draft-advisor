import hashlib
import json
from types import SimpleNamespace

import pytest
import requests

from advisor.data import ddragon
from advisor.data import lolalytics as L


class FonteFora:
    def get(self, *args, **kwargs):
        raise requests.ConnectionError("offline")


def _cache(tmp_path, url, versao):
    caminho = tmp_path / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    caminho.write_text("pagina armazenada", encoding="utf-8")
    caminho.with_suffix(".meta.json").write_text(json.dumps({
        "ddragon_version": versao,
        "salvo_em": "2026-08-16T12:00:00+00:00",
    }), encoding="utf-8")


def test_fonte_offline_aceita_cache_da_mesma_versao(tmp_path, monkeypatch):
    url = "https://lolalytics.com/lol/ashe/build/?tier=emerald_plus"
    monkeypatch.setattr(L, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ddragon, "load", lambda: SimpleNamespace(version="16.16.1"))
    _cache(tmp_path, url, "16.16.1")

    assert L.fetch(url, ttl=0, session=FonteFora()) == "pagina armazenada"


def test_fonte_offline_rejeita_cache_de_outro_patch(tmp_path, monkeypatch):
    url = "https://lolalytics.com/lol/ashe/build/?tier=emerald_plus"
    monkeypatch.setattr(L, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(ddragon, "load", lambda: SimpleNamespace(version="16.16.1"))
    _cache(tmp_path, url, "16.15.1")

    with pytest.raises(requests.ConnectionError):
        L.fetch(url, ttl=0, session=FonteFora())


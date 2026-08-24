"""Extrai e resolve o estado Qwik embutido nas páginas do Lolalytics."""

from __future__ import annotations

import json
import re
from typing import Any, Iterator

_SCRIPT_RE = re.compile(r'<script[^>]+type="qwik/json"[^>]*>(.*?)</script>', re.DOTALL)
_BASE36_RE = re.compile(r"^[0-9a-z]+$")


class QwikPayloadNotFound(RuntimeError):
    """A página não contém o payload Qwik esperado."""


def extract(html: str) -> dict:
    """Retorna o payload qwik/json cru (com as referências ainda por resolver)."""
    match = _SCRIPT_RE.search(html)
    if match is None:
        raise QwikPayloadNotFound(
            "nenhum <script type='qwik/json'> encontrado — o lolalytics pode ter "
            "trocado de framework, ou a resposta foi um bloqueio/captcha"
        )
    return json.loads(match.group(1))


class Resolver:
    """Resolve e memoiza referências base-36 do pool ``objs``."""

    def __init__(self, objs: list) -> None:
        self._objs = objs
        self._memo: dict[int, Any] = {}
        self._active: set[int] = set()

    def index(self, i: int) -> Any:
        """Resolve o valor no índice ``i`` do pool."""
        if i in self._memo:
            return self._memo[i]
        if i in self._active:
            return None  # O Qwik pode serializar referências circulares.
        self._active.add(i)
        try:
            value = self.value(self._objs[i])
        finally:
            self._active.discard(i)
        self._memo[i] = value
        return value

    def value(self, raw: Any) -> Any:
        """Resolve um valor arbitrário, seguindo referências recursivamente."""
        if isinstance(raw, str):
            return self._string(raw)
        if isinstance(raw, list):
            return [self.value(item) for item in raw]
        if isinstance(raw, dict):
            return {key: self.value(val) for key, val in raw.items()}
        return raw

    def _string(self, s: str) -> Any:
        if not s:
            return ""
        if ord(s[0]) < 0x20:
            return s[1:]
        if _BASE36_RE.match(s):
            i = int(s, 36)
            if 0 <= i < len(self._objs):
                return self.index(i)
        return s


def find_objects(payload: dict, required_keys: set[str]) -> Iterator[dict]:
    """Localiza objetos pela assinatura de chaves, não pelo índice instável."""
    objs = payload["objs"]
    resolver = Resolver(objs)
    for i, raw in enumerate(objs):
        if isinstance(raw, dict) and required_keys <= raw.keys():
            resolved = resolver.index(i)
            if isinstance(resolved, dict):
                yield resolved


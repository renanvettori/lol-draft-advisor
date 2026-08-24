"""Localização e migração do cache fora do repositório."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def raiz() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "LoLDraftAdvisor" / "cache"


def pasta(nome: str) -> Path:
    return raiz() / nome


def migrar_legado() -> bool:
    """Move o cache antigo uma única vez, preservando arquivos já migrados."""
    antigo = Path.home() / ".lol-draft-advisor"
    if not antigo.is_dir():
        return False
    destino = raiz()
    destino.mkdir(parents=True, exist_ok=True)
    moveu = False
    for origem in antigo.iterdir():
        alvo = destino / origem.name
        if not alvo.exists():
            shutil.move(str(origem), str(alvo))
            moveu = True
    try:
        antigo.rmdir()
    except OSError:
        pass
    return moveu


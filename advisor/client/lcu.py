"""Lê o champ select pela API local do League Client."""

from __future__ import annotations

import base64
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import requests
import urllib3

from advisor.data.ddragon import Static
from advisor.domain.draft import Draft

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# O servidor local usa certificado autoassinado.
VERIFY_TLS = False

LOCKFILE_PATHS = [
    Path(r"C:\Riot Games\League of Legends\lockfile"),
    Path(r"C:\Program Files\Riot Games\League of Legends\lockfile"),
    Path(r"C:\Program Files (x86)\Riot Games\League of Legends\lockfile"),
    Path(r"D:\Riot Games\League of Legends\lockfile"),
]

# Nomenclatura do client -> nomenclatura do lolalytics.
POSITIONS = {
    "top": "top",
    "jungle": "jungle",
    "middle": "middle",
    "bottom": "bottom",
    "utility": "support",
}


class LCUError(RuntimeError):
    pass


@dataclass
class Credentials:
    port: int
    token: str

    @property
    def header(self) -> str:
        raw = f"riot:{self.token}".encode()
        return "Basic " + base64.b64encode(raw).decode()


def _from_lockfile() -> Credentials | None:
    for path in LOCKFILE_PATHS:
        try:
            parts = path.read_text(encoding="utf-8").strip().split(":")
        except OSError:
            continue
        if len(parts) >= 4:
            return Credentials(port=int(parts[2]), token=parts[3])
    return None


def _from_process() -> Credentials | None:
    """Lê porta e token do processo quando o lockfile não é encontrado."""
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "(Get-CimInstance Win32_Process -Filter \"Name='LeagueClientUx.exe'\")"
             ".CommandLine"],
            capture_output=True, text=True, timeout=20,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None

    port = token = None
    for chunk in out.split("--"):
        if chunk.startswith("app-port="):
            port = chunk.split("=", 1)[1].strip().strip('"')
        elif chunk.startswith("remoting-auth-token="):
            token = chunk.split("=", 1)[1].strip().strip('"')
    if port and token:
        return Credentials(port=int(port), token=token)
    return None


def find_credentials() -> Credentials:
    creds = _from_lockfile() or _from_process()
    if creds is None:
        raise LCUError(
            "não achei as credenciais do client — ele está aberto? "
            "(procurei o lockfile nos caminhos padrão e a linha de comando do "
            "LeagueClientUx)"
        )
    return creds


class LCU:
    """Cliente HTTP mínimo para a API local do League."""

    def __init__(self, creds: Credentials | None = None) -> None:
        self.creds = creds or find_credentials()
        self.session = requests.Session()
        self.session.headers["Authorization"] = self.creds.header
        self.session.verify = VERIFY_TLS

    def _request(self, method: str, path: str, payload=None):
        url = f"https://127.0.0.1:{self.creds.port}{path}"
        try:
            resp = self.session.request(method, url, json=payload, timeout=10)
        except requests.RequestException as exc:
            raise LCUError(f"falha ao falar com o client: {exc}") from exc
        if resp.status_code == 404:
            return None
        if resp.status_code == 401:
            raise LCUError("credenciais recusadas — o client foi reiniciado? "
                           "as credenciais mudam a cada execução")
        if not resp.ok:
            raise LCUError(f"{method} {path} devolveu {resp.status_code}: "
                           f"{resp.text[:300]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except ValueError:
            return resp.text

    def get(self, path: str):
        return self._request("GET", path)

    # Chamadas de escrita são usadas apenas pelo módulo perks.
    def post(self, path: str, payload):
        return self._request("POST", path, payload)

    def put(self, path: str, payload):
        return self._request("PUT", path, payload)

    def delete(self, path: str):
        return self._request("DELETE", path)

    def phase(self) -> str:
        """Fase atual: None, Lobby, Matchmaking, ReadyCheck, ChampSelect, InProgress…"""
        return self.get("/lol-gameflow/v1/gameflow-phase") or "None"

    def champ_select(self) -> dict | None:
        """Sessão de champ select, ou None se não estiver em seleção."""
        return self.get("/lol-champ-select/v1/session")


# Rank do client -> faixa de elo do lolalytics.
TIERS = {
    "IRON": "iron", "BRONZE": "bronze", "SILVER": "silver", "GOLD": "gold",
    "PLATINUM": "platinum", "EMERALD": "emerald", "DIAMOND": "diamond",
    "MASTER": "diamond_plus", "GRANDMASTER": "diamond_plus",
    "CHALLENGER": "diamond_plus",
}


def ranked_tier(api: LCU, queue: str = "RANKED_SOLO_5x5") -> tuple[str, str] | None:
    """Retorna o elo no formato do Lolalytics e um rótulo legível."""
    stats = api.get("/lol-ranked/v1/current-ranked-stats") or {}
    entry = (stats.get("queueMap") or {}).get(queue) or {}
    tier = (entry.get("tier") or "").upper()
    slug = TIERS.get(tier)
    if not slug:
        return None
    return slug, f"{tier.capitalize()} {entry.get('division', '')}".strip()


def _picked(entry: dict) -> int:
    """Campeão travado, ou o que está sendo passado o mouse (intent)."""
    return entry.get("championId") or entry.get("championPickIntent") or 0


def read_draft(session: dict, static: Static) -> Draft | None:
    """Converte a sessão em ``Draft`` após o jogador escolher um campeão."""
    my_cell = session.get("localPlayerCellId")
    my_team = session.get("myTeam") or []
    their_team = session.get("theirTeam") or []

    mine = next((e for e in my_team if e.get("cellId") == my_cell), None)
    if mine is None:
        return None
    champ = static.champion(_picked(mine))
    if champ is None:
        return None

    lane = POSITIONS.get((mine.get("assignedPosition") or "").lower(), "")

    def collect(team: list[dict]) -> list:
        out = []
        for entry in team:
            if entry.get("cellId") == my_cell:
                continue
            found = static.champion(_picked(entry))
            if found is not None:
                out.append(found)
        return out

    allies = collect(my_team)
    enemies = collect(their_team)

    # O time inimigo também aparece nas ações de pick; em algumas filas o
    # theirTeam demora a refletir os picks travados.
    known = {c.cid for c in enemies}
    for group in session.get("actions") or []:
        for action in group:
            if action.get("isAllyAction") or action.get("type") != "pick":
                continue
            found = static.champion(action.get("championId") or 0)
            if found is not None and found.cid not in known:
                known.add(found.cid)
                enemies.append(found)

    # Oponente direto: só quando o client informa a posição do inimigo, o que
    # não acontece em todas as filas. Sem isso, não vale chutar.
    opponent = None
    if lane:
        for entry in their_team:
            if POSITIONS.get((entry.get("assignedPosition") or "").lower(), "") == lane:
                opponent = static.champion(_picked(entry))
                break

    return Draft(champion=champ, lane=lane, enemies=enemies,
                 allies=allies, opponent=opponent)


def current_draft(static: Static, lcu: LCU | None = None) -> Draft | None:
    """Atalho: conecta, confere a fase e devolve o draft atual (ou None)."""
    lcu = lcu or LCU()
    session = lcu.champ_select()
    return read_draft(session, static) if session else None


def dump_session(path: str = "session.json") -> None:
    """Salva a sessão atual em disco — útil para depurar sem estar em partida."""
    session = LCU().champ_select()
    Path(path).write_text(json.dumps(session, indent=2), encoding="utf-8")


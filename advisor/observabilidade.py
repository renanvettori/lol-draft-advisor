"""Logs técnicos e histórico final; nenhum cálculo de recomendação vive aqui."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from advisor.domain.draft import Draft
from advisor.domain.recomendador import RecomendacaoDoDraft
from advisor.domain.adaptacao import ResultadoAdaptacao

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGGER = logging.getLogger("lol-draft-advisor")


@dataclass(frozen=True)
class ExecucaoRecomendacao:
    recomendacao: RecomendacaoDoDraft
    aplicacao: dict[str, str]
    adaptacao_elo_alto: ResultadoAdaptacao | None = None


def configurar() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if LOGGER.handlers:
        return
    handler = logging.FileHandler(LOG_DIR / "advisor.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"))
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)


def registrar_falhas(recomendacao: RecomendacaoDoDraft) -> None:
    for categoria, decisao in (
        ("runas", recomendacao.runas),
        ("feiticos", recomendacao.feiticos),
        ("sequencia", recomendacao.sequencia),
    ):
        if decisao.falha and decisao.falha.detalhe_tecnico:
            LOGGER.error("falha em %s: %s\n%s", categoria,
                         decisao.falha.resumo, decisao.falha.detalhe_tecnico)


def registrar_falhas_tecnicas(falhas) -> None:
    """Registra objetos de falha estruturada sem acoplar este módulo à origem."""
    for falha in falhas:
        LOGGER.error("%s: %s\n%s", falha.etapa, falha.resumo,
                     falha.detalhe_tecnico)


def registrar_final(execucao: ExecucaoRecomendacao, draft: Draft) -> str:
    """Registra somente o snapshot que efetivamente virou uma partida."""
    identificador = str(uuid4())
    registro = {
        "id": identificador,
        "registrado_em": datetime.now(timezone.utc).isoformat(),
        "draft": {
            "campeao": asdict(draft.champion),
            "rota": draft.lane,
            "inimigos": [asdict(c) for c in draft.enemies],
            "oponente_de_rota": (asdict(draft.opponent)
                                  if draft.opponent else None),
            "rotas_inimigas": draft.rotas_inimigas,
            "rotas_confirmadas": draft.rotas_confirmadas,
        },
        "recomendacao": asdict(execucao.recomendacao),
        "adaptacao_elo_alto": (asdict(execucao.adaptacao_elo_alto)
                                if execucao.adaptacao_elo_alto else None),
        "aplicacao": execucao.aplicacao,
    }
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    with (LOG_DIR / "recomendacoes.jsonl").open("a", encoding="utf-8") as arq:
        arq.write(json.dumps(registro, ensure_ascii=False) + "\n")
    LOGGER.info("recomendação final registrada: %s", identificador)
    return identificador


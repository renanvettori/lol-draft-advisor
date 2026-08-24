"""Roda os vinte drafts exploratórios pelo motor integrado."""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path

from advisor import config
from advisor.data import ddragon
from advisor.data.fonte_lolalytics import FonteLolalytics
from advisor.domain import adaptacao as A
from scripts.explorar_transferencias import (
    CENARIOS, CENARIOS_ANTERIORES, _coletar, _draft,
)

RAIZ = Path(__file__).resolve().parents[1]


def main():
    cfg = config.carregar()
    static = ddragon.load()
    fonte = FonteLolalytics()
    criterios = A.CriteriosAdaptacao(
        cfg.adaptacao_z_principal, cfg.adaptacao_z_alternativa,
        cfg.adaptacao_corrigir_multiplos_itens, cfg.adaptacao_fdr_botas,
        cfg.adaptacao_deflator_sobreposicao, cfg.adaptacao_max_alternativas)
    registros = []
    inicio_total = time.perf_counter()
    for nome, dados in CENARIOS_ANTERIORES + CENARIOS:
        inicio = time.perf_counter()
        draft = _draft(static, dados)
        paginas, elo, excluidos, criticos, tentativas = _coletar(
            draft, fonte, static, cfg)
        resultado = A.calcular(
            paginas, elo=elo, criterios=criterios,
            validos=static.itens_finais, elos_tentados=(elo,),
            lane=draft.lane)
        duracao = time.perf_counter() - inicio
        ids = [iid for _, iid in resultado.sequencia]
        falhas = []
        if len(ids) != 7:
            falhas.append(f"inventário com {len(ids)} entradas")
        if len(ids) != len(set(ids)):
            falhas.append("item duplicado")
        if {3033, 3036} <= set(ids):
            falhas.append("Dominik e Lembrete juntos")
        final_por_slot = dict(resultado.sequencia)
        for acao in resultado.acoes:
            if final_por_slot.get(acao.slot_destino) != acao.item_id:
                falhas.append(f"ação desfeita: {acao.item_id}")
            if len(acao.evidencias) != 5:
                falhas.append(
                    f"ação {acao.item_id} tem {len(acao.evidencias)} contribuições")
        resumo = ", ".join(
            f"{static.item(a.item_id)}->{a.slot_destino}"
            for a in resultado.acoes) or "build base"
        print(nome, resultado.estado, f"[{resumo}]",
              f"{duracao:.2f}s", tuple(falhas), flush=True)
        registros.append({
            "cenario": nome,
            "inimigos": [c.name for c in draft.enemies],
            "duracao_segundos": duracao,
            "tentativas": tentativas,
            "resultado": asdict(resultado),
            "falhas": falhas,
        })
    total = time.perf_counter() - inicio_total
    caminho = RAIZ / "relatorios" / "validacao-motor-principal.json"
    caminho.write_text(json.dumps({
        "duracao_total_segundos": total,
        "cenarios": registros,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print("TOTAL", f"{total:.2f}s", caminho)
    if any(r["falhas"] for r in registros):
        raise SystemExit("a validação encontrou invariantes quebradas")


if __name__ == "__main__":
    main()


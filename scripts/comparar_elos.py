"""Compara a estabilidade do motor experimental em recortes de elo."""

from __future__ import annotations

import json
from pathlib import Path

from advisor import config
from advisor.data import ddragon
from advisor.data.fonte_lolalytics import FonteLolalytics
from advisor.domain import transferencias as T
from scripts.explorar_transferencias import (
    CENARIOS_ANTERIORES as CENARIOS, _draft, _otimizar_sequencia, _percentual,
)

ELOS_COMPARADOS = (
    "master_plus", "diamond_plus", "emerald_plus", "platinum_plus")


def main():
    cfg = config.carregar()
    static = ddragon.load()
    fonte = FonteLolalytics()
    registros = []
    for elo in ELOS_COMPARADOS:
        print("\nELO", elo, flush=True)
        totais = {"atual": 0, "completa_165": 0, "completa_150": 0}
        for nome, dados in CENARIOS:
            draft = _draft(static, dados)
            paginas = fonte.coletar_paginas(
                draft, elo=elo, janela=cfg.adaptacao_janela_dias,
                catalogo=static, relevancia=cfg.relevancia)
            validas = [p for p in paginas.paginas
                       if p.build.games >= cfg.adaptacao_jogos_por_matchup_minimos]
            paginas.paginas = validas
            jogos = sum(p.build.games for p in validas)
            if len(validas) < 3:
                print(" ", nome, "cobertura insuficiente", len(validas), jogos)
                registros.append({"elo": elo, "cenario": nome,
                                  "cobertura": len(validas), "jogos": jogos,
                                  "status": "cobertura insuficiente"})
                continue
            resultado = T.analisar(
                paginas, elo=elo,
                criterios=T.Criterios(
                    cfg.z_minimo, cfg.adaptacao_fdr_botas,
                    cfg.adaptacao_deflator_sobreposicao),
                validos=static.itens_finais, total_inimigos=5,
                lane=draft.lane)
            relaxado = T.analisar(
                paginas, elo=elo,
                criterios=T.Criterios(
                    1.65, 1.0, cfg.adaptacao_deflator_sobreposicao),
                validos=static.itens_finais, total_inimigos=5,
                lane=draft.lane)
            opt165 = _otimizar_sequencia(relaxado, 1.65)
            opt150 = _otimizar_sequencia(relaxado, 1.50)
            tem_atual = bool(resultado.modificacoes)
            tem165 = tem_atual or opt165 is not None
            tem150 = tem_atual or opt150 is not None
            totais["atual"] += tem_atual
            totais["completa_165"] += tem165
            totais["completa_150"] += tem150
            def item(opt):
                return static.item(opt[4]) if opt else None
            print(" ", nome, f"{len(validas)}/5", f"jogos={jogos}",
                  "atual=" + (str(len(resultado.modificacoes)) if tem_atual else "-"),
                  "seq1.65=" + (item(opt165) or "-"),
                  "seq1.50=" + (item(opt150) or "-"))
            registros.append({
                "elo": elo, "cenario": nome, "cobertura": len(validas),
                "jogos": jogos, "atual": len(resultado.modificacoes),
                "sequencia_165": item(opt165), "sequencia_150": item(opt150),
                "limite_165": (_percentual(opt165[0]) if opt165 else None),
                "limite_150": (_percentual(opt150[0]) if opt150 else None),
            })
        print(" TOTAL", totais)
    caminho = Path(__file__).resolve().parents[1] / "relatorios" / "comparacao-elos.json"
    caminho.write_text(json.dumps(registros, ensure_ascii=False, indent=2),
                       encoding="utf-8")
    print("\n", caminho)


if __name__ == "__main__":
    main()


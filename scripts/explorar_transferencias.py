"""Executa dez composições mistas e gera uma análise exploratória isolada."""

from __future__ import annotations

import html
import json
import math
from dataclasses import asdict
from pathlib import Path

from advisor import config
from advisor.data import ddragon
from advisor.data.fonte_lolalytics import FonteLolalytics
from advisor.domain import transferencias as T
from advisor.domain.draft import Draft

RAIZ = Path(__file__).resolve().parents[1]

CENARIOS_ANTERIORES = (
    ("Dive com alcance", (("Camille", "top"), ("Vi", "jungle"),
                          ("Ahri", "middle"), ("KaiSa", "bottom"),
                          ("Rakan", "support"))),
    ("Front line leve", (("Gnar", "top"), ("Viego", "jungle"),
                         ("Viktor", "middle"), ("Jhin", "bottom"),
                         ("Nami", "support"))),
    ("Pressão lateral", (("Renekton", "top"), ("Sejuani", "jungle"),
                         ("Akali", "middle"), ("Ezreal", "bottom"),
                         ("Karma", "support"))),
    ("Pick e cerco", (("Fiora", "top"), ("JarvanIV", "jungle"),
                      ("Syndra", "middle"), ("Caitlyn", "bottom"),
                      ("Thresh", "support"))),
    ("Teamfight clássico", (("Kennen", "top"), ("LeeSin", "jungle"),
                            ("Orianna", "middle"), ("Jinx", "bottom"),
                            ("Braum", "support"))),
    ("Escala híbrida", (("KSante", "top"), ("Kindred", "jungle"),
                        ("Leblanc", "middle"), ("Smolder", "bottom"),
                        ("Milio", "support"))),
    ("Engage e poke", (("Gragas", "top"), ("Nocturne", "jungle"),
                       ("Hwei", "middle"), ("Varus", "bottom"),
                       ("Nautilus", "support"))),
    ("Curto alcance", (("Gwen", "top"), ("XinZhao", "jungle"),
                       ("Yasuo", "middle"), ("Xayah", "bottom"),
                       ("Lulu", "support"))),
    ("Ameaças divididas", (("Jax", "top"), ("Lillia", "jungle"),
                           ("Zed", "middle"), ("MissFortune", "bottom"),
                           ("Leona", "support"))),
    ("Controle e mobilidade", (("Aatrox", "top"), ("Graves", "jungle"),
                               ("Anivia", "middle"), ("Lucian", "bottom"),
                               ("Bard", "support"))),
)

CENARIOS = (
    ("Proteção e execução", (("Shen", "top"), ("Khazix", "jungle"),
                             ("Azir", "middle"), ("Aphelios", "bottom"),
                             ("Renata", "support"))),
    ("Entrada em duas frentes", (("Rumble", "top"), ("MonkeyKing", "jungle"),
                                 ("Sylas", "middle"), ("Zeri", "bottom"),
                                 ("Alistar", "support"))),
    ("Controle móvel", (("Poppy", "top"), ("Ekko", "jungle"),
                        ("Corki", "middle"), ("Kalista", "bottom"),
                        ("Neeko", "support"))),
    ("Sustain e zoneamento", (("Olaf", "top"), ("Ivern", "jungle"),
                              ("Cassiopeia", "middle"), ("Tristana", "bottom"),
                              ("Rell", "support"))),
    ("Pressão explosiva", (("Aurora", "top"), ("Belveth", "jungle"),
                           ("TwistedFate", "middle"), ("Samira", "bottom"),
                           ("Maokai", "support"))),
    ("Flanco e disengage", (("Urgot", "top"), ("Elise", "jungle"),
                            ("Yone", "middle"), ("Sivir", "bottom"),
                            ("Janna", "support"))),
    ("Alcance desigual", (("Kled", "top"), ("Taliyah", "jungle"),
                          ("Veigar", "middle"), ("KogMaw", "bottom"),
                          ("Blitzcrank", "support"))),
    ("Pressão de alvo único", (("Mordekaiser", "top"), ("Nidalee", "jungle"),
                               ("Jayce", "middle"), ("Vayne", "bottom"),
                               ("Sona", "support"))),
    ("Pick e aceleração", (("Chogath", "top"), ("Kayn", "jungle"),
                           ("Zoe", "middle"), ("Draven", "bottom"),
                           ("Milio", "support"))),
    ("Rotação e iniciação", (("Quinn", "top"), ("Amumu", "jungle"),
                             ("Kassadin", "middle"), ("Twitch", "bottom"),
                             ("Seraphine", "support"))),
)


def _draft(static, dados) -> Draft:
    ashe = static.champion("Ashe")
    pares = [(static.champion(nome), rota) for nome, rota in dados]
    if ashe is None or any(c is None for c, _ in pares):
        faltantes = [nome for (nome, _), (c, _) in zip(dados, pares) if c is None]
        raise RuntimeError(f"campeões não encontrados: {faltantes}")
    enemies = [c for c, _ in pares]
    rotas = {c.cid: rota for c, rota in pares}
    opponent = next(c for c, rota in pares if rota == "bottom")
    return Draft(champion=ashe, lane="bottom", enemies=enemies,
                 opponent=opponent, rotas_inimigas=rotas,
                 rotas_confirmadas=True)


def _coletar(draft, fonte, static, cfg):
    melhor = None
    tentativas = []
    for elo in cfg.adaptacao_elos:
        paginas = fonte.coletar_paginas(
            draft, elo=elo, janela=cfg.adaptacao_janela_dias,
            catalogo=static, relevancia=cfg.relevancia)
        validas = [p for p in paginas.paginas
                   if p.build.games >= cfg.adaptacao_jogos_por_matchup_minimos]
        nomes_validos = {p.enemy.cid for p in validas}
        excluidos = tuple(c.name for c in draft.enemies
                          if c.cid not in nomes_validos)
        paginas.paginas = validas
        paginas.ausentes = [c for c in draft.enemies if c.cid not in nomes_validos]
        jogos = sum(p.build.games for p in validas)
        tentativas.append({"elo": elo, "cobertura": len(validas),
                           "jogos": jogos, "excluidos": excluidos})
        candidato = (len(validas), jogos, paginas, excluidos, elo)
        if melhor is None or candidato[:2] > melhor[:2]:
            melhor = candidato
        if (len(validas) >= 3
                and jogos >= cfg.adaptacao_jogos_totais_minimos):
            melhor = candidato
            break
    assert melhor is not None
    _, _, paginas, excluidos, elo = melhor
    criticos = tuple(
        nome for nome in excluidos
        if next((paginas.peso(c.cid) for c in draft.enemies if c.name == nome), 1.0)
        > cfg.relevancia["outra_rota"])
    return paginas, elo, excluidos, criticos, tentativas


def _nome(static, iid):
    return static.item(iid)


def _sequencia(static, seq):
    return " → ".join(_nome(static, iid) for _, iid in seq) or "indisponível"


def _percentual(delta):
    return (math.exp(delta) - 1) * 100


def _otimizar_sequencia(resultado: T.Resultado, z_minimo: float = 1.65):
    """Compatibilidade de saída para os relatórios exploratórios antigos."""
    plano = T.otimizar_sequencias(
        resultado, z_principal=z_minimo,
        z_alternativa=z_minimo, max_alternativas=0)
    otimizada = plano.principal
    if otimizada is None:
        return None
    primeira = otimizada.acoes[0]
    return (otimizada.limite_inferior, otimizada.efeito, otimizada.z,
            primeira.slot_destino, primeira.candidato, primeira.removido,
            otimizada.sequencia)


def _motivo(static, mod):
    candidato = _nome(static, mod.candidato)
    ocupante = _nome(static, mod.ocupante)
    removido = _nome(static, mod.removido) if mod.removido else None
    if mod.tipo in {"antecipacao", "adiamento"}:
        return (f"{candidato} passou de {mod.slot_origem} para {mod.slot_destino}; "
                "a presença total permaneceu estável.")
    if mod.slot_destino == "Botas":
        return f"{candidato} ganhou preferência de {ocupante}."
    if removido:
        return f"Presença de {removido} foi transferida para {candidato}."
    if mod.tipo == "ambigua":
        return f"{candidato} ganhou espaço de {ocupante}, mas a cascata não fechou: {mod.motivo}."
    return f"{candidato} ganhou espaço de {ocupante}: {mod.motivo}."


def _gerar_html(resultados, static, caminho: Path):
    cards = []
    for registro in resultados:
        r = registro["resultado"]
        otimizada = registro.get("otimizada")
        if otimizada:
            limite, efeito, z, destino, candidato, removido, sequencia = otimizada
            bloco_otimizado = (
                f'<div class="optimized"><label>Sequência completa · z ≥ 1,65</label>'
                f'<p>{html.escape(_sequencia(static, sequencia))}</p>'
                f'<small>Entra <b>{html.escape(_nome(static, candidato))}</b> em '
                f'{html.escape(destino)} · '
                f'{("sai " + html.escape(_nome(static, removido))) if removido else "muda de posição"} · '
                f'efeito conjunto {_percentual(efeito):+.1f}% · '
                f'limite conservador {_percentual(limite):+.1f}% · z {z:.2f}</small></div>')
        else:
            bloco_otimizado = (
                '<div class="optimized muted"><label>Sequência completa · z ≥ 1,65</label>'
                '<p>Build base mantida.</p></div>')
        mods = ''.join(
            f'<li><b>{html.escape(_nome(static, m.candidato))}</b> — {html.escape(m.tipo)} em '
            f'{html.escape(m.slot_destino)} <strong>{_percentual(m.efeito):+.1f}%</strong>'
            f'<small>bruto {_percentual(m.efeito_bruto):+.1f}% · '
            f'limite posterior {_percentual(m.limite_inferior):+.1f}% · '
            f'contração {m.contracao * 100:.0f}% · {html.escape(_motivo(static, m))}</small></li>'
            for m in r.modificacoes) or '<li class="muted">Nenhuma modificação aplicada.</li>'
        alternativas = ''.join(
            f'<li><b>{html.escape(_nome(static, m.candidato))}</b> — '
            f'{_percentual(m.efeito):+.1f}% <small>{html.escape(_motivo(static, m))}</small></li>'
            for m in r.alternativas[:3]) or '<li class="muted">Nenhuma alternativa bloqueada.</li>'
        alerta = (f'<p class="alert">Cobertura crítica ausente: {html.escape(", ".join(r.cobertura_critica))}</p>'
                  if r.cobertura_critica else '')
        inv = (f'<p class="error">Invariantes: {html.escape(", ".join(r.invariantes))}</p>'
               if r.invariantes else '')
        cards.append(f'''<section><header><div><span>{html.escape(registro["nome"])}</span>
        <h2>Ashe vs {html.escape(", ".join(registro["inimigos"]))}</h2></div>
        <code>{html.escape(r.elo)} · cobertura {r.cobertura}/{r.total_inimigos}</code></header>
        {alerta}{inv}<div class="build"><label>Build base</label><p>{html.escape(_sequencia(static, r.sequencia_base))}</p>
        <label>Resultado exploratório</label><p>{html.escape(_sequencia(static, r.sequencia))}</p>
        {('<small>Item 6 estimado usando a distribuição do Item 5; erro ampliado em 1,5×.</small>' if r.item6_proxy else '')}</div>
        {bloco_otimizado}
        <div class="cols"><div><h3>Modificações</h3><ul>{mods}</ul></div>
        <div><h3>Alternativas observadas</h3><ul>{alternativas}</ul></div></div></section>''')
    documento = f'''<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width"><title>Análise exploratória</title><style>
    :root{{--bg:#071521;--panel:#0d2637;--line:#315065;--gold:#d2ad5c;--text:#e8dcc1;--muted:#91aab8;--cyan:#62cad7}}
    *{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 Segoe UI,Arial}}
    main{{width:min(1200px,calc(100% - 36px));margin:auto;padding:36px 0}}h1{{font:42px Georgia;margin:0}}.intro{{color:var(--muted);max-width:850px}}
    section{{margin:24px 0;border:1px solid var(--line);background:var(--panel);padding:20px}}header{{display:flex;justify-content:space-between;gap:20px}}header span,label{{color:var(--gold);font:11px Consolas;text-transform:uppercase;letter-spacing:.12em}}h2{{margin:4px 0;font:24px Georgia}}code{{color:var(--cyan)}}
    .build{{margin:16px 0;padding:14px;border-left:3px solid var(--gold);background:#091d2b}}.build p{{margin:4px 0 12px}}.optimized{{margin:16px 0;padding:14px;border:1px solid var(--line);background:#0a1f2d}}.optimized p{{margin:5px 0}}.optimized b{{color:var(--cyan)}}
    .cols{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}.cols>div{{border-top:1px solid var(--line)}}h3{{font:18px Georgia}}ul{{padding-left:20px}}li{{margin:10px 0}}li strong{{color:var(--cyan)}}small{{display:block;color:var(--muted)}}.muted{{color:var(--muted)}}.alert{{color:#efbc72}}.error{{color:#ff8181}}
    @media(max-width:760px){{.cols{{grid-template-columns:1fr}}header{{display:block}}}}
    </style></head><body><main><span>Análise isolada · não integrada ao advisor</span><h1>Transferências de escolha</h1>
    <p class="intro">Dez drafts mistos, deltas agregados antes dos cortes, referência compartilhada e FDR por slot. O relatório de partida permanece inalterado.</p>
    {''.join(cards)}</main></body></html>'''
    caminho.write_text(documento, encoding="utf-8")


def main():
    cfg = config.carregar()
    static = ddragon.load()
    fonte = FonteLolalytics()
    resultados = []
    for nome, dados in CENARIOS:
        print("coletando", nome, flush=True)
        draft = _draft(static, dados)
        paginas, elo, excluidos, criticos, tentativas = _coletar(
            draft, fonte, static, cfg)
        resultado = T.analisar(
            paginas, elo=elo,
            criterios=T.Criterios(
                cfg.z_minimo, cfg.adaptacao_fdr_botas,
                cfg.adaptacao_deflator_sobreposicao),
            validos=static.itens_finais, total_inimigos=len(draft.enemies),
            excluidos=excluidos, cobertura_critica=criticos, lane=draft.lane)
        resultado_variado = T.analisar(
            paginas, elo=elo,
            criterios=T.Criterios(
                cfg.adaptacao_z_alternativa, 1.0,
                cfg.adaptacao_deflator_sobreposicao),
            validos=static.itens_finais, total_inimigos=len(draft.enemies),
            excluidos=excluidos, cobertura_critica=criticos, lane=draft.lane)
        otimizada = _otimizar_sequencia(resultado_variado)
        resultados.append({
            "nome": nome, "inimigos": [c.name for c in draft.enemies],
            "tentativas": tentativas, "resultado": resultado,
            "otimizada": otimizada})
        print(" ", elo, resultado.cobertura, "mods", len(resultado.modificacoes),
              "alts", len(resultado.alternativas), "inv", resultado.invariantes)
        for mod in resultado.modificacoes:
            print("   ", mod.tipo, static.item(mod.ocupante), "->",
                  static.item(mod.candidato), mod.slot_destino,
                  f"efeito={_percentual(mod.efeito):+.1f}%",
                  f"limite={_percentual(mod.limite_inferior):+.1f}%")
        for mod in resultado.alternativas[:3]:
            print("    alternativa", mod.tipo, static.item(mod.candidato),
                  mod.slot_destino, f"efeito={_percentual(mod.efeito):+.1f}%",
                  _motivo(static, mod))
        quase = sorted(
            (h for h in resultado.hipoteses
             if h.tipo == "slot" and h.efeito_posterior > 0
             and h.p_posterior < 1 and not h.passou_fdr),
            key=lambda h: h.p_posterior,
        )
        for h in quase[:5]:
            print("    quase", h.slot, static.item(h.ocupante), "->",
                  static.item(h.candidato),
                  f"efeito={_percentual(h.efeito_posterior):+.1f}%",
                  f"z={h.z_posterior:.2f}", f"p={h.p_posterior:.4f}")
        if resultado_variado.modificacoes or resultado_variado.alternativas:
            print("    modo ilustrativo sem FDR:")
            for mod in resultado_variado.modificacoes:
                print("     ", mod.tipo, static.item(mod.ocupante), "->",
                      static.item(mod.candidato), mod.slot_destino,
                      f"efeito={_percentual(mod.efeito):+.1f}%",
                      f"limite={_percentual(mod.limite_inferior):+.1f}%")
            for mod in resultado_variado.alternativas[:5]:
                print("      bloqueada", static.item(mod.ocupante), "->",
                      static.item(mod.candidato), mod.slot_destino,
                      f"efeito={_percentual(mod.efeito):+.1f}%", mod.motivo)
        if otimizada:
            limite, efeito, z, destino, candidato, removido, sequencia = otimizada
            print("    sequência completa:",
                  f"entra {static.item(candidato)} em {destino};",
                  (f"sai {static.item(removido)};" if removido else
                   "apenas muda a ordem;"),
                  f"efeito conjunto={_percentual(efeito):+.1f}%",
                  f"limite={_percentual(limite):+.1f}%", f"z={z:.2f}")
            print("     ", " -> ".join(
                _nome(static, iid) for _, iid in sequencia))
        otimizada_sensivel = _otimizar_sequencia(resultado_variado, 1.50)
        if otimizada_sensivel and otimizada_sensivel != otimizada:
            limite, efeito, z, destino, candidato, removido, sequencia = otimizada_sensivel
            print("    sequência sensível (z>=1,50):",
                  f"entra {static.item(candidato)} em {destino};",
                  (f"sai {static.item(removido)};" if removido else
                   "apenas muda a ordem;"),
                  f"efeito conjunto={_percentual(efeito):+.1f}%",
                  f"limite={_percentual(limite):+.1f}%", f"z={z:.2f}")
            print("     ", " -> ".join(
                _nome(static, iid) for _, iid in sequencia))

    pasta = RAIZ / "relatorios"
    pasta.mkdir(exist_ok=True)
    json_path = pasta / "analise-comps-mistas-2.json"
    json_path.write_text(json.dumps([
        {**{k: v for k, v in r.items() if k != "resultado"},
         "resultado": r["resultado"].json()} for r in resultados
    ], ensure_ascii=False, indent=2), encoding="utf-8")
    html_path = pasta / "analise-comps-mistas-2.html"
    _gerar_html(resultados, static, html_path)
    print(html_path)
    print(json_path)


if __name__ == "__main__":
    main()


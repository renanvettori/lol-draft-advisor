"""Gera um painel HTML local para inspecionar a validação dos vinte drafts."""

from __future__ import annotations

import html
import json
import math
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from advisor.data import ddragon
from scripts.explorar_transferencias import CENARIOS, CENARIOS_ANTERIORES


ENTRADA = RAIZ / "relatorios" / "validacao-motor-principal.json"
SAIDA = RAIZ / "relatorios" / "painel-validacao-motor.html"
ROTAS = {"top": "Topo", "jungle": "Selva", "middle": "Meio",
         "bottom": "Atirador", "support": "Suporte"}


def esc(valor) -> str:
    return html.escape(str(valor))


def percentual_log(valor: float) -> float:
    return (math.exp(valor) - 1) * 100


def item(static, iid: int, slot: str, *, alterado: bool = False) -> str:
    classe = "item alterado" if alterado else "item"
    return f'''<div class="{classe}" title="{esc(static.item(iid))}">
      <span class="slot">{esc(slot.replace("Item ", ""))}</span>
      <img src="{esc(static.item_icon(iid))}" alt="{esc(static.item(iid))}" loading="lazy">
      <strong>{esc(static.item(iid))}</strong>
    </div>'''


def trilho(static, sequencia, alterados=()) -> str:
    alterados = set(alterados)
    return '<div class="build-rail">' + "".join(
        item(static, iid, slot, alterado=slot in alterados)
        for slot, iid in sequencia
    ) + "</div>"


def composicao(static, dados) -> str:
    cards = []
    for nome, rota in dados:
        champ = static.champion(nome)
        if champ is None:
            continue
        cards.append(f'''<div class="champ">
          <img src="{esc(static.champion_icon(champ.key))}" alt="{esc(champ.name)}" loading="lazy">
          <span><strong>{esc(champ.name)}</strong><small>{ROTAS.get(rota, rota)}</small></span>
        </div>''')
    return '<div class="enemy-line">' + "".join(cards) + "</div>"


def confianca(z: float) -> tuple[str, str]:
    if z >= 2.30:
        return "forte", "Sinal forte"
    if z >= 1.96:
        return "boa", "Sinal consistente"
    return "limiar", "Passou no corte"


def acao_html(static, acao: dict) -> str:
    iid = acao["item_id"]
    removido = acao.get("removido")
    z = float(acao.get("z", 0))
    classe, rotulo = confianca(z)
    evidencias = sorted(acao.get("evidencias", []),
                        key=lambda e: abs(e.get("contribuicao", 0)), reverse=True)
    maior = max((abs(e.get("contribuicao", 0)) for e in evidencias), default=1) or 1
    linhas = []
    for ev in evidencias:
        contrib = float(ev.get("contribuicao", 0))
        largura = max(3, abs(contrib) / maior * 100)
        direcao = "pos" if contrib >= 0 else "neg"
        linhas.append(f'''<div class="evidence-row">
          <span>{esc(ev["inimigo"])}</span>
          <div class="bar-track"><i class="{direcao}" style="width:{largura:.1f}%"></i></div>
          <code>{contrib:+.3f}</code>
        </div>''')
    troca = (f'Sai <b>{esc(static.item(removido))}</b>' if removido
             else "A ordem da build muda")
    limite = percentual_log(float(acao.get("limite_inferior", 0)))
    return f'''<article class="decision">
      <div class="decision-main">
        <img src="{esc(static.item_icon(iid))}" alt="" loading="lazy">
        <div><small>{esc(acao.get("tipo", "ajuste"))} · {esc(acao["slot_destino"])}</small>
          <h3>{esc(static.item(iid))}</h3><p>{troca}</p></div>
        <span class="confidence {classe}">{rotulo}<b>z {z:.2f}</b></span>
      </div>
      <details><summary>Ver contribuição dos cinco oponentes <span>limite {limite:+.1f}%</span></summary>
        <div class="evidence">{"".join(linhas)}</div>
      </details>
    </article>'''


def cenario_html(static, registro: dict, dados) -> str:
    resultado = registro["resultado"]
    acoes = resultado.get("acoes", [])
    adaptado = bool(acoes)
    alterados = [a["slot_destino"] for a in acoes]
    status = "adaptado" if adaptado else "base"
    decisoes = "".join(acao_html(static, a) for a in acoes)
    if not decisoes:
        decisoes = '''<div class="base-note"><span>∅</span><div><strong>Nenhum sinal venceu a build base</strong>
        <p>O motor avaliou as hipóteses, mas não encontrou uma troca suficientemente convincente.</p></div></div>'''
    falhas = registro.get("falhas", [])
    integridade = ("Falhas: " + ", ".join(falhas)) if falhas else "Inventário íntegro · 7 posições · sem conflitos"
    tent = registro.get("tentativas", [{}])[0]
    return f'''<section class="scenario" data-status="{status}">
      <header class="scenario-head">
        <div><span class="index">{registro["_indice"]:02d}</span>
          <div><small>Draft de teste</small><h2>{esc(registro["cenario"])}</h2></div></div>
        <span class="status {status}">{"Build adaptada" if adaptado else "Build base"}</span>
      </header>
      {composicao(static, dados)}
      <div class="builds">
        <div><label>Build base</label>{trilho(static, resultado["sequencia_base"])}</div>
        <div><label>Recomendação final</label>{trilho(static, resultado["sequencia"], alterados)}</div>
      </div>
      <div class="decisions">{decisoes}</div>
      <footer class="scenario-foot">
        <span>{esc(integridade)}</span><span>Emerald+ · {tent.get("jogos", 0):,} jogos · {registro["duracao_segundos"]:.2f}s</span>
      </footer>
    </section>'''.replace(",", ".")


def gerar() -> Path:
    dados = json.loads(ENTRADA.read_text(encoding="utf-8"))
    static = ddragon.load()
    cenarios_def = dict(CENARIOS_ANTERIORES + CENARIOS)
    registros = dados["cenarios"]
    adaptados = sum(bool(r["resultado"].get("acoes")) for r in registros)
    falhas = sum(bool(r.get("falhas")) for r in registros)
    secoes = []
    for indice, registro in enumerate(registros, 1):
        registro["_indice"] = indice
        secoes.append(cenario_html(static, registro, cenarios_def[registro["cenario"]]))

    documento = f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Validação do motor · Draft Advisor</title>
<style>
:root{{--ink:#06141d;--deep:#091f2b;--panel:#0c2836;--panel2:#102f3d;--line:#294956;--paper:#eee2c7;--muted:#91a9ae;--gold:#d8b45d;--cyan:#74ccd1;--coral:#e2836f;--green:#79bfa4}}
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:var(--ink);color:var(--paper);font:15px/1.45 "Segoe UI",sans-serif}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.15;background-image:linear-gradient(rgba(116,204,209,.12) 1px,transparent 1px),linear-gradient(90deg,rgba(116,204,209,.12) 1px,transparent 1px);background-size:64px 64px;mask-image:linear-gradient(to bottom,black,transparent 65%)}}
.shell{{width:min(1440px,calc(100% - 40px));margin:auto;padding:46px 0 80px;position:relative}}
.eyebrow,.scenario small,label{{font:600 11px/1.2 Consolas,monospace;text-transform:uppercase;letter-spacing:.14em;color:var(--gold)}}
.hero{{display:grid;grid-template-columns:1.4fr .8fr;gap:56px;padding:22px 0 40px;border-bottom:1px solid var(--line)}}
h1,h2,h3{{font-family:Georgia,serif}}h1{{font-size:clamp(42px,6vw,76px);line-height:.96;letter-spacing:-.04em;margin:15px 0 20px;max-width:850px}}
.hero p{{color:var(--muted);font-size:18px;max-width:720px}}.scoreboard{{align-self:end;border-left:1px solid var(--gold);padding-left:28px;display:grid;grid-template-columns:repeat(2,1fr);gap:22px}}
.metric b{{display:block;font:36px Georgia;color:var(--paper)}}.metric span{{color:var(--muted);font-size:13px}}
.toolbar{{position:sticky;top:0;z-index:5;background:rgba(6,20,29,.93);backdrop-filter:blur(14px);display:flex;align-items:center;justify-content:space-between;gap:20px;padding:16px 0;border-bottom:1px solid var(--line)}}
.filters{{display:flex;gap:8px}}button{{appearance:none;border:1px solid var(--line);background:transparent;color:var(--muted);padding:9px 14px;border-radius:99px;cursor:pointer;font-weight:600}}button:hover,button:focus-visible,button.active{{color:var(--ink);background:var(--gold);border-color:var(--gold);outline:none}}.toolbar>span{{color:var(--muted);font:12px Consolas}}
.scenario{{margin-top:28px;border:1px solid var(--line);background:linear-gradient(135deg,var(--panel),var(--deep));box-shadow:0 24px 70px rgba(0,0,0,.18)}}
.scenario[hidden]{{display:none}}.scenario-head{{display:flex;align-items:center;justify-content:space-between;padding:20px 24px;border-bottom:1px solid var(--line)}}.scenario-head>div{{display:flex;align-items:center;gap:18px}}.index{{font:28px Georgia;color:var(--gold);min-width:40px}}h2{{font-size:27px;margin:3px 0}}
.status{{border:1px solid;padding:7px 11px;border-radius:2px;font:600 11px Consolas;text-transform:uppercase;letter-spacing:.08em}}.status.adaptado{{color:var(--cyan);border-color:var(--cyan)}}.status.base{{color:var(--muted);border-color:var(--line)}}
.enemy-line{{display:grid;grid-template-columns:repeat(5,1fr);border-bottom:1px solid var(--line)}}.champ{{display:flex;align-items:center;gap:11px;padding:13px 18px;border-right:1px solid var(--line)}}.champ:last-child{{border:0}}.champ img{{width:46px;height:46px;object-fit:cover;object-position:top;border:1px solid #527080}}.champ strong,.champ small{{display:block}}.champ small{{margin-top:3px;color:var(--muted)}}
.builds{{display:grid;grid-template-columns:1fr 1fr;border-bottom:1px solid var(--line)}}.builds>div{{padding:20px 22px;min-width:0}}.builds>div+div{{border-left:1px solid var(--line)}}.build-rail{{display:grid;grid-template-columns:repeat(7,minmax(62px,1fr));gap:8px;margin-top:12px}}
.item{{position:relative;min-width:0}}.item img{{display:block;width:100%;aspect-ratio:1;object-fit:cover;border:1px solid #456471;background:#06141d}}.item strong{{display:block;margin-top:6px;color:var(--muted);font-size:11px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}.item .slot{{position:absolute;z-index:1;top:4px;left:4px;min-width:20px;text-align:center;background:rgba(6,20,29,.9);color:var(--gold);font:10px Consolas;padding:3px}}.item.alterado img{{border:2px solid var(--gold);box-shadow:0 0 0 3px rgba(216,180,93,.13)}}.item.alterado strong{{color:var(--paper)}}
.decisions{{padding:22px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}}.decision{{border:1px solid var(--line);background:rgba(6,20,29,.35)}}.decision-main{{display:grid;grid-template-columns:54px 1fr auto;align-items:center;gap:13px;padding:14px}}.decision-main img{{width:54px;height:54px;border:1px solid var(--gold)}}.decision h3{{font-size:19px;margin:2px 0}}.decision p{{margin:0;color:var(--muted);font-size:13px}}.confidence{{text-align:right;color:var(--muted);font-size:11px}}.confidence b{{display:block;font:18px Georgia;color:var(--paper)}}.confidence.forte b{{color:var(--cyan)}}
details{{border-top:1px solid var(--line)}}summary{{cursor:pointer;padding:11px 14px;color:var(--muted);font-size:12px;display:flex;justify-content:space-between}}summary:hover{{color:var(--paper)}}.evidence{{padding:4px 14px 14px}}.evidence-row{{display:grid;grid-template-columns:82px 1fr 58px;gap:9px;align-items:center;margin:7px 0;font-size:12px}}.evidence-row code{{text-align:right;color:var(--muted)}}.bar-track{{height:4px;background:#193541}}.bar-track i{{display:block;height:100%}}.bar-track .pos{{background:var(--cyan)}}.bar-track .neg{{background:var(--coral)}}
.base-note{{grid-column:1/-1;display:flex;align-items:center;gap:16px;color:var(--muted);padding:10px 2px}}.base-note>span{{font:36px Georgia;color:var(--line)}}.base-note strong{{color:var(--paper)}}.base-note p{{margin:4px 0}}
.scenario-foot{{display:flex;justify-content:space-between;padding:12px 22px;border-top:1px solid var(--line);color:var(--muted);font:11px Consolas}}
.legend{{margin-top:42px;color:var(--muted);border-top:1px solid var(--line);padding-top:18px;font-size:13px}}
@media(max-width:980px){{.hero{{grid-template-columns:1fr}}.scoreboard{{max-width:500px}}.builds{{grid-template-columns:1fr}}.builds>div+div{{border-left:0;border-top:1px solid var(--line)}}.decisions{{grid-template-columns:1fr}}.enemy-line{{overflow-x:auto;grid-template-columns:repeat(5,180px)}}}}
@media(max-width:640px){{.shell{{width:min(100% - 22px,1440px);padding-top:20px}}.toolbar{{align-items:flex-start;flex-direction:column}}.build-rail{{grid-template-columns:repeat(4,1fr)}}.scenario-head,.scenario-foot{{align-items:flex-start;gap:12px;flex-direction:column}}.decision-main{{grid-template-columns:48px 1fr}}.confidence{{grid-column:2;text-align:left}}}}
@media(prefers-reduced-motion:reduce){{html{{scroll-behavior:auto}}}}
</style></head><body><main class="shell">
<section class="hero"><div><span class="eyebrow">Draft Advisor · validação do motor principal</span><h1>Vinte drafts. Uma build que precisa saber quando mudar.</h1><p>O painel mostra o que o motor faria em cada composição mista. A leitura começa pela decisão final; os cálculos dos cinco matchups ficam disponíveis logo abaixo de cada troca.</p></div>
<div class="scoreboard"><div class="metric"><b>{len(registros)}</b><span>drafts testados</span></div><div class="metric"><b>{adaptados}</b><span>builds adaptadas</span></div><div class="metric"><b>{len(registros)-adaptados}</b><span>bases mantidas</span></div><div class="metric"><b>{falhas}</b><span>invariantes quebradas</span></div></div></section>
<nav class="toolbar"><div class="filters"><button class="active" data-filter="all">Todos</button><button data-filter="adaptado">Adaptados</button><button data-filter="base">Sem troca</button></div><span>Emerald+ · 30 dias · {dados["duracao_total_segundos"]:.1f}s em cache</span></nav>
<div id="scenarios">{"".join(secoes)}</div>
<p class="legend"><b>Como ler:</b> o contorno dourado identifica o slot alterado. “Limite” é a melhoria mínima ainda compatível com a incerteza do sinal. As barras mostram quanto cada adversário puxou a recomendação para cima ou para baixo.</p>
</main><script>
const buttons=[...document.querySelectorAll('[data-filter]')];const cards=[...document.querySelectorAll('.scenario')];
buttons.forEach(button=>button.addEventListener('click',()=>{{buttons.forEach(b=>b.classList.remove('active'));button.classList.add('active');const f=button.dataset.filter;cards.forEach(c=>c.hidden=f!=='all'&&c.dataset.status!==f);}}));
</script></body></html>'''
    SAIDA.write_text(documento, encoding="utf-8")
    return SAIDA


if __name__ == "__main__":
    print(gerar())


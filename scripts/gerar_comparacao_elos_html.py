"""Gera o painel visual da comparação experimental entre recortes de elo."""

from __future__ import annotations

import html
import json
from pathlib import Path

from advisor.data import ddragon
from scripts.explorar_transferencias import CENARIOS_ANTERIORES as CENARIOS

RAIZ = Path(__file__).resolve().parents[1]
ELOS = ("master_plus", "diamond_plus", "emerald_plus", "platinum_plus")
ROTULOS = {
    "master_plus": "Master+", "diamond_plus": "Diamond+",
    "emerald_plus": "Emerald+", "platinum_plus": "Platinum+",
}
ROTAS = {"top": "Topo", "jungle": "Selva", "middle": "Meio",
         "bottom": "Atirador", "support": "Suporte"}


def e(valor) -> str:
    return html.escape(str(valor), quote=True)


def main():
    static = ddragon.load()
    origem = RAIZ / "relatorios" / "comparacao-elos.json"
    registros = json.loads(origem.read_text(encoding="utf-8"))
    por_chave = {(r["cenario"], r["elo"]): r for r in registros}
    ids_por_nome = {nome: iid for iid, nome in static.items.items()}

    secoes = []
    for indice, (cenario, dados) in enumerate(CENARIOS, 1):
        campeoes = []
        for nome, rota in dados:
            champ = static.champion(nome)
            if champ is None:
                continue
            campeoes.append(
                f'<li><img src="{e(static.champion_icon(champ.key))}" '
                f'alt=""><span>{e(ROTAS[rota])}</span><b>{e(champ.name)}</b></li>')
        celulas = []
        for elo in ELOS:
            r = por_chave.get((cenario, elo), {})
            modos = []
            for sufixo, classe in (("165", "seguro"), ("150", "sensivel")):
                nome_item = r.get(f"sequencia_{sufixo}")
                iid = ids_por_nome.get(nome_item)
                margem = r.get(f"limite_{sufixo}")
                if nome_item and iid:
                    conteudo = (
                        f'<img src="{e(static.item_icon(iid))}" alt="">'
                        f'<div><b>{e(nome_item)}</b><small>margem conservadora '
                        f'{margem:+.1f}%</small></div>')
                else:
                    conteudo = '<div class="sem"><b>Build base</b><small>nenhuma troca passou</small></div>'
                modos.append(f'<div class="modo {classe}">{conteudo}</div>')
            atual = int(r.get("atual", 0))
            selo = (f'<span class="selo">motor atual · {atual}</span>' if atual else '')
            celulas.append(
                f'<article class="elo"><header><span>{e(ROTULOS[elo])}</span>'
                f'<small>{int(r.get("jogos", 0)):,} jogos</small></header>'
                f'{"".join(modos)}{selo}</article>')
        secoes.append(
            f'<section class="cenario"><div class="cenario-head">'
            f'<span class="indice">{indice:02}</span><div><p>Composição mista</p>'
            f'<h2>{e(cenario)}</h2></div></div><ul class="champions">'
            f'{"".join(campeoes)}</ul><div class="trilha">{"".join(celulas)}</div></section>')

    destino = RAIZ / "relatorios" / "comparacao-elos.html"
    destino.write_text(f'''<!doctype html><html lang="pt-BR"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Recortes de elo · Draft Advisor</title><style>
:root{{--ink:#07131c;--panel:#0d2230;--panel2:#102b3a;--line:#294656;--paper:#e7e1d3;--muted:#8da2aa;--amber:#e7b94b;--blue:#7ec8da;--green:#83d0ad}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--ink);color:var(--paper);font:15px/1.45 "Segoe UI",sans-serif}}
body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.22;background-image:linear-gradient(rgba(126,200,218,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(126,200,218,.035) 1px,transparent 1px);background-size:32px 32px}}
main{{position:relative;width:min(1440px,calc(100% - 40px));margin:auto;padding:48px 0 80px}}
.hero{{display:grid;grid-template-columns:1fr auto;align-items:end;gap:30px;padding-bottom:28px;border-bottom:1px solid var(--line)}}
.eyebrow,.cenario-head p{{margin:0;color:var(--amber);font:700 11px/1.2 Consolas,monospace;letter-spacing:.16em;text-transform:uppercase}}
h1{{font:500 clamp(38px,6vw,76px)/.95 Georgia,serif;letter-spacing:-.045em;margin:10px 0 16px;max-width:780px}}
.lede{{color:var(--muted);max-width:720px;margin:0;font-size:17px}}.switch{{display:flex;padding:4px;border:1px solid var(--line);background:#091a25}}
.switch button{{border:0;background:transparent;color:var(--muted);padding:11px 16px;font:700 12px Consolas;cursor:pointer}}
.switch button.active{{background:var(--amber);color:#17202a}}.switch button:focus-visible{{outline:2px solid var(--blue);outline-offset:2px}}
.summary{{display:flex;gap:28px;padding:18px 0;color:var(--muted);font-family:Consolas,monospace;font-size:12px}}.summary b{{color:var(--paper)}}
.cenario{{display:grid;grid-template-columns:220px 1fr;gap:14px 24px;padding:28px 0;border-top:1px solid var(--line)}}
.cenario-head{{display:flex;gap:14px;align-items:flex-start}}.indice{{color:var(--line);font:38px/1 Georgia,serif}}h2{{margin:3px 0 0;font:500 25px/1.1 Georgia,serif}}
.champions{{grid-column:1;list-style:none;margin:5px 0 0;padding:0;display:grid;gap:5px}}.champions li{{display:grid;grid-template-columns:34px 58px 1fr;align-items:center;gap:8px}}
.champions img{{width:34px;height:34px;object-fit:cover;filter:saturate(.78)}}.champions span{{font:10px Consolas;color:var(--muted);text-transform:uppercase}}.champions b{{font-size:13px}}
.trilha{{grid-column:2;grid-row:1/3;display:grid;grid-template-columns:repeat(4,1fr);align-self:stretch;border:1px solid var(--line);background:var(--panel)}}
.elo{{position:relative;min-width:0;padding:16px;border-left:1px solid var(--line)}}.elo:first-child{{border-left:0}}.elo:after{{content:"";position:absolute;top:55px;left:-4px;width:7px;height:7px;border-radius:50%;background:var(--amber)}}.elo:first-child:after{{display:none}}
.elo header{{display:flex;justify-content:space-between;gap:8px;padding-bottom:13px;border-bottom:1px solid var(--line)}}.elo header span{{font:700 12px Consolas;color:var(--blue);text-transform:uppercase}}.elo header small{{color:var(--muted);font:10px Consolas}}
.modo{{display:none;align-items:center;gap:11px;min-height:76px;padding-top:14px}}body[data-mode="165"] .modo.seguro,body[data-mode="150"] .modo.sensivel{{display:flex}}
.modo img{{width:52px;height:52px;border:1px solid var(--amber)}}.modo b{{display:block;font-size:14px}}.modo small{{display:block;color:var(--green);font:11px Consolas;margin-top:4px}}.modo .sem small{{color:var(--muted)}}
.selo{{display:inline-block;margin-top:8px;padding:3px 6px;border:1px solid #806b37;color:var(--amber);font:9px Consolas;text-transform:uppercase}}
@media(max-width:1000px){{.cenario{{grid-template-columns:1fr}}.champions{{grid-column:1;grid-template-columns:repeat(5,1fr)}}.champions li{{grid-template-columns:34px 1fr}}.champions span{{display:none}}.trilha{{grid-column:1;grid-row:auto}}}}
@media(max-width:720px){{main{{width:min(100% - 24px,1440px);padding-top:28px}}.hero{{grid-template-columns:1fr}}.switch{{width:max-content}}.trilha{{grid-template-columns:1fr 1fr}}.elo:nth-child(3){{border-left:0;border-top:1px solid var(--line)}}.elo:nth-child(4){{border-top:1px solid var(--line)}}.champions{{grid-template-columns:1fr 1fr}}}}
@media(prefers-reduced-motion:no-preference){{.cenario{{animation:rise .35s both;animation-timeline:view();animation-range:entry 0 entry 25%}}@keyframes rise{{from{{opacity:.25;transform:translateY(12px)}}}}}}
</style></head><body data-mode="165"><main>
<header class="hero"><div><p class="eyebrow">Laboratório de builds · Ashe</p><h1>O elo muda a leitura do draft.</h1><p class="lede">As mesmas dez composições, avaliadas em quatro populações. Alterne o nível de confiança e acompanhe onde cada item aparece.</p></div>
<div class="switch" role="group" aria-label="Nível de confiança"><button class="active" data-mode="165">Mais seletivo · z 1,65</button><button data-mode="150">Mais sensível · z 1,50</button></div></header>
<div class="summary"><span><b>10</b> composições</span><span><b>4</b> recortes</span><span><b>30 dias</b> de dados</span><span>As populações são cumulativas.</span></div>
{''.join(secoes)}</main><script>
document.querySelectorAll('.switch button').forEach(button=>button.addEventListener('click',()=>{{document.body.dataset.mode=button.dataset.mode;document.querySelectorAll('.switch button').forEach(x=>x.classList.toggle('active',x===button));}}));
</script></body></html>''', encoding="utf-8")
    print(destino)


if __name__ == "__main__":
    main()


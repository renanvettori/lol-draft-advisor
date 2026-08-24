"""Relatório visual da recomendação final, aberto localmente no navegador."""
from __future__ import annotations

import html as _html
import os
import webbrowser
from datetime import datetime
from pathlib import Path

from advisor.domain import recomendador as R
from advisor.domain import adaptacao as A
from advisor.fluxos import execucao

RAIZ_PROJETO = Path(__file__).resolve().parents[2]


def _e(valor) -> str:
    return _html.escape(str(valor), quote=True)


def _asset(static, metodo: str, ref, alt: str, classe: str = "icon") -> str:
    resolvedor = getattr(static, metodo, None)
    src = resolvedor(ref) if callable(resolvedor) else ""
    if not src:
        return f'<span class="{classe} fallback" aria-hidden="true"></span>'
    return (f'<img class="{classe}" src="{_e(src)}" alt="{_e(alt)}" '
            'loading="eager" referrerpolicy="no-referrer">')


def _estado(decisao: R.Decisao) -> tuple[str, str]:
    return {
        R.EstadoDecisao.PERSONALIZADA: ("Ajustada ao draft", "custom"),
        R.EstadoDecisao.SEM_EVIDENCIA: ("Base mantida", "base"),
        R.EstadoDecisao.FALTA_DADOS: ("Dados insuficientes", "warn"),
        R.EstadoDecisao.ERRO: ("Falha no cálculo", "warn"),
    }[decisao.estado]


def _evidencia(troca) -> str:
    z = troca.delta / troca.erro if troca.erro else 0.0
    jogos = f"{troca.jogos:,}".replace(",", ".")
    return (f"{troca.delta:+.2f} pp · z {z:.2f} · {jogos} jogos · "
            f"{troca.matchups}/5 confrontos")


def _runa(static, rid: int, compacta: bool = False) -> str:
    nome = static.rune(rid)
    classe = "rune compact" if compacta else "rune"
    return (f'<div class="{classe}">{_asset(static, "rune_icon", rid, nome)}'
            f'<span>{_e(nome)}</span></div>')


def _runas(decisao: R.Decisao, static) -> str:
    pagina = decisao.recomendado
    if pagina is None:
        return _vazio(decisao)
    primaria = "".join(_runa(static, rid) for rid in pagina.primary)
    secundaria = "".join(_runa(static, rid, True) for rid in pagina.secondary)
    fragmentos = "".join(_runa(static, rid, True) for rid in pagina.mods)
    trocas = "".join(
        '<article class="evidence"><div><span class="eyebrow">Runa alterada</span>'
        f'<strong>{_e(static.rune(t.saiu))} <b>→</b> {_e(static.rune(t.entrou))}</strong></div>'
        f'<code>{_e(_evidencia(t))}</code></article>' for t in decisao.trocas)
    return f"""<div class="rune-board">
      <div class="rune-path"><span class="eyebrow">Caminho principal</span>{primaria}</div>
      <div class="rune-side"><div><span class="eyebrow">Caminho secundário</span>{secundaria}</div>
      <div><span class="eyebrow">Fragmentos</span>{fragmentos}</div></div></div>
      {f'<div class="evidence-list">{trocas}</div>' if trocas else ''}"""


def _feiticos(decisao: R.Decisao, static, ordem_aplicada=None) -> str:
    ids = ordem_aplicada or decisao.recomendado or ()
    if not ids:
        return _vazio(decisao)
    teclas = ("D", "F")
    cards = "".join(
        '<div class="spell">'
        f'<kbd>{teclas[i]}</kbd>{_asset(static, "spell_icon", sid, static.spell(sid), "spell-icon")}'
        f'<div><span class="eyebrow">Tecla {teclas[i]}</span><strong>{_e(static.spell(sid))}</strong></div></div>'
        for i, sid in enumerate(ids[:2]))
    troca = decisao.trocas[0] if decisao.trocas else None
    evidencia = (f'<article class="evidence spell-evidence"><span class="eyebrow">Sinal do draft</span>'
                 f'<code>{_e(_evidencia(troca))}</code></article>') if troca else ""
    return f'<div class="spell-row">{cards}{evidencia}</div>'


def _itens(decisao: R.Decisao, static) -> str:
    sequencia = decisao.recomendado or ()
    if not sequencia:
        return _vazio(decisao)
    cards = []
    for indice, (slot, iid) in enumerate(sequencia, 1):
        nome = static.item(iid)
        cards.append('<li class="item">'
                     f'<span class="order">{indice:02d}</span>'
                     f'{_asset(static, "item_icon", iid, nome, "item-icon")}'
                     f'<span class="slot">{_e(slot)}</span><strong>{_e(nome)}</strong></li>')
    trocas = "".join(
        '<article class="evidence"><div><span class="eyebrow">Mudança na sequência</span>'
        f'<strong>{_e(t.slot)} · {_e(static.item(t.saiu))} <b>→</b> {_e(static.item(t.entrou))}</strong></div>'
        f'<code>{_e(_evidencia(t))}</code></article>' for t in decisao.trocas)
    return (f'<ol class="build-rail">{"".join(cards)}</ol>'
            + (f'<div class="evidence-list">{trocas}</div>' if trocas else ''))


def _lista_motor(sequencia, static) -> str:
    if not sequencia:
        return '<p class="empty">Sem sequência disponível.</p>'
    return '<ol class="engine-build">' + ''.join(
        '<li>'
        f'<span class="order">{indice + 1:02d}</span>'
        f'{_asset(static, "item_icon", iid, static.item(iid), "engine-icon")}'
        f'<span><small>{_e(slot)}</small><strong>{_e(static.item(iid))}</strong></span></li>'
        for indice, (slot, iid) in enumerate(sequencia)
    ) + '</ol>'


def _motores_itens(resultado: execucao.ResultadoDoDraft, static) -> str:
    experimental = resultado.adaptacao_elo_alto
    popular = resultado.recomendacao.sequencia.recomendado or ()
    sequencia = experimental.sequencia if experimental and experimental.sequencia else popular
    if experimental is None:
        estado, meta = "Build popular", "Sem adaptação adicional configurada."
    elif experimental.estado == A.EstadoAdaptacao.DADOS_INSUFICIENTES:
        estado = "Build popular"
        meta = experimental.falha or "Amostra insuficiente; nenhuma troca foi aplicada."
    elif experimental.estado == A.EstadoAdaptacao.ERRO:
        estado = "Build popular"
        meta = "Falha na adaptação; a build popular foi preservada."
    else:
        estado = "Adaptada ao draft" if experimental.acoes else "Build base mantida"
        meta = f'{experimental.elo} · {len(experimental.acoes)} adaptação(ões)'
    estilo = '''<style>
    .engine-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}
    .engine-panel{background:#0c2233;border:1px solid #5dc7d566;padding:18px}
    .engine-panel>header{display:flex;justify-content:space-between;gap:12px;align-items:start}.engine-panel h3{margin:4px 0;color:var(--pale);font:20px "Palatino Linotype",Georgia,serif}.engine-panel>p,.engine-note{color:var(--muted)}
    .engine-build{list-style:none;margin:14px 0 0;padding:0;display:grid;gap:7px}.engine-build li{position:relative;display:grid;grid-template-columns:34px 48px 1fr;align-items:center;gap:10px;padding:7px;border:1px solid #294b61;background:#0a1c2b}
    .engine-build .order{position:static;text-align:center;background:transparent;padding:0}.engine-icon{width:48px;height:48px;object-fit:cover;border:1px solid var(--gold)}.engine-build small{display:block;color:var(--muted);font:9px Consolas;text-transform:uppercase}.engine-build strong{display:block;color:var(--pale)}.engine-note{margin:12px 0 0;font-size:12px}
    </style>'''
    return estilo + f'''<div class="engine-grid">
      <article class="engine-panel"><header><div><span class="eyebrow">Motor por escolhas</span>
      <h3>Build popular adaptada ao draft · Emerald+</h3></div><span class="badge custom">{_e(estado)}</span></header>
      <p>{_e(meta)}</p>{_lista_motor(sequencia, static)}
      </article></div><p class="engine-note">A build começa pela popularidade e só muda quando a evidência de pick rate dos matchups é suficiente.</p>'''


def _vazio(decisao: R.Decisao) -> str:
    mensagem = decisao.falha.resumo if decisao.falha else "Sem recomendação disponível"
    return f'<p class="empty">{_e(mensagem)}</p>'


def _secao(numero: str, titulo: str, decisao: R.Decisao, conteudo: str) -> str:
    rotulo, classe = _estado(decisao)
    return f"""<section><header class="section-head"><div><span class="section-no">{numero}</span>
      <h2>{_e(titulo)}</h2></div><span class="badge {classe}">{_e(rotulo)}</span></header>
      {conteudo}</section>"""


def _calculos(resultado: execucao.ResultadoDoDraft,
              contexto: execucao.ContextoExecucao) -> str:
    """Auditoria legível dos dados que sustentaram o snapshot final."""
    rec, paginas = resultado.recomendacao, resultado.paginas_do_draft
    cfg, static = contexto.config, contexto.dados_estaticos
    origem_rotas = ("Posições confirmadas pelo cliente da partida"
                    if resultado.draft.rotas_confirmadas
                    else "Posições inferidas durante o draft")
    pesos = []
    if paginas is not None:
        total = sum(paginas.peso(c.cid) for c in resultado.draft.enemies) or 1.0
        for champ in resultado.draft.enemies:
            peso, motivos = paginas.relevancias.get(champ.cid, (1.0, ["outra rota"]))
            pesos.append('<tr><td><span class="champ-cell">'
                         f'{_asset(static, "champion_icon", champ.key, champ.name, "mini-champ")}'
                         f'<strong>{_e(champ.name)}</strong></span></td><td>{peso:.2f}</td>'
                         f'<td>{peso / total * 100:.1f}%</td><td>{_e("; ".join(motivos))}</td></tr>')
    tabela = (f'<table><thead><tr><th>Inimigo</th><th>Peso</th><th>Participação</th><th>Motivo</th>'
              f'</tr></thead><tbody>{"".join(pesos)}</tbody></table>' if pesos
              else '<p class="empty">Pesos indisponíveis.</p>')
    blocos = []
    for categoria, decisao in (("Runas", rec.runas), ("Feitiços", rec.feiticos)):
        if not decisao.trocas:
            blocos.append(f'<article class="calc-card"><span class="eyebrow">{categoria}</span>'
                          '<strong>Nenhuma troca passou no corte</strong>'
                          '<p>A build base foi mantida.</p></article>')
        for troca in decisao.trocas:
            barras = "".join(
                '<li><span><b>' + _e(nome) + '</b><em>'
                + _e(f"{delta:+.2f} pp · {jogos:,} jogos".replace(",", "."))
                + '</em></span><i style="--v:' + str(min(abs(delta) * 12, 100))
                + '%" class="' + ("positive" if delta >= 0 else "negative")
                + '"></i></li>' for nome, delta, jogos in getattr(troca, "detalhe", ()))
            blocos.append(f'<article class="calc-card"><span class="eyebrow">{categoria}</span>'
                          f'<strong>{_e(_evidencia(troca))}</strong>'
                          + (f'<ul class="matchup-bars">{barras}</ul>' if barras else
                             '<p>Sem decomposição individual disponível.</p>') + '</article>')
    jogos_min = f"{cfg.jogos_minimos:,}".replace(",", ".")
    adapt = resultado.adaptacao_elo_alto
    auditoria_adaptacao = ""
    if adapt is not None:
        ordem_inimigos = {c.name: i for i, c in enumerate(resultado.draft.enemies)}

        def card_acao(a):
            saida = (f' · sai {_e(static.item(a.removido))}' if a.removido else '')
            linhas = ''.join(
                f'<tr><td><strong>{_e(ev.inimigo)}</strong></td>'
                f'<td class="{"positive" if ev.contribuicao >= 0 else "negative"}">'
                f'{ev.contribuicao:+.3f}</td><td>{ev.pick_matchup:.2f}%</td>'
                f'<td>{ev.pick_base:.2f}%</td></tr>'
                for ev in sorted(a.evidencias,
                                 key=lambda ev: ordem_inimigos.get(ev.inimigo, 99)))
            return (f'<article class="calc-card action-card"><span class="eyebrow">{_e(a.tipo)}</span>'
                    f'<strong>{_e(static.item(a.item_id))} → {_e(a.slot_destino)}</strong>'
                    f'<p>{_e(A.confianca(a.z))} · z {a.z:.2f}{saida}</p>'
                    f'<div class="table-wrap"><table><thead><tr><th>Inimigo</th>'
                    f'<th>Contribuição</th><th>Candidato</th><th>Referência</th>'
                    f'</tr></thead><tbody>{linhas}</tbody></table></div></article>')

        acoes = ''.join(card_acao(a) for a in adapt.acoes) or (
            '<p class="empty">A build base de Emerald+ foi mantida.</p>')
        alternativas = ''.join(
            '<li><strong>' + _e(' → '.join(
                static.item(iid) for _, iid in alt.sequencia)) + '</strong>'
            f'<small>{_e(A.confianca(alt.z_conjunto))} · z {alt.z_conjunto:.2f}</small></li>'
            for alt in adapt.alternativas) or '<li class="empty">Nenhuma sequência exploratória.</li>'
        conjunto = (f'{_e(A.confianca(adapt.z_conjunto))} · z {adapt.z_conjunto:.2f}'
                    if adapt.z_conjunto else "somente botas ou build base")
        item6 = ('<p>Item 6 estimado combinando Item 5 com presença total.</p>'
                 if adapt.item6_estimado else '')
        cache = ""
        if adapt.cache_em:
            try:
                cache_data = datetime.fromisoformat(adapt.cache_em).astimezone()
                cache = f'<p>Fonte indisponível: cache compatível de {cache_data:%d/%m/%Y %H:%M}.</p>'
            except ValueError:
                cache = '<p>Fonte indisponível: usando cache compatível.</p>'
        auditoria_adaptacao = f'''<h3>Adaptação ao draft · Emerald+</h3>
        <div class="method-intro"><div><span class="eyebrow">Elo selecionado</span>
        <strong>{_e(adapt.elo or "nenhum")}</strong></div><div><span class="eyebrow">Testes</span>
        <strong>{adapt.hipoteses_avaliadas} avaliados · {adapt.passaram_z} passaram z · {adapt.sobreviveram_fdr} botas passaram FDR</strong></div>
        <div><span class="eyebrow">Confiança conjunta</span><strong>{conjunto}</strong></div>
        <p>Recorte fixo: Emerald+ · itens sem FDR · botas com FDR.</p>{item6}{cache}</div>
        <div class="calc-grid">{acoes}</div>
        <h4>Sequências exploratórias</h4><ol class="alternatives">{alternativas}</ol>'''
    return f"""<section class="method"><header class="section-head"><div>
      <span class="section-no">04</span><h2>Como o advisor decidiu</h2></div>
      <span class="badge">Auditoria do cálculo</span></header>
      <div class="method-intro"><div><span class="eyebrow">Recorte</span>
      <strong>{_e(rec.recorte_matchups.elo)} · {_e(rec.recorte_matchups.janela)}</strong></div>
      <div><span class="eyebrow">Corte de runas e feitiços</span><strong>z ≥ {cfg.z_minimo:.2f} · {jogos_min}+ jogos</strong></div>
      <div><span class="eyebrow">Rotas usadas nos itens</span><strong>{_e(origem_rotas)}</strong></div>
      <p>Runas e feitiços são comparados à opção mais escolhida em cada confronto. A build
      de itens parte da popularidade e só muda quando a adaptação por pick rate tem evidência.</p></div>
      <h3>Quanto cada confronto pesou</h3><div class="table-wrap">{tabela}</div>
      <h3>Resultado dos cortes</h3><div class="calc-grid">{"".join(blocos)}</div>
      {auditoria_adaptacao}
      <details><summary>Como ler os números</summary><p><b>Delta</b> é a diferença de win rate
      contra a escolha base no mesmo matchup. <b>z</b> divide o efeito pela incerteza:
      quanto maior, mais firme o sinal. A amostra soma apenas observações que
      contribuíram; ausência de dado não conta como voto contra.</p></details></section>"""


def _resolver_pasta(valor: str) -> Path:
    pasta = Path(os.path.expandvars(os.path.expanduser(valor)))
    return pasta if pasta.is_absolute() else RAIZ_PROJETO / pasta


def gerar(resultado: execucao.ResultadoDoDraft,
          contexto: execucao.ContextoExecucao,
          aplicacao: execucao.ResultadoAplicacao | None = None) -> Path:
    """Gera o snapshot final e devolve seu caminho absoluto."""
    draft, rec, static = resultado.draft, resultado.recomendacao, contexto.dados_estaticos
    pasta = _resolver_pasta(contexto.config.html_pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    agora = datetime.now().astimezone()
    oponente = draft.opponent.name if draft.opponent else "não identificado"
    inimigos = "".join(
        f'<li class="{"opponent" if draft.opponent and c.cid == draft.opponent.cid else ""}">'
        + _asset(static, "champion_icon", c.key, c.name, "champ-icon")
        + f'<span>{_e(c.name)}</span></li>' for c in draft.enemies)
    status = aplicacao.estados if aplicacao else {}
    aplicacoes = "".join(
        f'<span>{_e(nome.capitalize())}: <b>{_e(valor.replace("_", " "))}</b></span>'
        for nome, valor in status.items())
    splash = getattr(static, "champion_splash", lambda _: "")(draft.champion.key)
    corpo = (_secao("01", "Runas", rec.runas, _runas(rec.runas, static))
             + _secao("02", "Feitiços", rec.feiticos, _feiticos(
                 rec.feiticos, static, aplicacao.ordem_feiticos if aplicacao else None))
             + _secao("03", "Rotas de compra", rec.sequencia,
                      _motores_itens(resultado, static))
             + _calculos(resultado, contexto))

    documento = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_e(draft.champion.name)} · plano de partida</title>
<style>
:root{{--ink:#071521;--panel:#102c40;--gold:#c9a75d;--pale:#e8dcc1;--ice:#dbeaf1;--muted:#8ba5b4;--cyan:#5dc7d5;--warn:#e9b36a}}
*{{box-sizing:border-box}}html{{background:var(--ink)}}body{{margin:0;color:var(--ice);font:15px/1.45 "Segoe UI",Arial,sans-serif;background:linear-gradient(115deg,#071521,#0a1c2b 60%,#071521)}}body:before{{content:"";position:fixed;inset:0;pointer-events:none;opacity:.16;background-image:linear-gradient(#5dc7d510 1px,transparent 1px),linear-gradient(90deg,#5dc7d510 1px,transparent 1px);background-size:34px 34px}}
.hero{{min-height:300px;position:relative;display:flex;align-items:flex-end;overflow:hidden;border-bottom:1px solid #c9a75d55;background:#0b1c29}}.hero-bg{{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:center 24%;filter:saturate(.74) contrast(1.08)}}.hero:after{{content:"";position:absolute;inset:0;background:linear-gradient(90deg,#071521 3%,#071521dd 32%,#07152144 68%,#071521cc),linear-gradient(0deg,#071521 0%,transparent 60%)}}
.hero-inner{{position:relative;z-index:1;width:min(1180px,calc(100% - 44px));margin:0 auto 28px;display:grid;grid-template-columns:1fr auto;gap:30px;align-items:end}}.kicker,.eyebrow{{display:block;color:var(--gold);font:700 10px/1.2 Consolas,monospace;text-transform:uppercase;letter-spacing:.16em}}h1{{margin:7px 0 9px;color:var(--pale);font:700 clamp(38px,7vw,74px)/.9 "Palatino Linotype",Georgia,serif;letter-spacing:-.045em}}.subtitle{{margin:0;color:#b9cbd3;font-size:16px}}
.enemy-label{{text-align:right;margin-bottom:9px}}.enemy-line{{display:flex;gap:7px;list-style:none;padding:0;margin:0}}.enemy-line li{{position:relative}}.champ-icon{{display:block;width:48px;height:48px;object-fit:cover;border:1px solid #c9a75d88;background:var(--panel)}}.enemy-line li span{{display:none}}main{{width:min(1180px,calc(100% - 44px));margin:0 auto;padding:25px 0 64px}}.status-line{{display:flex;justify-content:space-between;gap:20px;padding-bottom:17px;border-bottom:1px solid #315065}}.applied{{display:flex;gap:18px;color:var(--muted);font:11px Consolas,monospace;text-transform:uppercase}}.applied b{{color:var(--cyan)}}
section{{padding:29px 0;border-bottom:1px solid #315065}}.section-head{{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px}}.section-head>div{{display:flex;align-items:baseline;gap:13px}}.section-no{{color:var(--gold);font:12px Consolas,monospace}}h2{{margin:0;color:var(--pale);font:700 27px "Palatino Linotype",Georgia,serif}}.badge{{padding:5px 9px;border:1px solid #507084;color:#a8c0cb;font:10px Consolas,monospace;text-transform:uppercase;letter-spacing:.08em}}.badge.custom{{border-color:#5dc7d588;color:var(--cyan)}}.badge.warn{{border-color:#e9b36a88;color:var(--warn)}}
.rune-board{{display:grid;grid-template-columns:1.5fr 1fr;gap:24px;background:#0c2233;border:1px solid #294b61;padding:20px}}.rune-path{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}}.rune-path>.eyebrow{{grid-column:1/-1}}.rune-side{{display:grid;gap:18px;border-left:1px solid #315065;padding-left:24px}}.rune-side>div{{display:flex;flex-wrap:wrap;gap:9px}}.rune-side .eyebrow{{width:100%}}.rune{{min-width:0;display:flex;flex-direction:column;align-items:center;text-align:center;gap:7px;color:#bdd0d9;font-size:12px}}.rune .icon{{width:54px;height:54px;object-fit:contain;background:#071521;border-radius:50%;border:1px solid #42647a;padding:3px}}.rune:first-of-type .icon{{border-color:var(--gold);box-shadow:0 0 18px #c9a75d33}}.rune.compact{{flex-direction:row;text-align:left}}.rune.compact .icon{{width:36px;height:36px}}
.spell-row{{display:grid;grid-template-columns:repeat(2,minmax(180px,260px)) 1fr;gap:12px}}.spell{{position:relative;display:grid;grid-template-columns:64px 1fr;align-items:center;gap:14px;background:var(--panel);border:1px solid #31556c;padding:13px}}.spell-icon{{width:64px;height:64px;object-fit:cover}}.spell strong{{display:block;color:var(--pale);font-size:18px}}kbd{{position:absolute;top:5px;left:5px;z-index:1;background:#071521dd;border:1px solid var(--gold);color:var(--pale);padding:2px 6px;font:700 12px Consolas}}
.build-rail{{display:grid;grid-template-columns:repeat(6,1fr);list-style:none;padding:0;margin:0;position:relative}}.build-rail:before{{content:"";position:absolute;left:8%;right:8%;top:50px;border-top:1px solid var(--gold)}}.item{{position:relative;z-index:1;display:grid;justify-items:center;text-align:center;padding:0 8px}}.item:not(:last-child):after{{content:"";position:absolute;right:-5px;top:46px;width:8px;height:8px;border-top:2px solid var(--gold);border-right:2px solid var(--gold);background:var(--ink);transform:rotate(45deg)}}.item-icon{{width:74px;height:74px;object-fit:cover;border:2px solid var(--gold);background:var(--panel);box-shadow:0 7px 20px #0008}}.order{{position:absolute;top:-7px;left:calc(50% - 47px);background:var(--ink);color:var(--gold);font:11px Consolas;padding:2px 4px}}.slot{{color:var(--muted);font:10px Consolas,monospace;text-transform:uppercase;margin-top:9px}}.item strong{{color:var(--pale);font-size:13px;line-height:1.25}}
.evidence-list{{margin-top:18px}}.evidence{{display:flex;justify-content:space-between;align-items:center;gap:18px;padding:11px 13px;background:#132d3e;border-left:2px solid var(--cyan)}}.evidence strong{{display:block;margin-top:3px}}.evidence b{{color:var(--gold)}}.evidence code{{color:#a9c0ca;font-size:11px;text-align:right}}.spell-evidence{{height:100%;align-items:flex-start;justify-content:center;flex-direction:column}}.empty{{color:var(--warn)}}.fallback{{display:inline-block;background:#17394e}}.foot{{padding-top:17px;color:var(--muted);font:11px Consolas,monospace}}
.method{{border-bottom:0;padding-top:40px}}.method-intro{{display:grid;grid-template-columns:auto auto 1fr;gap:22px;padding:17px;border:1px solid #315065;background:#0c2233;align-items:center}}.method-intro strong{{display:block;color:var(--pale);margin-top:5px}}.method-intro p{{margin:0;color:var(--muted)}}.method h3{{margin:26px 0 10px;color:var(--pale);font:16px "Palatino Linotype",Georgia,serif}}.table-wrap{{overflow-x:auto}}table{{width:100%;border-collapse:collapse;background:#0c2233}}th,td{{padding:10px 12px;text-align:left;border-bottom:1px solid #294b61}}th{{color:var(--gold);font:10px Consolas,monospace;text-transform:uppercase;letter-spacing:.1em}}td{{color:#b9cbd3}}td.positive{{color:var(--cyan)}}td.negative{{color:var(--warn)}}.champ-cell{{display:flex;align-items:center;gap:9px}}.mini-champ{{width:30px;height:30px;object-fit:cover;border:1px solid #42647a}}.calc-grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:10px}}.calc-card{{background:#0c2233;border:1px solid #294b61;padding:15px}}.calc-card.action-card{{grid-column:1/-1}}.calc-card>strong{{display:block;color:var(--pale);margin:5px 0 10px}}.calc-card p{{color:var(--muted);margin:8px 0 0}}.alternatives{{display:grid;gap:8px;padding-left:22px}}.alternatives li{{padding:10px;background:#0c2233;border:1px solid #294b61}}.alternatives strong,.alternatives small{{display:block}}.alternatives small{{color:var(--muted);margin-top:4px}}.matchup-bars{{list-style:none;padding:0;margin:0}}.matchup-bars li{{padding:7px 0;border-top:1px solid #294b61}}.matchup-bars span{{display:flex;justify-content:space-between;gap:12px;font-size:12px}}.matchup-bars em{{color:var(--muted);font:11px Consolas,monospace}}.matchup-bars i{{display:block;width:var(--v);height:2px;margin-top:5px;background:var(--cyan)}}.matchup-bars i.negative{{background:var(--warn)}}details{{margin-top:18px;border-left:2px solid var(--gold);padding:9px 13px;background:#0c2233}}summary{{cursor:pointer;color:var(--pale);font-weight:700}}details p{{color:var(--muted)}}
@media(max-width:800px){{.hero-inner{{grid-template-columns:1fr}}.enemy-label{{text-align:left}}.rune-board,.spell-row,.method-intro,.calc-grid{{grid-template-columns:1fr}}.rune-side{{border-left:0;border-top:1px solid #315065;padding:18px 0 0}}.build-rail{{grid-template-columns:repeat(3,1fr);row-gap:24px}}.build-rail:before,.item:after{{display:none}}.status-line{{flex-direction:column}}}}@media(max-width:480px){{.enemy-line{{flex-wrap:wrap}}.rune-path{{grid-template-columns:repeat(2,1fr)}}.build-rail{{grid-template-columns:repeat(2,1fr)}}.applied{{flex-direction:column;gap:4px}}}}
</style></head><body><header class="hero">{f'<img class="hero-bg" src="{_e(splash)}" alt="">' if splash else ''}<div class="hero-inner"><div><span class="kicker">Plano de partida · {_e(draft.lane or 'rota padrão')}</span><h1>{_e(draft.champion.name)}</h1><p class="subtitle">Foque a rota contra <strong>{_e(oponente)}</strong>. Abaixo está só o que você precisa levar para o jogo.</p></div><div><span class="kicker enemy-label">Composição inimiga</span><ul class="enemy-line">{inimigos}</ul></div></div></header>
<main><div class="status-line"><span class="kicker">{_e(agora.strftime('%d/%m/%Y · %H:%M'))}</span><div class="applied">{aplicacoes}</div></div>{corpo}<footer class="foot">Matchups: {_e(rec.recorte_matchups.elo)} · {_e(rec.recorte_matchups.janela)} · assets oficiais Riot Data Dragon</footer></main></body></html>"""
    caminho = pasta / "ultima-recomendacao.html"
    temporario = pasta / ".ultima-recomendacao.tmp"
    temporario.write_text(documento, encoding="utf-8")
    temporario.replace(caminho)
    return caminho.resolve()


def abrir(caminho: Path) -> None:
    if not webbrowser.open(caminho.resolve().as_uri()):
        raise RuntimeError("o navegador padrão recusou abrir o relatório")


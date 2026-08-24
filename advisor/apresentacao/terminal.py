"""Exibe a recomendação no terminal."""

from __future__ import annotations

import io
import sys

from advisor.domain import draft as draft_mod, recomendador as matchups
from advisor.fluxos import execucao, investigacao

# Evita substituir um stdout que já usa UTF-8.
if hasattr(sys.stdout, "buffer") and (sys.stdout.encoding or "").lower() not in {
    "utf-8", "utf8"
}:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DIM, BOLD, RESET = "\033[2m", "\033[1m", "\033[0m"
GREEN, RED, YELLOW, CYAN = "\033[32m", "\033[31m", "\033[33m", "\033[36m"

MIN_SAMPLE = 1000


def num(value: int) -> str:
    """Separador de milhar no padrão brasileiro."""
    return f"{value:,}".replace(",", ".")


def head(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{text}{RESET}")


def tint(delta: float) -> str:
    color = GREEN if delta > 1 else RED if delta < -1 else ""
    return f"{color}{delta:+.2f}{RESET}" if color else f"{delta:+.2f}"


def status_vigia(texto: str) -> None:
    print(f"{DIM}{texto}{RESET}")


def erro_vigia(texto: str) -> None:
    print(f"{YELLOW}{texto}{RESET}")


def _apresentar_resumo(
    resultado: execucao.ResultadoDoDraft,
    contexto: execucao.ContextoExecucao,
    aplicacao: execucao.ResultadoAplicacao | None,
) -> None:
    """Mostra só as decisões acionáveis; os detalhes ficam no HTML."""
    static = contexto.dados_estaticos
    rec = resultado.recomendacao
    pagina = rec.runas.recomendado
    if pagina is not None:
        prim = " > ".join(static.rune(rid) for rid in pagina.primary)
        sec = " + ".join(static.rune(rid) for rid in pagina.secondary)
        mods = " + ".join(static.rune(rid) for rid in pagina.mods)
        print(f"  {BOLD}Runas:{RESET} {prim} | {sec} | fragmentos: {mods}")
    else:
        print(f"  {YELLOW}Runas: sem recomendação{RESET}")

    feiticos = rec.feiticos.recomendado or ()
    if len(feiticos) == 2:
        nomes = " + ".join(static.spell(sid) for sid in feiticos)
        print(f"  {BOLD}Feitiços:{RESET} D {static.spell(feiticos[0])} · "
              f"F {static.spell(feiticos[1])} ({nomes})")
    else:
        print(f"  {YELLOW}Feitiços: sem recomendação{RESET}")

    adaptacao = resultado.adaptacao_elo_alto
    sequencia = adaptacao.sequencia if adaptacao and adaptacao.sequencia else (
        rec.sequencia.recomendado or ())
    if sequencia:
        nomes = " → ".join(static.item(iid) for _, iid in sequencia)
        origem = ("build popular; amostra insuficiente para adaptar"
                  if adaptacao and adaptacao.estado.value == "dados_insuficientes"
                  else "build popular adaptada ao draft"
                  if adaptacao else "build popular")
        print(f"  {BOLD}Itens:{RESET} {nomes} {DIM}({origem}){RESET}")
    else:
        print(f"  {YELLOW}Itens: sem sequência disponível{RESET}")

    if aplicacao:
        falhas = [falha.resumo for falha in aplicacao.falhas]
        if falhas:
            print(f"  {YELLOW}Falha na aplicação: {'; '.join(falhas)}{RESET}")


def apresentar(
    resultado: execucao.ResultadoDoDraft,
    contexto: execucao.ContextoExecucao,
    aplicacao: execucao.ResultadoAplicacao | None = None,
    resultado_analise: investigacao.ResultadoAnalise | None = None,
) -> None:
    draft = resultado.draft
    static = contexto.dados_estaticos
    args = contexto.config
    me = draft.champion
    build = resultado.pagina_base
    paginas = resultado.paginas_do_draft
    recomendacao = resultado.recomendacao

    print(f"\n{BOLD}{me.name}{RESET} — {build.lane or draft.lane or 'rota padrão'} "
          f"{DIM}| patch {build.patch} | {args.tier_label}"
          f"{RESET}")
    if build.games:
        print(f"  {build.wr}% de vitória em {num(build.games)} partidas"
              f" | tier {build.tier} ({build.rank}º de {build.rank_total})")

    for falha in resultado.falhas:
        print(f"  {YELLOW}{falha.resumo}{RESET}")
    if resultado_analise is not None and resultado_analise.falha:
        print(f"  {YELLOW}{resultado_analise.falha.resumo}{RESET}")

    if not args.detalhe:
        _apresentar_resumo(resultado, contexto, aplicacao)
        return

    # Runas de elo alto só aparecem quando divergem das runas do jogador.
    referencia = resultado.comparacao_elo_alto

    head("Runas")
    if referencia is not None:
        atual = build.rune_pages[0] if build.rune_pages else None
        ref_tier_nome, ref_page = referencia
        if atual and (atual.primary != ref_page.primary
                      or atual.secondary != ref_page.secondary):
            pri = static.style(static.estilo_da_runa(ref_page.primary[0]) or 0)
            sec = static.style(static.estilo_da_runa(ref_page.secondary[0]) or 0)
            print(f"  {BOLD}{GREEN}Em {ref_tier_nome} escolhem diferente:{RESET}")
            print(f"    {' > '.join(static.rune(r) for r in ref_page.primary)}")
            print(f"    {BOLD}{sec}{RESET}: "
                  f"{' + '.join(static.rune(r) for r in ref_page.secondary)}")
            print(f"    {DIM}fragmentos: "
                  f"{', '.join(static.rune(m) for m in ref_page.mods)}{RESET}")
            print(f"  {DIM}abaixo, o do seu elo:{RESET}")

    # Indica matchups cuja página de runas diverge.
    if paginas is not None and build.rune_pages:
        base_pri = build.rune_pages[0].primary
        iguais, divergentes = 0, []
        for enemy, pg in paginas.paginas_de_runa():
            if pg.primary == base_pri:
                iguais += 1
            else:
                divergentes.append((enemy, pg))
        total = iguais + len(divergentes)
        if total:
            if divergentes:
                print(f"  {YELLOW}a runa muda em {len(divergentes)} de {total} "
                      f"matchups:{RESET}")
                for enemy, pg in divergentes:
                    print(f"    vs {enemy.name}: "
                          f"{' > '.join(static.rune(r) for r in pg.primary)}")
            else:
                print(f"  {DIM}mesma runa nos {total} matchups do draft — "
                      f"a página base já é a resposta{RESET}")

    # O filtro por keystone existe na página do campeão, não nos matchups.
    linhas_runa = resultado.estatisticas_de_runa
    if linhas_runa:
        print(f"  {DIM}win rate por runa principal (campeão, não por "
              f"matchup — o site não cruza os dois):{RESET}")
        for r in linhas_runa[:4]:
            if r.delta == 0:
                extra = f"{DIM}mais escolhida{RESET}"
            else:
                cor = GREEN if r.z > 2 else RED if r.z < -2 else ""
                extra = f"{cor}{r.delta:+.2f}pp{RESET} {DIM}±{r.erro:.2f}{RESET}"
            print(f"    {static.rune(r.keystone):26s} {r.wr:5.2f}%  "
                  f"{DIM}{r.share:5.2f}% · {num(r.games)} jogos{RESET}  {extra}")

    # Deriva o rótulo pelo pick rate, sem confiar na ordem do payload.
    def _escolha_media(pagina) -> float:
        vistos = [build.rune_stats.get(r) for r in pagina.primary]
        vistos = [v for v in vistos if v]
        return sum(v.pr for v in vistos) / len(vistos) if vistos else 0.0

    paginas_runa = list(build.rune_pages[:2])
    escolhas = {id(p): _escolha_media(p) for p in paginas_runa}
    mais_escolhida = recomendacao.runas.base

    for page in paginas_runa:
        pri_style = static.style(static.estilo_da_runa(page.primary[0]) or 0) if page.primary else "?"
        sec_style = static.style(static.estilo_da_runa(page.secondary[0]) or 0) if page.secondary else "?"
        if len(paginas_runa) > 1 and page is mais_escolhida:
            rotulo = f"mais escolhida ({escolhas[id(page)]:.0f}% de adesão média)"
        elif len(paginas_runa) > 1:
            rotulo = f"maior win rate ({escolhas[id(page)]:.0f}% de adesão média)"
        else:
            rotulo = ""
        print(f"  {BOLD}{pri_style}{RESET} {DIM}— {rotulo}{RESET}")
        print(f"    {' > '.join(static.rune(r) for r in page.primary)}")
        print(f"    {BOLD}{sec_style}{RESET}: {' + '.join(static.rune(r) for r in page.secondary)}")
        print(f"    {DIM}fragmentos: {', '.join(static.rune(m) for m in page.mods)}{RESET}")

    # Feitiços são escolhidos antes da partida, então o win rate não sofre compra
    # reativa como os itens.
    head("Feitiços")
    conhecidos = {tuple(sorted(sp.ids)) for sp in build.spells}
    # Ordena por amostra em vez de atribuir significado à posição no payload.
    visiveis = [sp for sp in sorted(build.spells, key=lambda s: -s.games)
                if sp.games >= 30][:4]
    for spell in visiveis:
        print(f"  {' + '.join(static.spell(i2) for i2 in spell.ids):30s} "
              f"{spell.wr:5.2f}%  {DIM}{spell.pr:5.2f}% pick · "
              f"{num(spell.games)} jogos{RESET}")

    # Mostra somente alternativas sustentadas pela soma dos matchups.
    for cand in recomendacao.feiticos.trocas:
        nome = " + ".join(static.spell(i) for i in cand.ids)
        padrao = recomendacao.feiticos.base or ()
        print(f"  {GREEN}{nome:30s}{RESET} {DIM}contra este draft: "
              f"{cand.delta:+.2f}pp sobre {' + '.join(static.spell(i) for i in padrao)}"
              f" (±{cand.erro:.2f}) · {cand.matchups}/{cand.total_paginas} "
              f"matchups · {num(cand.jogos)} jogos{RESET}")

    head("Habilidades")
    if build.skill_priority:
        print(f"  prioridade: {BOLD}{' > '.join(build.skill_priority)}{RESET}")
    if build.skill_order:
        print(f"  ordem:      {' '.join(build.skill_order)}")

    head("Build")
    if build.starting_items:
        nomes = ", ".join(static.item(i) for i in build.starting_items.items)
        print(f"  início: {nomes} {DIM}({build.starting_items.wr}%){RESET}")
    if build.core_build:
        nomes = " → ".join(static.item(i) for i in build.core_build.items)
        print(f"  núcleo: {BOLD}{nomes}{RESET} {DIM}({build.core_build.wr}% em "
              f"{num(build.core_build.games)} jogos){RESET}")

    if draft.enemies:
        head("O draft")
        prof = draft_mod.profile_enemies(draft.enemies, static)
        print(f"  composição inimiga: {prof.summary()}")

        counters = paginas.counters if paginas is not None else {}
        if not counters:
            print(f"  {DIM}(sem dados de confronto){RESET}")

        # A camada de dados já resolveu o oponente direto.
        opponent = paginas.opponent if paginas is not None else draft.opponent
        inferido = paginas.opponent_inferido if paginas is not None else False
        if inferido and opponent is not None:
            print(f"  {DIM}oponente direto inferido pela rota padrão: "
                  f"{opponent.name} — já contou no peso dos matchups{RESET}")

        for enemy in draft.enemies:
            match = counters.get(enemy.cid)
            marca = " ←" + ("?" if inferido else "") if opponent and enemy.cid == opponent.cid else ""
            if match is None:
                print(f"    {enemy.name:16s} {DIM}sem dado destacado{RESET}{marca}")
                continue
            aviso = f" {YELLOW}(n={match.games}){RESET}" if match.games < 300 else ""
            print(f"    {enemy.name:16s} {match.vs_wr:5.2f}%  delta {tint(match.delta)}"
                  f"  {DIM}{match.games} jogos{RESET}{aviso}{marca}")

    if (resultado_analise is not None
            and resultado_analise.paginas is not None
            and resultado_analise.scores is not None):
        head("Análise estatística da composição")
        from advisor.domain import analise as stats
        # A análise pode usar um recorte maior que a build base.
        tier_comp = args.analise_elo
        janela = args.analise_janela_dias
        paginas_comp = resultado_analise.paginas
        rel = paginas_comp.relevancias
        total_rel = sum(p for p, _ in rel.values()) or 1.0
        print(f"  {DIM}peso de cada inimigo na decisão (lógica de jogo, "
              f"não amostra):{RESET}")
        for enemy in sorted(draft.enemies, key=lambda c: -rel[c.cid][0]):
            peso, motivos = rel[enemy.cid]
            print(f"    {enemy.name:14s} {peso / total_rel * 100:4.1f}%  "
                  f"{DIM}{'; '.join(motivos)}{RESET}")
        analise = resultado_analise.scores
        usados = resultado_analise.usados
        deslocamento = resultado_analise.deslocamento
        # Exibe os recortes para não misturar as duas leituras.
        print(f"  {DIM}amostra: últimos {janela} dias, {tier_comp} "
              f"— a build acima é do patch {build.patch}, "
              f"{args.pagina_base_elo}{RESET}")
        if not analise:
            print(f"  {YELLOW}nenhum inimigo tinha página de matchup utilizável{RESET}")
        elif args.detalhe:
            print(f"  {DIM}lift = win rate do item contra esta comp menos o win rate "
                  f"dele no geral · peso inverso à variância · prior N(0,{stats.TAU}pp²)"
                  f"{RESET}")
            print(f"  {DIM}matchups: {', '.join(c.name for c in usados)}{RESET}")
            print(f"  {DIM}deslocamento geral do campeão contra esta comp: "
                  f"{deslocamento:+.2f}pp — já descontado das colunas abaixo{RESET}")
            for slot in ["Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5"]:
                scores = [s for s in analise.get(slot, []) if s.obs]
                if not scores:
                    continue
                mostrar = scores if args.todos_os_itens else scores[: args.itens]
                print(f"\n  {BOLD}{slot}{RESET} {DIM}({len(scores)} itens com "
                      f"amostra suficiente){RESET}")
                for s in mostrar:
                    cor = GREEN if s.z > 1.5 else RED if s.z < -1.5 else ""
                    sinal = f"{cor}{s.efeito:+6.2f}pp{RESET}" if cor else f"{s.efeito:+6.2f}pp"
                    print(f"    {static.item(s.item_id):32s} {sinal} "
                          f"{DIM}±{s.sd:.2f} · bruto {s.lift:+5.2f} · "
                          f"{len(s.obs)} matchups · {num(s.jogos_comp):>6} jogos{RESET}")
            print(f"\n  {YELLOW}confiança exibida é otimista:{RESET}"
                  f"{DIM} as páginas compartilham as mesmas partidas.{RESET}")
        else:
            print(f"  {DIM}comparando {len(usados)} matchups: "
                  f"{', '.join(c.name for c in usados)}{RESET}")
            # Corrige os testes simultâneos antes de mostrar candidatos.
            candidatos = [
                s for scores in analise.values() for s in scores
                if len(s.obs) >= 4 and s.jogos_comp >= 1000
            ]
            aprovados = {id(s) for s in stats.corrigir_fdr(candidatos)}
            fortes, fracos = [], []
            for slot, scores in analise.items():
                for s in scores:
                    if len(s.obs) < 4 or s.jogos_comp < 1000:
                        continue
                    if id(s) in aprovados:
                        fortes.append((slot, s))
                    elif abs(s.z) >= 2.0:
                        fracos.append((slot, s))

            if not fortes and not fracos:
                print(f"\n  {GREEN}Veredito: mantenha a build padrão.{RESET}")
                print(f"  {DIM}Nenhum item rende de forma perceptível diferente "
                      f"contra essa composição.{RESET}")
            else:
                if fortes:
                    print(f"\n  {BOLD}Diferenças consistentes:{RESET}")
                    for slot, s in sorted(fortes, key=lambda x: -abs(x[1].z))[:4]:
                        verbo = "acima" if s.lift > 0 else "abaixo"
                        cor = GREEN if s.lift > 0 else RED
                        print(f"    {cor}{static.item(s.item_id)}{RESET} rendeu "
                              f"~{abs(s.lift):.0f} ponto(s) {verbo} do normal "
                              f"{DIM}({slot}, {num(s.jogos_comp)} jogos){RESET}")
                if fracos:
                    print(f"\n  {BOLD}Sinais fracos{RESET} "
                          f"{DIM}(pode ser sorte — não mudaria minha build por isso)"
                          f"{RESET}")
                    for slot, s in sorted(fracos, key=lambda x: -abs(x[1].z))[:3]:
                        verbo = "acima" if s.lift > 0 else "abaixo"
                        print(f"    {static.item(s.item_id)} rendeu "
                              f"~{abs(s.lift):.0f} ponto(s) {verbo} do normal "
                              f"{DIM}({slot}, {num(s.jogos_comp)} jogos){RESET}")
                print(f"\n  {DIM}Sem nada na primeira lista, a build padrão continua "
                      f"sendo a aposta certa.{RESET}")
            print(f"  {DIM}use --detalhe para ver os números por trás{RESET}")

    # A página final parte da mais usada e mantém a estrutura válida.
    pagina_final = recomendacao.runas.recomendado
    feiticos_final = recomendacao.feiticos.recomendado
    trocas = recomendacao.runas.trocas
    troca_sp = (recomendacao.feiticos.trocas[0]
                if recomendacao.feiticos.trocas else None)
    seq_itens = recomendacao.sequencia.recomendado
    trocas_itens = recomendacao.sequencia.trocas
    if seq_itens:
        head("Build montada para este draft")
        mexidos = {t.slot for t in trocas_itens}
        for slot, iid in seq_itens:
            marca = f"  {GREEN}<= trocado{RESET}" if slot in mexidos else ""
            print(f"  {slot:8s} {static.item(iid)}{marca}")
        for t in trocas_itens:
            verbo = "antecipar" if t.descido else "entra no lugar de"
            alvo_txt = "" if t.descido else f" {static.item(t.saiu)}"
            print(f"    {DIM}{t.slot}: {verbo}{alvo_txt} — "
                  f"{t.delta:+.2f}pp ±{t.erro:.2f} · {t.matchups} matchups · "
                  f"{num(t.jogos)} jogos{RESET}")
        if not trocas_itens:
            print(f"    {DIM}nenhuma troca passou no corte — "
                  f"a sequência mais escolhida é a recomendação{RESET}")

    if pagina_final is not None:
        head("Runas e feitiços para este draft")
        if trocas or troca_sp:
            for t in trocas:
                print(f"  {static.rune(t.saiu)} → {GREEN}{static.rune(t.entrou)}"
                      f"{RESET} {DIM}{t.delta:+.2f}pp ±{t.erro:.2f} · "
                      f"{t.matchups} matchups · {num(t.jogos)} jogos{RESET}")
            if troca_sp:
                nomes = " + ".join(static.spell(i) for i in troca_sp.ids)
                print(f"  feitiço → {GREEN}{nomes}{RESET} "
                      f"{DIM}{troca_sp.delta:+.2f}pp ±{troca_sp.erro:.2f} · "
                      f"{troca_sp.matchups} matchups · {num(troca_sp.jogos)} jogos"
                      f"{RESET}")
        else:
            print(f"  {DIM}nenhuma troca passou no corte "
                  f"(z ≥ {args.z_minimo}, {num(args.jogos_minimos)} jogos) — "
                  f"a página mais escolhida é a recomendação{RESET}")
    for decisao in (recomendacao.runas, recomendacao.feiticos,
                    recomendacao.sequencia):
        if decisao.estado is matchups.EstadoDecisao.ERRO and decisao.falha:
            print(f"  {YELLOW}{decisao.falha.resumo}{RESET}")

    if aplicacao is not None and any(
        estado != "nao_solicitada" for estado in aplicacao.estados.values()
    ):
        head("Aplicando no client")
        if aplicacao.pagina is not None:
            pg = aplicacao.pagina
            print(f"  runas: página {pg.acao} — {BOLD}{pg.nome}{RESET} "
                  f"{DIM}(id {pg.page_id}){RESET}")
        if aplicacao.ordem_feiticos is not None:
            ordem = aplicacao.ordem_feiticos
            print(f"  feitiços: {BOLD}D = {static.spell(ordem[0])}{RESET}, "
                  f"F = {static.spell(ordem[1])}")
        for falha in aplicacao.falhas:
            print(f"  {YELLOW}{falha.resumo}{RESET}")

    print(f"\n{DIM}fonte: {build.origem}{RESET}")
    # O aviso considera apenas tabelas visíveis.
    exibidas = [build.tables.get(s) or []
                for s in ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")]
    if any(r.games < MIN_SAMPLE for rows in exibidas for r in rows):
        print(f"{DIM}itens marcados como amostra baixa têm menos de "
              f"{num(MIN_SAMPLE)} jogos — trate como sugestão, não como dado.{RESET}")
    return None




"""Gera um relatório final sem depender de uma partida aberta."""

from advisor import config
from advisor.apresentacao import html
from advisor.data import ddragon
from advisor.data.fonte_lolalytics import FonteLolalytics
from advisor.domain.draft import Draft
from advisor.fluxos import execucao


def main() -> None:
    static = ddragon.load()
    champion = static.champion("Ashe")
    nomes = ("Aatrox", "Graves", "Anivia", "Lucian", "Bard")
    enemies = [static.champion(nome) for nome in nomes]
    if champion is None or any(enemy is None for enemy in enemies):
        raise RuntimeError("não consegui resolver os campeões da simulação")
    por_nome = dict(zip(nomes, enemies))
    draft = Draft(
        champion=champion, lane="bottom", enemies=enemies,
        opponent=por_nome["Lucian"],
    )
    cfg = config.carregar()
    cfg.pagina_base_elo = "platinum_plus"
    cfg.matchups_elo = "platinum_plus"
    cfg.referencia_elo = "master_plus"
    cfg.aplicar_runas = cfg.aplicar_feiticos = False
    cfg.html_abrir_automaticamente = False
    contexto = execucao.ContextoExecucao(
        cfg, static, fonte=FonteLolalytics())

    inicial = execucao.executar_draft(draft, contexto)
    confirmado = Draft(
        champion=champion, lane="bottom", enemies=enemies,
        allies=draft.allies, opponent=por_nome["Lucian"],
        rotas_inimigas={
            por_nome["Aatrox"].cid: "top",
            por_nome["Graves"].cid: "jungle",
            por_nome["Anivia"].cid: "middle",
            por_nome["Lucian"].cid: "bottom",
            por_nome["Bard"].cid: "support",
        },
        rotas_confirmadas=True,
    )
    final = execucao.recalcular_itens_confirmados(
        inicial, confirmado, contexto)
    caminho = html.gerar(final, contexto)
    print(caminho)
    adaptacao = final.adaptacao_elo_alto
    if adaptacao:
        print("estado:", adaptacao.estado, "elo:", adaptacao.elo)
        print("sequencia:", adaptacao.sequencia)
        print("testes:", adaptacao.hipoteses_avaliadas,
              "z:", adaptacao.passaram_z, "fdr:", adaptacao.sobreviveram_fdr)
        for acao in adaptacao.acoes:
            print("acao:", acao.tipo, acao.item_id,
                  acao.slot_destino, f"score={acao.score:+.3f}")
            for evidencia in acao.evidencias:
                print("  ", evidencia.inimigo, evidencia.direcao,
                      f"pick={evidencia.pick_base:.2f}->{evidencia.pick_matchup:.2f}",
                      f"z={evidencia.z:+.2f}",
                      f"contrib={evidencia.contribuicao:+.3f}")


if __name__ == "__main__":
    main()


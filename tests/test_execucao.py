from types import SimpleNamespace

from advisor import config
from advisor.data.ddragon import Champion
from advisor.domain import recomendador as R
from advisor.domain.draft import Draft
from advisor.domain import modelos as M
from advisor.fluxos import execucao
from advisor.fluxos.fontes import ColetaDoDraft, FalhaColeta


def _draft():
    ashe = Champion(22, "Ashe", "Ashe", "ashe")
    xerath = Champion(101, "Xerath", "Xerath", "xerath")
    return Draft(champion=ashe, lane="bottom", enemies=[xerath],
                 opponent=xerath)


def _recomendacao(build):
    vazio = R.Decisao(R.EstadoDecisao.FALTA_DADOS, None, None)
    return R.RecomendacaoDoDraft(
        vazio, vazio, vazio,
        R.Recorte("platinum", "patch_atual"),
        R.Recorte("platinum", "30 dias"),
    )


def test_falha_de_matchup_produz_resultado_parcial():
    build = M.DadosDeBuild(origem="base")

    class FonteEmMemoria:
        def coletar_draft(self, *args, **kwargs):
            return ColetaDoDraft(
                build, falhas=(FalhaColeta(
                    "matchups", "não consegui buscar matchups", "sem página"),))

    cfg = config.Config(
        pagina_base_elo="platinum", matchups_elo="platinum",
        referencia_elo="platinum")
    static = SimpleNamespace(itens_finais=set())

    resultado = execucao.executar_draft(
        _draft(), execucao.ContextoExecucao(
            cfg, static, fonte=FonteEmMemoria()))

    assert resultado.pagina_base is build
    assert resultado.paginas_do_draft is None
    assert resultado.falhas[0].etapa == "matchups"


def test_falha_ao_aplicar_runas_nao_impede_feiticos(monkeypatch):
    pagina = M.PaginaRunas([8005, 1, 2, 3], [4, 5], [5005, 5008, 5001], 50, 10)
    runas = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA, pagina, pagina)
    feiticos = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA, (4, 7), (4, 7))
    itens = R.Decisao(R.EstadoDecisao.FALTA_DADOS, None, None)
    rec = R.RecomendacaoDoDraft(
        runas, feiticos, itens,
        R.Recorte("platinum", "patch_atual"),
        R.Recorte("platinum", "30 dias"))
    resultado = execucao.ResultadoDoDraft(
        _draft(), M.DadosDeBuild(origem="base"), None, rec)
    monkeypatch.setattr(execucao.perks, "aplicar", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("runas falharam")))
    chamados = []
    monkeypatch.setattr(execucao.perks, "aplicar_feiticos",
                        lambda *a, **k: chamados.append(True) or [4, 7])
    contexto = execucao.ContextoExecucao(
        config.Config(pagina_base_elo="platinum", matchups_elo="platinum"),
        SimpleNamespace(), object())

    aplicado = execucao.aplicar_recomendacao(resultado, contexto)

    assert aplicado.estados["runas"] == "erro"
    assert aplicado.estados["feiticos"] == "aplicados"
    assert chamados == [True]


def test_recalculo_confirmado_substitui_apenas_itens(monkeypatch):
    build = M.DadosDeBuild(origem="base")
    anterior = _recomendacao(build)
    runas_anteriores = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA, "runas", "runas")
    feiticos_anteriores = R.Decisao(
        R.EstadoDecisao.SEM_EVIDENCIA, (4, 21), (4, 21))
    itens_anteriores = R.Decisao(
        R.EstadoDecisao.SEM_EVIDENCIA, (("Item 1", 1),), (("Item 1", 1),))
    rec_anterior = R.RecomendacaoDoDraft(
        runas_anteriores, feiticos_anteriores, itens_anteriores,
        anterior.recorte_pagina_base, anterior.recorte_matchups)
    resultado = execucao.ResultadoDoDraft(
        _draft(), build, None, rec_anterior)
    confirmado = _draft()
    confirmado.rotas_confirmadas = True
    confirmado.rotas_inimigas = {confirmado.enemies[0].cid: "bottom"}
    class Fonte:
        def coletar_paginas(self, *args, **kwargs):
            return M.PaginasDoDraft()

    contexto = execucao.ContextoExecucao(
        config.Config(pagina_base_elo="platinum", matchups_elo="platinum"),
        SimpleNamespace(), fonte=Fonte())
    final = execucao.recalcular_itens_confirmados(
        resultado, confirmado, contexto)

    assert final.recomendacao.runas is runas_anteriores
    assert final.recomendacao.feiticos is feiticos_anteriores
    assert final.recomendacao is rec_anterior
    assert final.draft.rotas_confirmadas is True


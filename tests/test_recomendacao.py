from types import SimpleNamespace

from advisor.domain import recomendador as R
from advisor.domain import modelos as M


def entrada(build, paginas=None):
    return R.EntradaRecomendacao(
        pagina_base=build,
        paginas_do_draft=paginas,
        dados_estaticos=SimpleNamespace(itens_finais=set()),
        criterios=R.CriteriosRecomendacao(2.0, 500),
        recorte_pagina_base=R.Recorte("platinum", "patch_atual"),
        recorte_matchups=R.Recorte("platinum", "30 dias"),
    )


def build_base():
    menos_usada = M.PaginaRunas([8005], [8304], [5005], 55.0, 100)
    mais_usada = M.PaginaRunas([8008], [8304], [5005], 51.0, 1000)
    return M.DadosDeBuild(
        origem="teste",
        tables={"Botas": [M.Item(3006, 52.0, 60.0, 500, 12)]},
        rune_pages=[menos_usada, mais_usada],
        rune_stats={
            8005: M.EstatisticaRuna(8005, 4.0, 55.0, 100),
            8008: M.EstatisticaRuna(8008, 60.0, 51.0, 1000),
        },
        spells=[M.Feiticos([4, 7], 51.0, 1000, 60.0)],
    )


def test_pagina_base_e_derivada_por_adesao_e_nao_indice():
    recomendacao = R.recomendar(entrada(build_base()))
    assert recomendacao.runas.base.primary == [8008]
    assert recomendacao.runas.estado is R.EstadoDecisao.FALTA_DADOS
    assert recomendacao.feiticos.recomendado == (4, 7)


def test_erro_em_runas_nao_apaga_feiticos_ou_sequencia():
    enemy = M.Champion(1, "Annie", "Annie", "annie")
    matchup_build = M.DadosDeBuild(
        spells=[M.Feiticos([4, 7], 55.0, 500, 60.0)],
        tables={"Botas": [M.Item(3006, 52.0, 60.0, 500, 12)]},
        rune_stats={
            8005: M.EstatisticaRuna(8005, 40.0, 55.0, 500),
            8008: M.EstatisticaRuna(8008, 60.0, 51.0, 500),
        },
    )
    paginas = M.PaginasDoDraft(
        paginas=[M.PaginaMatchup(enemy, matchup_build, 1.0)],
    )

    class StaticComErroRuna:
        itens_finais = {3006}

        def vaga_da_runa(self, rid):
            raise RuntimeError("quebrou runas")

    ent = R.EntradaRecomendacao(
        pagina_base=build_base(),
        paginas_do_draft=paginas,
        dados_estaticos=StaticComErroRuna(),
        criterios=R.CriteriosRecomendacao(2.0, 500),
        recorte_pagina_base=R.Recorte("platinum", "patch_atual"),
        recorte_matchups=R.Recorte("platinum", "30 dias"),
    )

    recomendacao = R.recomendar(ent)

    assert recomendacao.runas.estado is R.EstadoDecisao.ERRO
    assert recomendacao.feiticos.estado is R.EstadoDecisao.SEM_EVIDENCIA
    assert recomendacao.sequencia.recomendado == (("Botas", 3006),)


def test_recomendar_usa_build_popular_como_base_dos_itens():
    recomendacao = R.recomendar(entrada(build_base()))
    assert recomendacao.sequencia.recomendado == (("Botas", 3006),)


from advisor.domain import modelos as M
from advisor.domain import transferencias as T


def _build(candidato, ocupante):
    return M.DadosDeBuild(games=10_000, tables={
        "Item 1": [
            M.Item(1, 50, ocupante / 100, ocupante, 12),
            M.Item(2, 50, candidato / 100, candidato, 12),
        ]})


def _sem_contracao(hipoteses, criterios):
    return ([T.replace(
        h, efeito_posterior=h.delta, erro_posterior=h.erro,
        z_posterior=h.z, p_posterior=h.p_valor,
        limite_posterior=h.limite_inferior, contracao=0.0)
             for h in hipoteses], {})


def test_combina_sinais_antes_do_corte_e_transfere_ocupante(monkeypatch):
    monkeypatch.setattr(T, "_regularizar", _sem_contracao)
    inimigos = [M.Champion(i, str(i), f"Inimigo {i}", str(i)) for i in range(3)]
    paginas = M.PaginasDoDraft(
        base=_build(1_000, 8_000),
        paginas=[
            M.PaginaMatchup(inimigos[0], _build(3_000, 6_000), 1),
            M.PaginaMatchup(inimigos[1], _build(2_800, 6_200), 1),
            M.PaginaMatchup(inimigos[2], _build(900, 8_100), 1),
        ])

    resultado = T.analisar(
        paginas, elo="master_plus", criterios=T.Criterios(2, .10, 1),
        validos={1, 2}, total_inimigos=3)

    hipotese = next(h for h in resultado.hipoteses
                     if h.tipo == "slot" and h.candidato == 2)
    assert hipotese.parcelas[2].delta < 0  # o sinal contrário não virou zero
    assert hipotese.delta > 0
    assert hipotese.passou_fdr
    assert resultado.modificacoes[0].tipo == "substituicao"
    assert resultado.sequencia == (("Item 1", 2),)


def test_duas_paginas_mostram_alternativa_sem_alterar_sequencia(monkeypatch):
    monkeypatch.setattr(T, "_regularizar", _sem_contracao)
    inimigos = [M.Champion(i, str(i), f"Inimigo {i}", str(i)) for i in range(2)]
    paginas = M.PaginasDoDraft(
        base=_build(1_000, 8_000),
        paginas=[M.PaginaMatchup(c, _build(4_000, 5_000), 1)
                 for c in inimigos])

    resultado = T.analisar(
        paginas, elo="platinum_plus", criterios=T.Criterios(2, .10, 1),
        validos={1, 2}, total_inimigos=5,
        excluidos=("A", "B", "C"))

    assert resultado.pode_alterar is False
    assert resultado.sequencia == resultado.sequencia_base
    assert resultado.alternativas


def test_aplica_somente_a_transferencia_de_botas_mais_forte():
    inimigos = [M.Champion(i, str(i), f"Inimigo {i}", str(i)) for i in range(3)]
    base = M.DadosDeBuild(games=10_000, tables={"Botas": [
        M.Item(10, 50, 80, 8_000, 10), M.Item(11, 50, 10, 1_000, 10),
        M.Item(12, 50, 5, 500, 10)]})
    versus = M.DadosDeBuild(games=10_000, tables={"Botas": [
        M.Item(10, 50, 40, 4_000, 10), M.Item(11, 50, 35, 3_500, 10),
        M.Item(12, 50, 20, 2_000, 10)]})
    paginas = M.PaginasDoDraft(
        base=base, paginas=[M.PaginaMatchup(c, versus, 1) for c in inimigos])

    resultado = T.analisar(
        paginas, elo="master_plus", criterios=T.Criterios(2, .10, 1),
        validos={10, 11, 12}, total_inimigos=3)

    botas = [m for m in resultado.modificacoes if m.slot_destino == "Botas"]
    assert len(botas) == 1
    assert dict(resultado.sequencia)["Botas"] == botas[0].candidato
    assert not resultado.invariantes


def test_candidato_omitido_em_matchup_nao_vira_sinal_por_pseudocontagem():
    enemy = M.Champion(1, "Enemy", "Inimigo", "enemy")
    base = M.DadosDeBuild(tables={"Item 1": [
        M.Item(1, 50, 80, 8_000, 10), M.Item(2, 50, .1, 10, 10)]})
    versus = M.DadosDeBuild(tables={"Item 1": [
        M.Item(1, 50, 70, 700, 10), M.Item(3, 50, 1, 10, 10)]})
    paginas = M.PaginasDoDraft(
        base=base, paginas=[M.PaginaMatchup(enemy, versus, 1)])

    hipotese = T._transferencia(
        paginas, "Item 1", 2, 1, T.Criterios(2, .10, 1))

    assert hipotese.p_valor == 1
    assert hipotese.passou_z is False
    assert hipotese.limite_inferior == float("-inf")


def test_bottom_recebe_sexto_item_estimado_sem_duplicar():
    def build():
        tabelas = {"Botas": [M.Item(3006, 50, 80, 8_000, 10)]}
        for indice in range(1, 6):
            tabelas[f"Item {indice}"] = [
                M.Item(1000 + indice, 50, 70, 7_000, 10 + indice),
                M.Item(2000 + indice, 50, 10, 1_000, 10 + indice),
            ]
        tabelas["Item 5"].append(M.Item(9999, 50, 5, 500, 20))
        return M.DadosDeBuild(games=10_000, tables=tabelas)

    enemies = [M.Champion(i, str(i), f"Inimigo {i}", str(i)) for i in range(3)]
    paginas = M.PaginasDoDraft(
        base=build(), paginas=[M.PaginaMatchup(c, build(), 1) for c in enemies])

    resultado = T.analisar(
        paginas, elo="master_plus", criterios=T.Criterios(),
        validos={3006, 1001, 1002, 1003, 1004, 1005,
                 2001, 2002, 2003, 2004, 2005, 9999},
        total_inimigos=3, lane="bottom")

    assert len(resultado.sequencia_base) == 7
    assert resultado.sequencia_base[-1] == ("Item 6", 2005)
    assert len({iid for _, iid in resultado.sequencia_base}) == 7
    assert resultado.item6_proxy is True
    assert not resultado.invariantes


def _hipotese(slot, candidato, ocupante, efeito, erro):
    z = efeito / erro
    parcela = T.Parcela("Inimigo", 1.0, efeito, erro, 20, 10, False)
    return T.Hipotese(
        "slot", slot, candidato, ocupante, efeito, erro, z, .01,
        efeito - 1.5 * erro, True, parcelas=(parcela,), familia=slot,
        efeito_posterior=efeito, erro_posterior=erro,
        z_posterior=z, p_posterior=.01,
        limite_posterior=efeito - 1.5 * erro, contracao=.1)


def _resultado_otimizacao(*hipoteses, base=None):
    base = base or tuple((f"Item {i}", i) for i in range(1, 7))
    return T.Resultado(
        elo="emerald_plus", cobertura=5, total_inimigos=5,
        excluidos=(), cobertura_critica=(), sequencia_base=base,
        sequencia=base, hipoteses=tuple(hipoteses), modificacoes=(),
        alternativas=(), pode_alterar=True)


def test_otimizador_aplica_multiplas_entradas_sem_desfazer_a_anterior():
    resultado = _resultado_otimizacao(
        _hipotese("Item 1", 91, 1, .40, .10),
        _hipotese("Item 2", 92, 2, .35, .10),
    )

    plano = T.otimizar_sequencias(resultado)

    assert plano.principal is not None
    assert dict(plano.principal.sequencia)["Item 1"] == 91
    assert dict(plano.principal.sequencia)["Item 2"] == 92
    assert len(plano.principal.acoes) == 2
    assert len({iid for _, iid in plano.principal.sequencia}) == 6


def test_otimizador_resolve_conflito_dominik_lembrete_removendo_o_outro():
    base = (("Item 1", 1), ("Item 2", 2), ("Item 3", 3),
            ("Item 4", 3036), ("Item 5", 5), ("Item 6", 6))
    resultado = _resultado_otimizacao(
        _hipotese("Item 4", 3033, 3036, .50, .10), base=base)

    plano = T.otimizar_sequencias(resultado)

    assert plano.principal is not None
    ids = {iid for _, iid in plano.principal.sequencia}
    assert 3033 in ids
    assert 3036 not in ids


def test_sinal_entre_cortes_aparece_somente_como_alternativa_completa():
    resultado = _resultado_otimizacao(
        _hipotese("Item 1", 77, 1, .155, .10))

    plano = T.otimizar_sequencias(resultado)

    assert plano.principal is None
    assert len(plano.alternativas) == 1
    assert dict(plano.alternativas[0].sequencia)["Item 1"] == 77


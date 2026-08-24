from types import SimpleNamespace

from advisor import config
from advisor.domain import adaptacao as A
from advisor.domain import modelos as M
from advisor.fluxos import adaptacao_elo_alto


def _build(games=10_000):
    return M.DadosDeBuild(games=games, tables={
        "Botas": [M.Item(3006, 50, 80, 8_000, 10)],
        "Item 1": [M.Item(1001, 50, 80, 8_000, 12)],
    })


def _paginas(games=10_000):
    enemy = M.Champion(1, "Enemy", "Inimigo", "enemy")
    return M.PaginasDoDraft(
        base=_build(),
        paginas=[M.PaginaMatchup(enemy, _build(games), 1.0)],
        tier="emerald_plus")


def test_sem_sinal_mantem_build_base_exatamente():
    resultado = A.calcular(
        _paginas(), elo="emerald_plus",
        criterios=A.CriteriosAdaptacao(),
        validos={1001, 3006})

    assert resultado.estado == A.EstadoAdaptacao.SEM_ADAPTACAO
    assert resultado.sequencia == resultado.sequencia_base
    assert resultado.acoes == ()


def test_fluxo_consulta_somente_recorte_configurado():
    chamadas = []

    class Fonte:
        def coletar_paginas(self, draft, *, elo, **kwargs):
            chamadas.append(elo)
            return _paginas()

    cfg = config.Config(
        adaptacao_elos=("emerald_plus",),
        adaptacao_jogos_totais_minimos=100,
        adaptacao_jogos_por_matchup_minimos=100)
    draft = SimpleNamespace(enemies=[object()], lane="bottom")
    catalogo = SimpleNamespace(itens_finais={1001, 3006})

    resultado = adaptacao_elo_alto.executar(draft, Fonte(), catalogo, cfg)

    assert chamadas == ["emerald_plus"]
    assert resultado.elo == "emerald_plus"
    assert resultado.elos_tentados == ("emerald_plus",)


def test_recorte_sem_volume_nao_desce_de_elo():
    chamadas = []

    class Fonte:
        def coletar_paginas(self, draft, *, elo, **kwargs):
            chamadas.append(elo)
            return _paginas(50)

    cfg = config.Config(
        adaptacao_elos=("emerald_plus",),
        adaptacao_jogos_totais_minimos=100,
        adaptacao_jogos_por_matchup_minimos=100)
    draft = SimpleNamespace(enemies=[object()], lane="bottom")
    catalogo = SimpleNamespace(itens_finais={1001, 3006})

    resultado = adaptacao_elo_alto.executar(draft, Fonte(), catalogo, cfg)

    assert chamadas == ["emerald_plus"]
    assert resultado.estado == A.EstadoAdaptacao.DADOS_INSUFICIENTES
    assert resultado.sequencia == resultado.sequencia_base
    assert resultado.sequencia


def test_config_carrega_criterios_da_adaptacao(tmp_path):
    caminho = tmp_path / "config.toml"
    caminho.write_text('''[adaptacao_elo_alto]
habilitada = false
elos = ["emerald_plus"]
janela_dias = 45
jogos_totais_minimos = 6000
jogos_por_matchup_minimos = 150
z_principal = 1.70
z_alternativa = 1.55
corrigir_multiplos_itens = true
fdr_botas = 0.05
deflator_sobreposicao = 1.3
max_alternativas = 2
''', encoding="utf-8")
    cfg = config.carregar(caminho)

    assert cfg.adaptacao_habilitada is False
    assert cfg.adaptacao_elos == ("emerald_plus",)
    assert cfg.adaptacao_janela_dias == "45"
    assert cfg.adaptacao_jogos_totais_minimos == 6000
    assert cfg.adaptacao_jogos_por_matchup_minimos == 150
    assert cfg.adaptacao_z_principal == 1.70
    assert cfg.adaptacao_z_alternativa == 1.55
    assert cfg.adaptacao_corrigir_multiplos_itens is True
    assert cfg.adaptacao_fdr_botas == .05
    assert cfg.adaptacao_deflator_sobreposicao == 1.3
    assert cfg.adaptacao_max_alternativas == 2


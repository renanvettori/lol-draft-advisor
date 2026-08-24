"""Testa a coleta das páginas de matchup sem acessar a rede."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from advisor.data import ddragon, lolalytics as L, paginas  # noqa: E402
from advisor.config import Config  # noqa: E402
from advisor.domain.draft import Draft  # noqa: E402

static = ddragon.load()

ASHE = static.champion("ashe")
CAITLYN = static.champion("caitlyn")   # bottom — oponente direto
LEONA = static.champion("leona")       # support
VIEGO = static.champion("viego")       # jungle
HWEI = static.champion("hwei")         # middle
KSANTE = static.champion("ksante")     # top

ROTAS_PADRAO = {
    CAITLYN.cid: "bottom", LEONA.cid: "support", VIEGO.cid: "jungle",
    HWEI.cid: "middle", KSANTE.cid: "top",
}
PESOS = Config().relevancia


def _carregar(*args, **kwargs):
    kwargs.setdefault("pesos", PESOS)
    return paginas.carregar(*args, **kwargs)


def _build(*, com_itens=True, com_feiticos=True, com_runas=True) -> L.Build:
    """Uma página de matchup sintética, mínima mas com a forma certa."""
    b = L.Build(url="fake://vs")
    if com_itens:
        b.tables["Item 1"] = [L.ItemRow(3031, 52.0, 40.0, 5000, 12)]
        b.tables["Botas"] = [L.ItemRow(3006, 51.0, 80.0, 9000, 11)]
    if com_feiticos:
        b.spells = [L.SpellChoice(ids=[4, 21], wr=51.0, games=8000, pr=60.0)]
    if com_runas:
        b.rune_stats = {8008: L.RuneStat(8008, 55.0, 52.0, 4000)}
        b.rune_pages = [L.RunePage(primary=[8008], secondary=[8226],
                                   mods=[5005], wr=51.0, games=8000)]
    return b


class FonteFalsa:
    """Substitui o módulo lolalytics: registra o que foi pedido e devolve páginas."""

    def __init__(self, paginas_por_inimigo=None, quebrar=()):
        self.chamadas = []
        self.paginas_por_inimigo = paginas_por_inimigo or {}
        self.quebrar = set(quebrar)

    def get_counters(self, champion):
        return {cid: L.Matchup(cid=cid, vs_wr=50.0, delta=0.0, games=1000, lane=rota)
                for cid, rota in ROTAS_PADRAO.items()}

    def get_build(self, champion, **kwargs):
        self.chamadas.append(kwargs)
        versus = kwargs.get("versus")
        if versus in self.quebrar:
            raise L.LolalyticsError(f"página não existe: {versus}")
        if versus is None:
            return _build()
        return self.paginas_por_inimigo.get(versus, _build())

    # Como o vslane foi pedido para cada inimigo.
    def vslane_de(self, slug):
        for c in self.chamadas:
            if c.get("versus") == slug:
                return c.get("vs_lane")
        raise AssertionError(f"nunca buscou {slug}")


def _draft(opponent=CAITLYN):
    return Draft(champion=ASHE, lane="bottom",
                 enemies=[CAITLYN, LEONA, VIEGO, HWEI, KSANTE],
                 opponent=opponent)


def test_vslane_e_a_rota_do_inimigo():
    """O erro que enterrou a soma dos matchups: vslane com a SUA rota."""
    fonte = FonteFalsa()
    _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)

    # O oponente direto divide a sua rota — ali as duas coincidem.
    assert fonte.vslane_de("caitlyn") == "bottom"
    # Os outros quatro vão com a rota DELES. Se algum vier "bottom", a regra
    # voltou a estar errada.
    assert fonte.vslane_de("leona") == "support"
    assert fonte.vslane_de("viego") == "jungle"
    assert fonte.vslane_de("hwei") == "middle"
    assert fonte.vslane_de("ksante") == "top"


def test_rotas_confirmadas_substituem_a_inferencia_dos_counters():
    """Na tela de carregamento, a posição oficial é a única autoridade."""
    d = _draft()
    d.rotas_inimigas = {
        CAITLYN.cid: "middle", LEONA.cid: "support", VIEGO.cid: "jungle",
        HWEI.cid: "bottom", KSANTE.cid: "top",
    }
    d.rotas_confirmadas = True
    d.opponent = HWEI
    fonte = FonteFalsa()
    fonte.get_counters = lambda *_: (_ for _ in ()).throw(
        AssertionError("não deve consultar counters com rotas confirmadas"))

    p = _carregar(d, static, tier="emerald_plus", fonte=fonte)

    assert fonte.vslane_de("hwei") == "bottom"
    assert fonte.vslane_de("caitlyn") == "middle"
    assert p.peso(HWEI.cid) == PESOS["oponente_de_rota"]
    assert p.peso(LEONA.cid) == PESOS["mesma_rota"]


def test_sua_rota_vai_no_lane_de_todas():
    """`lane` é sempre a sua; só o `vslane` muda por inimigo."""
    fonte = FonteFalsa()
    _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    assert all(c["lane"] == "bottom" for c in fonte.chamadas)


def test_oponente_e_deduzido_antes_de_buscar():
    """Infere o oponente antes de montar URLs e pesos."""
    p = _carregar(_draft(opponent=None), static, tier="emerald_plus",
                         fonte=FonteFalsa())
    assert p.opponent is not None and p.opponent.cid == CAITLYN.cid
    assert p.opponent_inferido is True
    assert "seu oponente direto de rota" in p.relevancias[CAITLYN.cid][1]
    assert p.peso(CAITLYN.cid) > p.peso(HWEI.cid)


def test_suporte_pesa_tambem_o_adc_inimigo():
    """Suporte divide a rota com o ADC, não apenas com o suporte rival."""
    d = _draft(opponent=LEONA)
    d.lane = "support"
    p = _carregar(d, static, tier="emerald_plus", fonte=FonteFalsa())

    assert p.peso(LEONA.cid) == PESOS["oponente_de_rota"]
    assert p.peso(CAITLYN.cid) == PESOS["mesma_rota"]
    assert p.peso(CAITLYN.cid) > p.peso(VIEGO.cid)
    assert any("ADC inimigo" in motivo
               for motivo in p.relevancias[CAITLYN.cid][1])


def test_deducao_ambigua_nao_chuta():
    """Dois inimigos com a mesma rota padrão: melhor não responder."""
    fonte = FonteFalsa()
    fonte.get_counters = lambda champion: {
        CAITLYN.cid: L.Matchup(CAITLYN.cid, 50.0, 0.0, 1000, "bottom"),
        LEONA.cid: L.Matchup(LEONA.cid, 50.0, 0.0, 1000, "bottom"),
        VIEGO.cid: L.Matchup(VIEGO.cid, 50.0, 0.0, 1000, "jungle"),
        HWEI.cid: L.Matchup(HWEI.cid, 50.0, 0.0, 1000, "middle"),
        KSANTE.cid: L.Matchup(KSANTE.cid, 50.0, 0.0, 1000, "top"),
    }
    p = _carregar(_draft(opponent=None), static, tier="emerald_plus",
                         fonte=fonte)
    assert p.opponent is None
    assert p.opponent_inferido is False


def test_vs_explicito_nao_e_marcado_como_inferido():
    """Quando o oponente veio de fora, não há dedução a anunciar."""
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=FonteFalsa())
    assert p.opponent.cid == CAITLYN.cid
    assert p.opponent_inferido is False


def test_sem_rota_nao_deduz():
    """Fila sem posição atribuída: não dá para saber quem divide a sua rota."""
    d = Draft(champion=ASHE, lane="", enemies=[CAITLYN, VIEGO], opponent=None)
    fonte = FonteFalsa()
    p = _carregar(d, static, tier="emerald_plus", fonte=fonte)
    assert p.opponent is None
    assert fonte.vslane_de("caitlyn") == "bottom"  # a rota padrão dela, não a sua
    assert all(c["lane"] is None for c in fonte.chamadas)


def test_uma_busca_por_inimigo():
    """Cinco inimigos, cinco páginas de matchup, mais a base. Nada repetido."""
    fonte = FonteFalsa()
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    versus = [c.get("versus") for c in fonte.chamadas]
    assert versus.count(None) == 1, "a página base deve ser buscada uma vez"
    assert len(versus) == 6, versus
    assert len(p.paginas) == 5


def test_busca_que_falha_vira_ausente():
    fonte = FonteFalsa(quebrar={"hwei"})
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    assert [c.name for c in p.ausentes] == ["Hwei"]
    assert len(p.usados) == 4


def test_pagina_sem_item_nao_e_ausente():
    """Página baixada mas sem tabela de item some da consulta, não da lista.

    São duas causas diferentes: "não consegui buscar" e "veio sem esse dado".
    Antes as duas se confundiam na mesma linha de aviso.
    """
    fonte = FonteFalsa(paginas_por_inimigo={"leona": _build(com_itens=False)})
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    assert p.ausentes == []
    assert len(p.usados) == 5
    # Some da consulta de item...
    assert all(o.enemy.cid != LEONA.cid for o in p.linhas("Item 1")[3031])
    # ...mas continua contando para feitiço.
    assert LEONA.cid in {e.cid for e, _, _ in p.feiticos()}


def test_pesos_usam_somente_proximidade():
    """Traços do campeão não contam duas vezes o efeito presente no matchup."""
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=FonteFalsa())
    assert p.peso(CAITLYN.cid) == PESOS["oponente_de_rota"]
    assert p.peso(VIEGO.cid) == PESOS["outra_rota"]
    assert p.peso(LEONA.cid) == PESOS["mesma_rota"]


def test_pesos_do_config_sao_respeitados():
    """O bug que motivou tudo: pesos do config chegando só em metade das seções."""
    fonte = FonteFalsa()
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte,
                         pesos={"oponente_de_rota": 99.0, "mesma_rota": 2.0,
                                "outra_rota": 1.0})
    assert p.peso(CAITLYN.cid) >= 99.0
    assert p.paginas[0].peso == p.peso(CAITLYN.cid)


def test_peso_total_conta_quem_poderia_ter_o_item():
    """Item ausente de uma página é escolha de zero ali, não dado faltante."""
    fonte = FonteFalsa(paginas_por_inimigo={"leona": _build(com_itens=False)})
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    total = p.peso_total("Item 1")
    assert abs(total - sum(p.peso(c.cid) for c in [CAITLYN, VIEGO, HWEI, KSANTE])) < 1e-9


def test_counters_indisponivel_nao_derruba():
    """Sem counters, a rota do inimigo fica em aberto — pior, mas não impede."""
    class SemCounters(FonteFalsa):
        def get_counters(self, champion):
            raise L.LolalyticsError("caiu")

    fonte = SemCounters()
    p = _carregar(_draft(), static, tier="emerald_plus", fonte=fonte)
    assert len(p.usados) == 5
    assert fonte.vslane_de("viego") is None
    # O oponente direto continua sendo filtrado pela rota compartilhada.
    assert fonte.vslane_de("caitlyn") == "bottom"


if __name__ == "__main__":
    falhas = 0
    for nome, func in sorted(globals().items()):
        if nome.startswith("test_"):
            try:
                func()
                print(f"OK   {nome}")
            except AssertionError as exc:
                falhas += 1
                # A linha que falhou vale mais que a mensagem: quase toda
                # asserção aqui é auto-explicativa e não carrega texto.
                import traceback
                quadro = traceback.extract_tb(exc.__traceback__)[-1]
                print(f"FALHOU {nome} (linha {quadro.lineno}): {quadro.line}")
    raise SystemExit(1 if falhas else 0)


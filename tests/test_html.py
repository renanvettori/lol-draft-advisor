from advisor import config
from advisor.apresentacao import html
from advisor.data.ddragon import Static
from advisor.domain import modelos as M
from advisor.domain import recomendador as R
from advisor.domain.draft import Draft
from advisor.fluxos import execucao


class Catalogo:
    def rune(self, rid):
        return {8005: "Ritmo Fatal", 9111: "Triunfo", 5005: "Ataque"}.get(rid, f"Runa {rid}")

    def spell(self, sid):
        return {4: "Flash", 7: "Curar"}.get(sid, f"Feitiço {sid}")

    def item(self, iid):
        return {3006: "Grevas", 3031: "Gume do Infinito"}.get(iid, f"Item {iid}")

    def item_icon(self, iid):
        return f"https://assets.test/item/{iid}.png"

    def rune_icon(self, rid):
        return f"https://assets.test/rune/{rid}.png"

    def spell_icon(self, sid):
        return f"https://assets.test/spell/{sid}.png"

    def champion_icon(self, key):
        return f"https://assets.test/champion/{key}.png"

    def champion_splash(self, key):
        return f"https://assets.test/splash/{key}.jpg"


def _resultado():
    ashe = M.Champion(22, "Ashe", "Ashe <ADC>", "ashe")
    xerath = M.Champion(101, "Xerath", "Xerath", "xerath")
    draft = Draft(champion=ashe, lane="bottom", enemies=[xerath],
                  opponent=xerath)
    pagina = M.PaginaRunas([8005, 9111], [], [5005], 51, 1000)
    runas = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA, pagina, pagina)
    feiticos = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA, (4, 7), (4, 7))
    itens = R.Decisao(R.EstadoDecisao.SEM_EVIDENCIA,
                      (("Botas", 3006), ("Item 1", 3031)),
                      (("Botas", 3006), ("Item 1", 3031)))
    rec = R.RecomendacaoDoDraft(
        runas, feiticos, itens, R.Recorte("platinum", "patch_atual"),
        R.Recorte("platinum", "30 dias"))
    return execucao.ResultadoDoDraft(draft, M.DadosDeBuild(), None, rec)


def test_gera_html_autocontido_e_escapa_conteudo(tmp_path):
    cfg = config.Config(html_pasta=str(tmp_path))
    contexto = execucao.ContextoExecucao(cfg, Catalogo())
    aplicacao = execucao.ResultadoAplicacao(
        {"runas": "atualizadas", "feiticos": "aplicados"},
        ordem_feiticos=(4, 7))

    caminho = html.gerar(_resultado(), contexto, aplicacao)
    conteudo = caminho.read_text(encoding="utf-8")

    assert caminho == tmp_path / "ultima-recomendacao.html"
    assert "Ashe &lt;ADC&gt;" in conteudo
    assert "Ritmo Fatal" in conteudo
    assert "Gume do Infinito" in conteudo
    assert "<kbd>D</kbd>" in conteudo and "Flash" in conteudo
    assert "https://assets.test/item/3031.png" in conteudo
    assert "https://assets.test/splash/Ashe.jpg" in conteudo
    assert "Como o advisor decidiu" in conteudo
    assert "Corte de runas e feitiços" in conteudo
    assert "Build popular adaptada ao draft" in conteudo
    assert "Associação de win rate" not in conteudo
    assert "Build popular adaptada ao draft · Emerald+" in conteudo


def test_configura_saida_html(tmp_path):
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("""
[html]
habilitado = false
abrir_automaticamente = false
pasta = "meus-relatorios"
""", encoding="utf-8")

    cfg = config.carregar(arquivo)

    assert cfg.html_habilitado is False
    assert cfg.html_abrir_automaticamente is False
    assert cfg.html_pasta == "meus-relatorios"


def test_fragmentos_usam_diretorio_estatico_do_data_dragon():
    static = Static("16.9.1")

    assert static.rune_icon(5005).endswith("/StatModsAttackSpeedIcon.png")
    assert static.rune_icon(5008).endswith("/StatModsAdaptiveForceIcon.png")
    assert static.rune_icon(5001).endswith("/StatModsHealthScalingIcon.png")


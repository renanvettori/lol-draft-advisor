from advisor import config


def test_recortes_explicitos_substituem_as_chaves_antigas(tmp_path):
    arquivo = tmp_path / "config.toml"
    arquivo.write_text("""
[pagina_base]
elo = "gold"
janela = "patch_atual"
referencia_elo = "master_plus"
[matchups]
elo = "platinum"
janela_dias = 45
[analise_estatistica]
habilitada = true
elo = "all"
janela_dias = 60
[dados]
tier = "iron"
dias = 7
""", encoding="utf-8")

    cfg = config.carregar(arquivo)

    assert cfg.pagina_base_elo == "gold"
    assert cfg.matchups_elo == "platinum"
    assert cfg.matchups_janela_dias == "45"
    assert cfg.analise_habilitada is True
    assert cfg.analise_janela_dias == "60"


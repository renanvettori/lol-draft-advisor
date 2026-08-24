"""Carrega o config.toml e aplica opções da linha de comando."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CAMINHO = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass
class Config:
    # recortes
    pagina_base_elo: str = "meu_elo"
    pagina_base_janela: str = "patch_atual"
    referencia_elo: str = "master_plus"
    matchups_elo: str = "meu_elo"
    matchups_janela_dias: str = "30"
    analise_habilitada: bool = False
    analise_elo: str = "all"
    analise_janela_dias: str = "30"
    # exibição
    itens: int = 3
    ordenar_por: str = "pick"
    min_jogos: int = 300
    detalhe: bool = False
    todos_os_itens: bool = False
    # relatório HTML final
    html_habilitado: bool = True
    html_abrir_automaticamente: bool = True
    html_pasta: str = "relatorios"
    # client
    aplicar_runas: bool = True
    pagina_runas: int = 0
    aplicar_feiticos: bool = True
    flash_no_d: bool = True
    # trocas
    z_minimo: float = 2.0
    jogos_minimos: int = 500
    # adaptação por escolhas de elo alto
    adaptacao_habilitada: bool = True
    adaptacao_elos: tuple[str, ...] = ("emerald_plus",)
    adaptacao_janela_dias: str = "30"
    adaptacao_jogos_totais_minimos: int = 5000
    adaptacao_jogos_por_matchup_minimos: int = 100
    adaptacao_z_principal: float = 1.65
    adaptacao_z_alternativa: float = 1.50
    adaptacao_corrigir_multiplos_itens: bool = False
    adaptacao_fdr_botas: float = 0.10
    adaptacao_deflator_sobreposicao: float = 1.2
    adaptacao_max_alternativas: int = 3
    # relevância
    relevancia: dict[str, float] = field(default_factory=lambda: {
        "oponente_de_rota": 2.0, "mesma_rota": 1.5, "outra_rota": 1.0,
    })
    # vigia
    intervalo: int = 2
    reaplicar_a_cada_mudanca: bool = True

    # Preenchido durante a execução.
    tier_label: str = ""


def carregar(caminho: Path | str = CAMINHO) -> Config:
    """Lê o config.toml. Arquivo ausente ou seção faltando cai nos padrões."""
    cfg = Config()
    try:
        dados = tomllib.loads(Path(caminho).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return cfg
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"config.toml inválido: {exc}") from exc

    def pegar(secao: str, chave: str, atual):
        return (dados.get(secao) or {}).get(chave, atual)

    cfg.pagina_base_elo = pegar("pagina_base", "elo", cfg.pagina_base_elo)
    cfg.pagina_base_janela = str(
        pegar("pagina_base", "janela", cfg.pagina_base_janela))
    cfg.referencia_elo = pegar(
        "pagina_base", "referencia_elo", cfg.referencia_elo)
    cfg.matchups_elo = pegar("matchups", "elo", cfg.matchups_elo)
    cfg.matchups_janela_dias = str(
        pegar("matchups", "janela_dias", cfg.matchups_janela_dias))
    cfg.analise_habilitada = bool(
        pegar("analise_estatistica", "habilitada", cfg.analise_habilitada))
    cfg.analise_elo = pegar(
        "analise_estatistica", "elo", cfg.analise_elo)
    cfg.analise_janela_dias = str(pegar(
        "analise_estatistica", "janela_dias", cfg.analise_janela_dias))

    cfg.itens = int(pegar("exibicao", "itens", cfg.itens))
    cfg.ordenar_por = pegar("exibicao", "ordenar_por", cfg.ordenar_por)
    cfg.min_jogos = int(pegar("exibicao", "min_jogos", cfg.min_jogos))
    cfg.detalhe = bool(pegar("exibicao", "detalhe", cfg.detalhe))
    cfg.todos_os_itens = bool(pegar("exibicao", "todos_os_itens", cfg.todos_os_itens))

    cfg.html_habilitado = bool(
        pegar("html", "habilitado", cfg.html_habilitado))
    cfg.html_abrir_automaticamente = bool(pegar(
        "html", "abrir_automaticamente", cfg.html_abrir_automaticamente))
    cfg.html_pasta = str(pegar("html", "pasta", cfg.html_pasta))

    cfg.aplicar_runas = bool(pegar("client", "aplicar_runas", cfg.aplicar_runas))
    cfg.pagina_runas = int(pegar("client", "pagina_runas", cfg.pagina_runas))
    cfg.aplicar_feiticos = bool(
        pegar("client", "aplicar_feiticos", cfg.aplicar_feiticos))
    cfg.flash_no_d = bool(pegar("client", "flash_no_d", cfg.flash_no_d))

    cfg.z_minimo = float(pegar("trocas", "z_minimo", cfg.z_minimo))
    cfg.jogos_minimos = int(pegar("trocas", "jogos_minimos", cfg.jogos_minimos))

    cfg.adaptacao_habilitada = bool(pegar(
        "adaptacao_elo_alto", "habilitada", cfg.adaptacao_habilitada))
    cfg.adaptacao_elos = tuple(str(v) for v in pegar(
        "adaptacao_elo_alto", "elos", cfg.adaptacao_elos))
    cfg.adaptacao_janela_dias = str(pegar(
        "adaptacao_elo_alto", "janela_dias", cfg.adaptacao_janela_dias))
    cfg.adaptacao_jogos_totais_minimos = int(pegar(
        "adaptacao_elo_alto", "jogos_totais_minimos",
        cfg.adaptacao_jogos_totais_minimos))
    cfg.adaptacao_jogos_por_matchup_minimos = int(pegar(
        "adaptacao_elo_alto", "jogos_por_matchup_minimos",
        cfg.adaptacao_jogos_por_matchup_minimos))
    cfg.adaptacao_z_principal = float(pegar(
        "adaptacao_elo_alto", "z_principal", cfg.adaptacao_z_principal))
    cfg.adaptacao_z_alternativa = float(pegar(
        "adaptacao_elo_alto", "z_alternativa", cfg.adaptacao_z_alternativa))
    cfg.adaptacao_corrigir_multiplos_itens = bool(pegar(
        "adaptacao_elo_alto", "corrigir_multiplos_itens",
        cfg.adaptacao_corrigir_multiplos_itens))
    cfg.adaptacao_fdr_botas = float(pegar(
        "adaptacao_elo_alto", "fdr_botas", cfg.adaptacao_fdr_botas))
    cfg.adaptacao_deflator_sobreposicao = float(pegar(
        "adaptacao_elo_alto", "deflator_sobreposicao",
        cfg.adaptacao_deflator_sobreposicao))
    cfg.adaptacao_max_alternativas = int(pegar(
        "adaptacao_elo_alto", "max_alternativas",
        cfg.adaptacao_max_alternativas))

    for chave in list(cfg.relevancia):
        cfg.relevancia[chave] = float(
            pegar("relevancia", chave, cfg.relevancia[chave]))

    cfg.intervalo = int(pegar("vigia", "intervalo", cfg.intervalo))
    cfg.reaplicar_a_cada_mudanca = bool(
        pegar("vigia", "reaplicar_a_cada_mudanca", cfg.reaplicar_a_cada_mudanca))
    return cfg


def aplicar_argumentos(cfg: Config, args) -> Config:
    """Aplica somente os argumentos informados pelo usuário."""
    mapa = {
        "referencia": "referencia_elo", "itens": "itens", "por": "ordenar_por",
        "min_jogos": "min_jogos", "pagina_runas": "pagina_runas",
    }
    for origem, destino in mapa.items():
        valor = getattr(args, origem, None)
        if valor is not None:
            setattr(cfg, destino, valor)

    # Uma flag ausente não desliga a opção do arquivo.
    tier = getattr(args, "tier", None)
    if tier is not None:
        cfg.pagina_base_elo = tier
        cfg.matchups_elo = tier
    dias = getattr(args, "dias", None)
    if dias is not None:
        cfg.matchups_janela_dias = str(dias)
    tier_comp = getattr(args, "tier_comp", None)
    if tier_comp is not None:
        cfg.analise_elo = tier_comp

    for flag, destino in (("comp", "analise_habilitada"),
                          ("detalhe", "detalhe"),
                          ("tudo", "todos_os_itens"),
                          ("aplicar_runas", "aplicar_runas")):
        if getattr(args, flag, False):
            setattr(cfg, destino, True)
    if getattr(args, "sem_aplicar", False):
        cfg.aplicar_runas = False
        cfg.aplicar_feiticos = False
    return cfg


"""Entrada de linha de comando: argumentos, contexto e despacho do modo."""

from __future__ import annotations

import argparse

from advisor import config, observabilidade
from advisor.apresentacao import terminal
from advisor.client import lcu
from advisor.data import ddragon
from advisor.data.fonte_lolalytics import FonteLolalytics
from advisor.domain.draft import Draft
from advisor.fluxos import execucao, investigacao, vigia


def _campeao(static: ddragon.Static, nome: str) -> ddragon.Champion:
    encontrado = static.champion(nome)
    if encontrado is None:
        raise SystemExit(f"campeão desconhecido: {nome!r}")
    return encontrado


def draft_dos_argumentos(static: ddragon.Static, args) -> Draft:
    jogador = _campeao(static, args.champion)
    inimigos = [
        _campeao(static, nome)
        for nome in args.inimigos.split(",")
        if nome.strip()
    ]
    oponente = _campeao(static, args.opponent) if args.opponent else None
    if oponente and oponente.cid not in {c.cid for c in inimigos}:
        inimigos.append(oponente)
    return Draft(champion=jogador, lane=args.lane or "", enemies=inimigos,
                 opponent=oponente)


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="advisor",
        description="Recomenda build, runas e feitiços a partir do draft. "
                    "As opções vivem no config.toml; os argumentos servem "
                    "para experimentar sem editar o arquivo.")
    ap.add_argument("champion", nargs="?",
                    help="seu campeão (dispensável com --auto/--vigiar)")
    ap.add_argument("--lane", help="top | jungle | middle | bottom | support")
    ap.add_argument("--vs", dest="opponent", help="oponente direto de rota")
    ap.add_argument("--inimigos", default="",
                    help="time inimigo, separado por vírgula")
    ap.add_argument("--auto", action="store_true", help="lê o champ select uma vez")
    ap.add_argument("--vigiar", action="store_true",
                    help="observa o client continuamente")
    ap.add_argument("--tier", default=None)
    ap.add_argument("--referencia", default=None)
    ap.add_argument("--dias", default=None)
    ap.add_argument("--tier-comp", default=None)
    ap.add_argument("--itens", type=int, default=None)
    ap.add_argument("--por", choices=["pick", "winrate"], default=None)
    ap.add_argument("--min-jogos", type=int, default=None)
    ap.add_argument("--pagina-runas", type=int, default=None, metavar="ID")
    ap.add_argument("--comp", action="store_true",
                    help="análise estatística da composição")
    ap.add_argument("--detalhe", action="store_true")
    ap.add_argument("--tudo", action="store_true")
    ap.add_argument("--aplicar-runas", action="store_true")
    ap.add_argument("--sem-aplicar", action="store_true",
                    help="não escreve nada no client nesta execução")
    return ap


def _client_opcional() -> lcu.LCU | None:
    try:
        return lcu.LCU()
    except lcu.LCUError:
        return None


def main() -> None:
    observabilidade.configurar()
    from advisor.data.cache import migrar_legado
    if migrar_legado():
        observabilidade.LOGGER.info("cache antigo migrado")

    ap = _parser()
    args = ap.parse_args()
    cfg = config.aplicar_argumentos(config.carregar(), args)
    static = ddragon.load()
    contexto = execucao.ContextoExecucao(
        cfg, static, _client_opcional(), FonteLolalytics())

    if args.auto or args.vigiar:
        if contexto.client is None:
            ap.error("League Client indisponível")
        try:
            if args.auto and not args.vigiar:
                vigia.executar_uma_vez(contexto)
            else:
                vigia.observar(contexto)
        except lcu.LCUError as exc:
            ap.error(str(exc))
        return

    if not args.champion:
        ap.error("informe um campeão, ou use --auto / --vigiar para ler do client")

    draft = draft_dos_argumentos(static, args)
    resultado = execucao.executar_draft(draft, contexto)
    aplicacao = execucao.aplicar_recomendacao(resultado, contexto)
    analise = investigacao.executar(draft, contexto)
    terminal.apresentar(resultado, contexto, aplicacao, analise)
    observabilidade.registrar_falhas(resultado.recomendacao)
    falhas = [*resultado.falhas, *aplicacao.falhas]
    if analise is not None and analise.falha:
        falhas.append(analise.falha)
    observabilidade.registrar_falhas_tecnicas(falhas)


if __name__ == "__main__":
    main()


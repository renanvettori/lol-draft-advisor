"""Adapta uma build popular ao draft por mudança de escolha em Emerald+.

Este é o seam consumido pelo fluxo principal. Coleta e apresentação ficam fora;
contração, testes, inventário, conflitos e cascata ficam no domínio.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from advisor.domain import estatistica
from advisor.domain import transferencias as T
from advisor.domain.modelos import PaginasDoDraft


class EstadoAdaptacao(StrEnum):
    PERSONALIZADA = "personalizada"
    SEM_ADAPTACAO = "sem_adaptacao"
    DADOS_INSUFICIENTES = "dados_insuficientes"
    ERRO = "erro"


@dataclass(frozen=True)
class CriteriosAdaptacao:
    z_principal: float = 1.65
    z_alternativa: float = 1.50
    corrigir_multiplos_itens: bool = False
    fdr_botas: float = 0.10
    deflator_sobreposicao: float = 1.2
    max_alternativas: int = 3


@dataclass(frozen=True)
class EvidenciaEscolha:
    item_id: int
    slot: str
    inimigo: str
    delta_log_odds: float
    erro: float
    z: float
    p_valor: float
    pick_base: float
    pick_matchup: float
    compras: int
    peso: float
    passou_z: bool = False
    passou_fdr: bool = False
    direcao: str = "neutra"
    contribuicao: float = 0.0


@dataclass(frozen=True)
class AcaoAdaptacao:
    tipo: str
    item_id: int
    slot_origem: str | None
    slot_destino: str
    score: float
    evidencias: tuple[EvidenciaEscolha, ...] = ()
    removido: int | None = None
    z: float = 0.0
    limite_inferior: float = 0.0


@dataclass(frozen=True)
class AlternativaAdaptacao:
    sequencia: tuple[tuple[str, int], ...]
    acoes: tuple[AcaoAdaptacao, ...]
    z_conjunto: float
    limite_inferior: float


@dataclass(frozen=True)
class ResultadoAdaptacao:
    estado: EstadoAdaptacao
    elo: str | None = None
    sequencia: tuple[tuple[str, int], ...] = ()
    sequencia_base: tuple[tuple[str, int], ...] = ()
    acoes: tuple[AcaoAdaptacao, ...] = ()
    evidencias: tuple[EvidenciaEscolha, ...] = ()
    hipoteses_avaliadas: int = 0
    passaram_z: int = 0
    sobreviveram_fdr: int = 0
    elos_tentados: tuple[str, ...] = ()
    falha: str | None = None
    alternativas: tuple[AlternativaAdaptacao, ...] = ()
    z_conjunto: float = 0.0
    limite_inferior: float = 0.0
    item6_estimado: bool = False
    cache_em: str | None = None


def indisponivel(elos: list[str] | tuple[str, ...], motivo: str) -> ResultadoAdaptacao:
    return ResultadoAdaptacao(
        EstadoAdaptacao.DADOS_INSUFICIENTES,
        elos_tentados=tuple(elos), falha=motivo,
    )


def build_popular(
    paginas: PaginasDoDraft,
    *,
    elo: str,
    validos: set[int],
    lane: str,
    elos_tentados: tuple[str, ...],
    motivo: str,
) -> ResultadoAdaptacao:
    """Entrega a build popular quando não há amostra para adaptá-la."""
    sequencia = T.sequencia_popular(
        paginas, validos, item6=lane == "bottom")
    if not sequencia:
        return indisponivel(elos_tentados, motivo)
    return ResultadoAdaptacao(
        estado=EstadoAdaptacao.DADOS_INSUFICIENTES,
        elo=elo,
        sequencia=sequencia,
        sequencia_base=sequencia,
        elos_tentados=elos_tentados,
        falha=motivo,
        item6_estimado=lane == "bottom",
    )


def confianca(z: float) -> str:
    if z >= 2.50:
        return "muito forte"
    if z >= 2.00:
        return "forte"
    if z >= 1.65:
        return "moderada"
    return "exploratória"


def _evidencias(acao: T.AcaoSequencia, *, fdr: bool = False) -> tuple[EvidenciaEscolha, ...]:
    saida = []
    for parcela in acao.parcelas:
        z = parcela.delta / parcela.erro if parcela.erro else 0.0
        direcao = "positiva" if parcela.delta > 0 else (
            "negativa" if parcela.delta < 0 else "neutra")
        saida.append(EvidenciaEscolha(
            acao.candidato, acao.slot_destino, parcela.inimigo,
            parcela.delta, parcela.erro, z,
            estatistica.p_valor_bilateral(z),
            parcela.base_pick, parcela.candidato_pick, 0, parcela.peso,
            passou_z=abs(z) >= 1.65, passou_fdr=fdr,
            direcao=direcao, contribuicao=parcela.delta * parcela.peso,
        ))
    return tuple(saida)


def _acao_item(acao: T.AcaoSequencia,
               posicao_base: dict[int, str]) -> AcaoAdaptacao:
    origem = posicao_base.get(acao.candidato)
    if origem is None:
        tipo = "substituicao"
    else:
        origem_i = int(origem.split()[1])
        destino_i = int(acao.slot_destino.split()[1])
        tipo = "antecipacao" if destino_i < origem_i else "adiamento"
    return AcaoAdaptacao(
        tipo, acao.candidato, origem, acao.slot_destino,
        acao.efeito, _evidencias(acao), acao.removido,
        acao.z, acao.limite_inferior,
    )


def _acao_bota(h: T.Hipotese, z_principal: float) -> AcaoAdaptacao:
    acao = T.AcaoSequencia(
        h.candidato, h.ocupante, "Botas", h.efeito_posterior,
        h.erro_posterior, h.z_posterior,
        h.efeito_posterior - z_principal * h.erro_posterior, h.parcelas)
    return AcaoAdaptacao(
        "botas", h.candidato, "Botas", "Botas", h.efeito_posterior,
        _evidencias(acao, fdr=True), h.ocupante, h.z_posterior,
        acao.limite_inferior)


def _com_bota(itens: tuple[tuple[str, int], ...],
              bota: int | None) -> tuple[tuple[str, int], ...]:
    return (("Botas", bota),) + itens if bota else itens


def calcular(
    paginas: PaginasDoDraft,
    *,
    elo: str,
    criterios: CriteriosAdaptacao,
    validos: set[int] | None = None,
    elos_tentados: tuple[str, ...] = (),
    lane: str = "",
) -> ResultadoAdaptacao:
    """Retorna uma build completa e auditável sem efeitos colaterais."""
    if paginas.base is None or not paginas.paginas:
        return indisponivel(elos_tentados, "páginas completas não disponíveis")
    if validos is None:
        validos = {r.item_id for build in [paginas.base]
                   + [p.build for p in paginas.paginas]
                   for rows in build.tables.values() for r in rows}
    analise = T.analisar(
        paginas, elo=elo,
        criterios=T.Criterios(
            criterios.z_alternativa, criterios.fdr_botas,
            criterios.deflator_sobreposicao),
        validos=validos, total_inimigos=len(paginas.paginas), lane=lane)
    if not analise.sequencia_base:
        return indisponivel(elos_tentados, "build base não disponível")

    plano = T.otimizar_sequencias(
        analise, z_principal=criterios.z_principal,
        z_alternativa=criterios.z_alternativa,
        max_alternativas=criterios.max_alternativas,
        exigir_fdr_itens=criterios.corrigir_multiplos_itens)
    base_por_slot = dict(analise.sequencia_base)
    bota_base = base_por_slot.get("Botas")
    botas = [h for h in analise.hipoteses
             if h.tipo == "slot" and h.slot == "Botas"
             and h.ocupante == bota_base and h.passou_fdr
             and h.z_posterior >= criterios.z_principal
             and h.efeito_posterior
             - criterios.z_principal * h.erro_posterior > 0]
    melhor_bota = max(
        botas,
        key=lambda h: h.efeito_posterior
        - criterios.z_principal * h.erro_posterior,
        default=None)
    bota = melhor_bota.candidato if melhor_bota else bota_base

    itens_base = tuple((slot, iid) for slot, iid in analise.sequencia_base
                       if slot != "Botas")
    posicao_base = {iid: slot for slot, iid in itens_base}
    principal = plano.principal
    itens_finais = principal.sequencia if principal else itens_base
    acoes = ([_acao_bota(melhor_bota, criterios.z_principal)]
             if melhor_bota else [])
    if principal:
        acoes.extend(_acao_item(a, posicao_base) for a in principal.acoes)
    evidencias = tuple(ev for acao in acoes for ev in acao.evidencias)
    alternativas = tuple(AlternativaAdaptacao(
        _com_bota(alt.sequencia, bota),
        tuple(_acao_item(a, posicao_base) for a in alt.acoes),
        alt.z, alt.limite_inferior,
    ) for alt in plano.alternativas)

    base_completa = _com_bota(itens_base, bota_base)
    final = _com_bota(itens_finais, bota)
    estado = (EstadoAdaptacao.PERSONALIZADA if acoes
              else EstadoAdaptacao.SEM_ADAPTACAO)
    caches = [b.cache_em for b in [paginas.base]
              + [p.build for p in paginas.paginas]
              if b.cache_fallback and b.cache_em]
    principais = [
        h for h in analise.hipoteses if h.tipo == "slot"
        and h.ocupante == base_por_slot.get(
            "Item 6" if h.familia == "Item 6 proxy" else h.slot)]
    return ResultadoAdaptacao(
        estado, elo, final, base_completa, tuple(acoes), evidencias,
        len(principais),
        sum(h.z_posterior >= criterios.z_principal for h in principais),
        sum(h.slot == "Botas" and h.passou_fdr for h in principais),
        elos_tentados, None, alternativas,
        principal.z if principal else 0.0,
        principal.limite_inferior if principal else 0.0,
        lane == "bottom",
        min(caches) if caches else None,
    )


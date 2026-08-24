"""Avalia mudanças de posição e presença dos itens na build."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass, field, replace

from advisor.domain import estatistica
from advisor.domain.modelos import Item, PaginasDoDraft

SLOTS = ("Botas", "Item 1", "Item 2", "Item 3", "Item 4", "Item 5")
SLOTS_ITENS = SLOTS[1:]


@dataclass(frozen=True)
class Criterios:
    z_minimo: float = 2.0
    fdr: float = .10
    deflator: float = 1.2


@dataclass(frozen=True)
class Parcela:
    inimigo: str
    peso: float
    delta: float
    erro: float
    candidato_pick: float
    base_pick: float
    censurado: bool


@dataclass(frozen=True)
class Hipotese:
    tipo: str
    slot: str
    candidato: int
    ocupante: int
    delta: float
    erro: float
    z: float
    p_valor: float
    limite_inferior: float
    passou_z: bool
    passou_fdr: bool = False
    parcelas: tuple[Parcela, ...] = ()
    familia: str = ""
    efeito_posterior: float = 0.0
    erro_posterior: float = 0.0
    z_posterior: float = 0.0
    p_posterior: float = 1.0
    limite_posterior: float = float("-inf")
    contracao: float = 1.0


@dataclass(frozen=True)
class Modificacao:
    tipo: str
    candidato: int
    ocupante: int
    slot_origem: str | None
    slot_destino: str
    efeito: float
    limite_inferior: float
    motivo: str
    removido: int | None = None
    efeito_bruto: float = 0.0
    contracao: float = 0.0


@dataclass
class Resultado:
    elo: str
    cobertura: int
    total_inimigos: int
    excluidos: tuple[str, ...]
    cobertura_critica: tuple[str, ...]
    sequencia_base: tuple[tuple[str, int], ...]
    sequencia: tuple[tuple[str, int], ...]
    hipoteses: tuple[Hipotese, ...]
    modificacoes: tuple[Modificacao, ...]
    alternativas: tuple[Modificacao, ...]
    pode_alterar: bool
    invariantes: tuple[str, ...] = ()
    prior_por_familia: dict[str, float] = field(default_factory=dict)
    item6_proxy: bool = False

    def json(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AcaoSequencia:
    candidato: int
    removido: int | None
    slot_destino: str
    efeito: float
    erro: float
    z: float
    limite_inferior: float
    parcelas: tuple[Parcela, ...] = ()


@dataclass(frozen=True)
class SequenciaOtimizada:
    sequencia: tuple[tuple[str, int], ...]
    acoes: tuple[AcaoSequencia, ...]
    efeito: float
    erro: float
    z: float
    limite_inferior: float
    precisao: float


@dataclass(frozen=True)
class PlanoSequencias:
    principal: SequenciaOtimizada | None
    alternativas: tuple[SequenciaOtimizada, ...] = ()


def _row(rows: list[Item], iid: int) -> Item | None:
    return next((r for r in rows if r.item_id == iid), None)


def _limite_omissao(rows: list[Item]) -> tuple[float, float]:
    validos = [r for r in rows if r.games > 0 and r.pr > 0]
    if not validos:
        return .5, 0.0
    menor = min(validos, key=lambda r: r.pr)
    return max(.5, float(menor.games)), menor.pr


def _n_estimado(rows: list[Item]) -> float:
    valores = sorted(r.games / (r.pr / 100) for r in rows
                     if r.games > 0 and r.pr > 0)
    return valores[len(valores) // 2] if valores else 0.0


def _contagem_conservadora(rows: list[Item], iid: int, papel: str) -> tuple[float, float, bool]:
    encontrado = _row(rows, iid)
    if encontrado:
        return float(encontrado.games), encontrado.pr, False
    _, pick = _limite_omissao(rows)
    limite = _n_estimado(rows) * pick / 100
    # A correção 0,5 evita log(0) nos extremos.
    usar_limite = papel in {"candidato_base", "ocupante_matchup"}
    return (limite if usar_limite else 0.0), (pick if usar_limite else 0.0), True


def _log_razao(x_c: float, x_b: float) -> tuple[float, float]:
    c, b = x_c + .5, x_b + .5
    return math.log(c / b), 1 / c + 1 / b


def _logit(x: float, n: float) -> tuple[float, float]:
    n = max(n, x)
    sucesso, falha = x + .5, n - x + .5
    return math.log(sucesso / falha), 1 / sucesso + 1 / falha


def _presenca(build, iid: int) -> tuple[float, float]:
    rows = [r for slot in SLOTS_ITENS for r in build.tables.get(slot, ())
            if r.item_id == iid]
    return float(sum(r.games for r in rows)), min(99.5, sum(r.pr for r in rows))


def _presenca_conservadora(build, iid: int, papel: str) -> tuple[float, float, bool]:
    jogos, pick = _presenca(build, iid)
    if jogos:
        return jogos, pick, False
    limites = [(_n_estimado(list(build.tables.get(slot, ()))),
                _limite_omissao(list(build.tables.get(slot, ())))[1])
               for slot in SLOTS_ITENS if build.tables.get(slot)]
    pick_limite = sum(x[1] for x in limites)
    ns = [x[0] for x in limites if x[0] > 0]
    limite = (sum(ns) / len(ns) * pick_limite / 100) if ns else 0.0
    usar_limite = papel in {"candidato_base", "ocupante_matchup"}
    return (limite if usar_limite else 0.0), (pick_limite if usar_limite else 0.0), True


def _transferencia(paginas: PaginasDoDraft, slot: str, candidato: int,
                   ocupante: int, criterios: Criterios, *, presenca=False,
                   proxy_item6=False) -> Hipotese:
    if proxy_item6:
        por_slot = _transferencia(
            paginas, slot, candidato, ocupante, criterios)
        por_presenca = _transferencia(
            paginas, "Presença", candidato, ocupante, criterios,
            presenca=True)
        parcelas = tuple(Parcela(
            a.inimigo, a.peso,
            (a.delta + b.delta) / 2,
            max(a.erro, b.erro),
            (a.candidato_pick + b.candidato_pick) / 2,
            (a.base_pick + b.base_pick) / 2,
            a.censurado or b.censurado,
        ) for a, b in zip(por_slot.parcelas, por_presenca.parcelas))
        robusta = por_slot.p_valor < 1 and por_presenca.p_valor < 1
        delta = (por_slot.delta + por_presenca.delta) / 2
        # As leituras são correlacionadas; usa-se o maior erro.
        erro = max(por_slot.erro, por_presenca.erro)
        z = delta / erro if erro else 0.0
        p = estatistica.p_valor_bilateral(z) if robusta else 1.0
        return Hipotese(
            "slot", slot, candidato, ocupante, delta, erro, z, p,
            delta - criterios.z_minimo * erro if robusta else float("-inf"),
            robusta and abs(z) >= criterios.z_minimo,
            parcelas=parcelas, familia="Item 6 proxy")
    base = paginas.base
    assert base is not None
    if presenca:
        cb, cpb, cens_c = _presenca_conservadora(base, candidato, "candidato_base")
        bb, bpb, cens_b = _presenca_conservadora(base, ocupante, "ocupante_base")
    else:
        rows = list(base.tables.get(slot, ()))
        cb, cpb, cens_c = _contagem_conservadora(rows, candidato, "candidato_base")
        bb, bpb, cens_b = _contagem_conservadora(rows, ocupante, "ocupante_base")
    razao_base, var_base = _log_razao(cb, bb)

    peso_total = sum(p.peso for p in paginas.paginas) or 1.0
    media = 0.0
    var_matchups = 0.0
    parcelas = []
    candidato_omitido_no_matchup = False
    for pagina in paginas.paginas:
        peso = pagina.peso / peso_total
        if presenca:
            cv, cp, cc = _presenca_conservadora(
                pagina.build, candidato, "candidato_matchup")
            bv, bp, bc = _presenca_conservadora(
                pagina.build, ocupante, "ocupante_matchup")
        else:
            rows = list(pagina.build.tables.get(slot, ()))
            cv, cp, cc = _contagem_conservadora(
                rows, candidato, "candidato_matchup")
            bv, bp, bc = _contagem_conservadora(
                rows, ocupante, "ocupante_matchup")
        razao, variancia = _log_razao(cv, bv)
        candidato_omitido_no_matchup = candidato_omitido_no_matchup or cc
        delta = razao - razao_base
        media += peso * razao
        var_matchups += peso * peso * variancia
        parcelas.append(Parcela(
            pagina.enemy.name, peso, delta, math.sqrt(variancia), cp, bp,
            cc or bc or cens_c or cens_b))

    delta = media - razao_base
    erro = math.sqrt(var_matchups + var_base) * criterios.deflator
    z = delta / erro if erro else 0.0
    robusta = not candidato_omitido_no_matchup
    p_valor = estatistica.p_valor_bilateral(z) if robusta else 1.0
    limite = delta - criterios.z_minimo * erro if robusta else float("-inf")
    return Hipotese(
        "presenca" if presenca else "slot", slot, candidato, ocupante,
        delta, erro, z, p_valor, limite,
        robusta and abs(z) >= criterios.z_minimo,
        parcelas=tuple(parcelas),
        familia=("Presença" if presenca else slot))


def _regularizar(hipoteses: list[Hipotese], criterios: Criterios) -> tuple[list[Hipotese], dict[str, float]]:
    """Aplica contração empírico-bayesiana por família."""
    familias: dict[str, list[Hipotese]] = {}
    for h in hipoteses:
        if h.p_valor < 1 and math.isfinite(h.delta):
            familias.setdefault(h.familia, []).append(h)
    taus: dict[str, float] = {}
    for familia, valores in familias.items():
        deltas = [h.delta for h in valores]
        mediana = statistics.median(deltas)
        mad = statistics.median(abs(x - mediana) for x in deltas)
        variancia_observada = (mad / .67448975) ** 2 if mad else 0.0
        variancia_ruido = statistics.median(h.erro * h.erro for h in valores)
        taus[familia] = max(0.0, variancia_observada - variancia_ruido)

    saida = []
    for h in hipoteses:
        tau2 = taus.get(h.familia, 0.0)
        if h.p_valor >= 1 or tau2 <= 0 or h.erro <= 0:
            saida.append(replace(
                h, efeito_posterior=0.0, erro_posterior=0.0,
                z_posterior=0.0, p_posterior=1.0,
                limite_posterior=float("-inf"), contracao=1.0))
            continue
        var = h.erro * h.erro
        fator = tau2 / (tau2 + var)
        efeito = fator * h.delta
        erro = math.sqrt(tau2 * var / (tau2 + var))
        z = efeito / erro if erro else 0.0
        p = estatistica.p_valor_bilateral(z)
        saida.append(replace(
            h, efeito_posterior=efeito, erro_posterior=erro,
            z_posterior=z, p_posterior=p,
            limite_posterior=efeito - criterios.z_minimo * erro,
            contracao=1 - fator))
    return saida, taus


def _bh(hipoteses: list[Hipotese], q: float) -> set[int]:
    if not hipoteses:
        return set()
    resultado = estatistica.corrigir_fdr(
        [hipotese.p_posterior for hipotese in hipoteses],
        alpha=q,
    )
    return {
        indice
        for indice, rejeitada in enumerate(resultado.rejeitadas)
        if rejeitada
    }


def _sequencia_base(paginas: PaginasDoDraft, validos: set[int],
                    *, item6: bool) -> list[tuple[str, int]]:
    usados = set()
    saida = []
    if paginas.base is None:
        return saida
    for slot in SLOTS:
        rows = sorted(paginas.base.tables.get(slot, ()), key=lambda r: -r.pr)
        item = next((r for r in rows if r.item_id in validos and r.item_id not in usados), None)
        if item:
            usados.add(item.item_id)
            saida.append((slot, item.item_id))
    if item6 and paginas.base is not None:
        candidatos = sorted(paginas.base.tables.get("Item 5", ()), key=lambda r: -r.pr)
        extra = next((r for r in candidatos
                      if r.item_id in validos and r.item_id not in usados), None)
        if extra:
            saida.append(("Item 6", extra.item_id))
    return saida


def sequencia_popular(
    paginas: PaginasDoDraft,
    validos: set[int],
    *,
    item6: bool = False,
) -> tuple[tuple[str, int], ...]:
    """Expõe a build popular sem avaliar win rate de itens."""
    return tuple(_sequencia_base(paginas, validos, item6=item6))


def _movimento(paginas: PaginasDoDraft, iid: int, criterios: Criterios,
               *, slot: str | None = None) -> Hipotese:
    """Mudança própria de um item; ausência torna a direção não robusta."""
    base = paginas.base
    assert base is not None

    def dados(build):
        if slot:
            rows = list(build.tables.get(slot, ()))
            row = _row(rows, iid)
            if row is None:
                return 0.0, 0.0, True
            n = _n_estimado(rows)
            return float(row.games), n, False
        jogos, pick = _presenca(build, iid)
        if not jogos:
            return 0.0, 0.0, True
        n = jogos / (pick / 100) if pick else 0.0
        return jogos, n, False

    xb, nb, cens_base = dados(base)
    if cens_base or nb <= 0:
        robusta = False
        logit_base = var_base = 0.0
    else:
        logit_base, var_base = _logit(xb, nb)
        robusta = True
    peso_total = sum(p.peso for p in paginas.paginas) or 1.0
    media = var_matchups = 0.0
    parcelas = []
    for pagina in paginas.paginas:
        x, n, cens = dados(pagina.build)
        robusta = robusta and not cens and n > 0
        if cens or n <= 0:
            valor, variancia = 0.0, 2.0
            pick = 0.0
        else:
            valor, variancia = _logit(x, n)
            pick = x / n * 100
        peso = pagina.peso / peso_total
        media += peso * valor
        var_matchups += peso * peso * variancia
        parcelas.append(Parcela(
            pagina.enemy.name, peso, valor - logit_base, math.sqrt(variancia),
            pick, 0.0, cens))
    delta = media - logit_base
    erro = math.sqrt(var_matchups + var_base) * criterios.deflator
    z = delta / erro if erro else 0.0
    p = estatistica.p_valor_bilateral(z) if robusta else 1.0
    nome_slot = slot or "Presença"
    return Hipotese(
        "movimento_slot" if slot else "movimento_presenca", nome_slot,
        iid, iid, delta, erro, z, p,
        delta - criterios.z_minimo * erro if robusta else float("-inf"),
        robusta and abs(z) >= criterios.z_minimo,
        parcelas=tuple(parcelas), familia=f"Movimento {nome_slot}")


def analisar(paginas: PaginasDoDraft, *, elo: str, criterios: Criterios,
             validos: set[int], total_inimigos: int,
             excluidos: tuple[str, ...] = (),
             cobertura_critica: tuple[str, ...] = (),
             lane: str = "") -> Resultado:
    tem_item6 = lane == "bottom"
    base_seq = _sequencia_base(paginas, validos, item6=tem_item6)
    base_por_slot = dict(base_seq)
    hipoteses: list[Hipotese] = []
    ids_totais: set[int] = set()

    fontes_slot = [(slot, slot, False) for slot in SLOTS]
    if tem_item6:
        fontes_slot.append(("Item 6", "Item 5", True))
    for destino, fonte, proxy in fontes_slot:
        ids = {r.item_id for p in paginas.paginas
               for r in p.build.tables.get(fonte, ()) if r.item_id in validos}
        ids.update(r.item_id for r in (
            paginas.base.tables.get(fonte, ()) if paginas.base else ())
                   if r.item_id in validos)
        ids_totais.update(ids)
        ocupantes = {iid for slot, iid in base_seq if slot != "Botas"}
        if destino == "Botas":
            ocupantes = {base_por_slot.get("Botas")} - {None}
        for candidato in ids:
            for ocupante in ocupantes - {candidato}:
                hipoteses.append(_transferencia(
                    paginas, fonte, candidato, ocupante, criterios,
                    proxy_item6=proxy))

    for iid in ids_totais:
        hipoteses.append(_movimento(paginas, iid, criterios))
    for slot in SLOTS_ITENS:
        ids_slot = {r.item_id for p in paginas.paginas
                    for r in p.build.tables.get(slot, ()) if r.item_id in validos}
        ids_slot.update(r.item_id for r in (
            paginas.base.tables.get(slot, ()) if paginas.base else ())
                        if r.item_id in validos)
        for iid in ids_slot:
            hipoteses.append(_movimento(paginas, iid, criterios, slot=slot))
    itens_base = {iid for slot, iid in base_seq if slot != "Botas"}
    for candidato in ids_totais:
        for ocupante in itens_base - {candidato}:
            hipoteses.append(_transferencia(
                paginas, "Presença", candidato, ocupante, criterios,
                presenca=True))

    hipoteses, taus = _regularizar(hipoteses, criterios)
    # Só candidato contra ocupante inicial entra na família do FDR.
    indices_por_slot: dict[str, list[int]] = {}
    for indice, h in enumerate(hipoteses):
        if h.tipo != "slot":
            continue
        destino = "Item 6" if h.familia == "Item 6 proxy" else h.slot
        if (h.ocupante == base_por_slot.get(destino)
                and h.p_posterior < 1
                and h.efeito_posterior > 0):
            indices_por_slot.setdefault(destino, []).append(indice)
    aprovadas: set[int] = set()
    for indices in indices_por_slot.values():
        familia = [hipoteses[i] for i in indices]
        aprovadas_locais = _bh(familia, criterios.fdr)
        aprovadas.update(indices[i] for i in aprovadas_locais)
    hipoteses = [replace(h, passou_fdr=i in aprovadas)
                 for i, h in enumerate(hipoteses)]
    por_chave = {(h.tipo, h.slot, h.candidato, h.ocupante): h for h in hipoteses}
    posicao_base = {iid: slot for slot, iid in base_seq}
    pode_alterar = len(paginas.paginas) >= 3
    itens = [iid for slot, iid in base_seq if slot != "Botas"]
    bota = base_por_slot.get("Botas")
    aplicadas: list[Modificacao] = []
    bloqueadas: list[Modificacao] = []
    usados_em_acao: set[int] = set()

    candidatas = [h for h in hipoteses
                  if h.tipo == "slot" and h.passou_fdr
                  and h.z_posterior >= criterios.z_minimo
                  and h.limite_posterior > 0]
    for h in sorted(candidatas, key=lambda x: -x.limite_posterior):
        destino = "Item 6" if h.familia == "Item 6 proxy" else h.slot
        if destino == "Botas":
            if bota != h.ocupante or h.candidato in usados_em_acao:
                continue
            mod = Modificacao(
                "substituicao", h.candidato, h.ocupante, "Botas", "Botas",
                h.efeito_posterior, h.limite_posterior,
                "botas candidatas ganharam preferência das botas base",
                removido=h.ocupante, efeito_bruto=h.delta,
                contracao=h.contracao)
            if pode_alterar:
                bota = h.candidato
                aplicadas.append(mod)
                usados_em_acao.add(h.candidato)
            else:
                bloqueadas.append(replace(mod, motivo="cobertura permite somente alternativa"))
            continue

        slots_atuais = [f"Item {i}" for i in range(1, len(itens) + 1)]
        atual_por_slot = dict(zip(slots_atuais, itens))
        if atual_por_slot.get(destino) != h.ocupante:
            continue
        origem_indice = itens.index(h.candidato) if h.candidato in itens else None
        alvo = int(destino.split()[1]) - 1
        removido = None
        if origem_indice is not None:
            origem = f"Item {origem_indice + 1}"
            mov_origem = por_chave.get(
                ("movimento_slot", posicao_base.get(h.candidato, ""),
                 h.candidato, h.candidato))
            if not (mov_origem
                    and mov_origem.z_posterior <= -criterios.z_minimo):
                bloqueadas.append(Modificacao(
                    "ambigua", h.candidato, h.ocupante, origem, destino,
                    h.efeito_posterior, h.limite_posterior,
                    "o item subiu no destino, mas não caiu no slot original",
                    efeito_bruto=h.delta, contracao=h.contracao))
                continue
            tipo = "antecipacao" if alvo < origem_indice else "adiamento"
        else:
            movimento_candidato = por_chave.get(
                ("movimento_presenca", "Presença", h.candidato, h.candidato))
            transferencias_presenca = []
            for iid in itens:
                hp = por_chave.get(("presenca", "Presença", h.candidato, iid))
                if (hp and hp.z_posterior >= criterios.z_minimo
                        and hp.limite_posterior > 0):
                    transferencias_presenca.append(hp)
            quedas = []
            for iid in itens:
                mov = por_chave.get(("movimento_presenca", "Presença", iid, iid))
                if (mov and mov.z_posterior <= -criterios.z_minimo):
                    quedas.append(mov)
            if transferencias_presenca:
                transferencia = max(
                    transferencias_presenca, key=lambda x: x.limite_posterior)
                removido = transferencia.ocupante
            elif (movimento_candidato
                  and movimento_candidato.z_posterior >= criterios.z_minimo
                  and quedas):
                removido = min(
                    quedas, key=lambda x: x.efeito_posterior).candidato
            else:
                bloqueadas.append(Modificacao(
                    "ambigua", h.candidato, h.ocupante, None, destino,
                    h.efeito_posterior, h.limite_posterior,
                    "o candidato subiu, mas nenhum item justificou sua saída",
                    efeito_bruto=h.delta, contracao=h.contracao))
                continue
            tipo = "substituicao"
            origem = None

        mod = Modificacao(
            tipo, h.candidato, h.ocupante, origem, destino,
            h.efeito_posterior, h.limite_posterior,
            ("item mudou de posição com presença total preservada"
             if origem_indice is not None else
             "candidato ganhou presença e outro item justificou a saída"),
            removido=removido, efeito_bruto=h.delta, contracao=h.contracao)
        if not pode_alterar:
            bloqueadas.append(replace(mod, motivo="cobertura permite somente alternativa"))
            continue
        tentativa = list(itens)
        if removido in tentativa:
            tentativa.remove(removido)
        if h.candidato in tentativa:
            tentativa.remove(h.candidato)
        tentativa.insert(min(alvo, len(tentativa)), h.candidato)
        if len(tentativa) != len(itens):
            bloqueadas.append(replace(mod, motivo="a cascata não preservou o inventário completo"))
            continue
        itens = tentativa
        aplicadas.append(mod)
        usados_em_acao.add(h.candidato)

    slots_finais = [f"Item {i}" for i in range(1, len(itens) + 1)]
    sequencia = ([('Botas', bota)] if bota else []) + list(zip(slots_finais, itens))
    invariantes = []
    esperado = (7 if tem_item6 else 6) if len(base_seq) >= 6 else len(base_seq)
    ids = [iid for _, iid in sequencia]
    if len(sequencia) != esperado:
        invariantes.append(f"inventário tem {len(sequencia)} entradas; esperado {esperado}")
    if len(ids) != len(set(ids)):
        invariantes.append("item duplicado")
    for mod in aplicadas:
        if dict(sequencia).get(mod.slot_destino) != mod.candidato:
            invariantes.append(f"ação desfeita: {mod.candidato} em {mod.slot_destino}")
    if invariantes:
        sequencia = list(base_seq)
        bloqueadas.extend(replace(m, motivo="resultado revertido por invariante")
                          for m in aplicadas)
        aplicadas = []
    return Resultado(
        elo, len(paginas.paginas), total_inimigos, excluidos,
        cobertura_critica, tuple(base_seq), tuple(sequencia), tuple(hipoteses),
        tuple(aplicadas), tuple(sorted(
            bloqueadas, key=lambda m: -m.limite_inferior))[:],
        pode_alterar, tuple(invariantes), taus, tem_item6)


def _destino(h: Hipotese) -> str:
    return "Item 6" if h.familia == "Item 6 proxy" else h.slot


def _avaliar_sequencia(
    sequencia: list[int],
    slots: list[str],
    base_por_slot: dict[str, int],
    comparacoes: dict[tuple[str, int, int], Hipotese],
    z_minimo: float,
) -> tuple[float, float, float, float, float] | None:
    componentes = []
    for slot, iid in zip(slots, sequencia):
        base = base_por_slot[slot]
        if iid == base:
            continue
        h = comparacoes.get((slot, iid, base))
        if h is None or h.p_posterior >= 1:
            return None
        componentes.append(h)
    if not componentes:
        return 0.0, 0.0, 0.0, 0.0, 0.0
    efeito = sum(h.efeito_posterior for h in componentes)
    erro = math.sqrt(sum(h.erro_posterior ** 2 for h in componentes))
    z = efeito / erro if erro else 0.0
    limite = efeito - z_minimo * erro
    precisao = sum(1 / (h.erro_posterior ** 2) for h in componentes
                   if h.erro_posterior > 0)
    return efeito, erro, z, limite, precisao


def _otimizar(
    resultado: Resultado,
    *,
    z_minimo: float,
    conflitos: tuple[frozenset[int], ...],
    z_maximo: float | None = None,
    exigir_fdr: bool = False,
    primeiras_bloqueadas: frozenset[tuple[str, int]] = frozenset(),
) -> SequenciaOtimizada | None:
    base = [iid for slot, iid in resultado.sequencia_base if slot != "Botas"]
    slots = [f"Item {i}" for i in range(1, len(base) + 1)]
    if not base:
        return None
    base_por_slot = dict(zip(slots, base))
    comparacoes: dict[tuple[str, int, int], Hipotese] = {}
    candidatas: dict[tuple[str, int], Hipotese] = {}
    for h in resultado.hipoteses:
        if h.tipo != "slot" or h.p_posterior >= 1:
            continue
        destino = _destino(h)
        if destino not in base_por_slot:
            continue
        comparacoes[(destino, h.candidato, h.ocupante)] = h
        limite = h.efeito_posterior - z_minimo * h.erro_posterior
        if (h.ocupante == base_por_slot[destino]
                and h.z_posterior >= z_minimo and limite > 0
                and (not exigir_fdr or h.passou_fdr)
                and (z_maximo is None or h.z_posterior < z_maximo)):
            candidatas[(destino, h.candidato)] = h

    atual = list(base)
    avaliacao_atual = (0.0, 0.0, 0.0, 0.0, 0.0)
    protegidas: dict[int, int] = {}
    acoes: list[AcaoSequencia] = []
    usadas: set[tuple[str, int]] = set()
    while True:
        opcoes = []
        for (destino, candidato), h in candidatas.items():
            if (destino, candidato) in usadas:
                continue
            if not acoes and (destino, candidato) in primeiras_bloqueadas:
                continue
            alvo = slots.index(destino)
            if candidato in atual:
                remocoes = [(None, [x for x in atual if x != candidato])]
            else:
                remocoes = [(iid, [x for x in atual if x != iid])
                            for iid in atual if iid not in protegidas]
            for removido, parcial in remocoes:
                tentativa = list(parcial)
                tentativa.insert(min(alvo, len(tentativa)), candidato)
                if len(tentativa) != len(base) or len(tentativa) != len(set(tentativa)):
                    continue
                ids = set(tentativa)
                if any(grupo <= ids for grupo in conflitos):
                    continue
                if any(indice >= len(tentativa) or tentativa[indice] != iid
                       for iid, indice in protegidas.items()):
                    continue
                avaliacao = _avaliar_sequencia(
                    tentativa, slots, base_por_slot, comparacoes, z_minimo)
                if avaliacao is None:
                    continue
                efeito, erro, z, limite, precisao = avaliacao
                if z < z_minimo or limite <= avaliacao_atual[3] + 1e-12:
                    continue
                mudancas = sum(a != b for a, b in zip(tentativa, base))
                picks = [p.candidato_pick for p in h.parcelas]
                popularidade = statistics.mean(picks) if picks else 0.0
                chave = (limite, precisao, -mudancas, popularidade)
                opcoes.append((chave, tentativa, removido, h, avaliacao))
        if not opcoes:
            break
        _, atual, removido, h, avaliacao_atual = max(opcoes, key=lambda x: x[0])
        destino = _destino(h)
        alvo = slots.index(destino)
        protegidas[h.candidato] = alvo
        usadas.add((destino, h.candidato))
        acoes.append(AcaoSequencia(
            h.candidato, removido, destino,
            h.efeito_posterior, h.erro_posterior, h.z_posterior,
            h.efeito_posterior - z_minimo * h.erro_posterior,
            h.parcelas,
        ))

    if not acoes:
        return None
    efeito, erro, z, limite, precisao = avaliacao_atual
    return SequenciaOtimizada(
        tuple(zip(slots, atual)), tuple(acoes), efeito, erro, z, limite,
        precisao)


def otimizar_sequencias(
    resultado: Resultado,
    *,
    z_principal: float = 1.65,
    z_alternativa: float = 1.50,
    conflitos: tuple[frozenset[int], ...] = (frozenset({3033, 3036}),),
    max_alternativas: int = 3,
    exigir_fdr_itens: bool = False,
) -> PlanoSequencias:
    """Monta builds completas sem desfazer ações anteriores."""
    principal = _otimizar(
        resultado, z_minimo=z_principal, conflitos=conflitos,
        exigir_fdr=exigir_fdr_itens)
    alternativas = []
    bloqueadas: set[tuple[str, int]] = set()
    while len(alternativas) < max_alternativas:
        alternativa = _otimizar(
            resultado, z_minimo=z_alternativa, z_maximo=z_principal,
            conflitos=conflitos,
            exigir_fdr=exigir_fdr_itens,
            primeiras_bloqueadas=frozenset(bloqueadas))
        if alternativa is None:
            break
        chave = (alternativa.acoes[0].slot_destino,
                 alternativa.acoes[0].candidato)
        bloqueadas.add(chave)
        if (principal is None
                or alternativa.sequencia != principal.sequencia):
            alternativas.append(alternativa)
    return PlanoSequencias(principal, tuple(alternativas))


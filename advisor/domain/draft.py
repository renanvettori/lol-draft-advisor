"""Representa o draft e calcula a relevância dos inimigos."""

from __future__ import annotations

from dataclasses import dataclass, field

from advisor.domain.modelos import CatalogoJogo, Champion
from advisor.domain import regras


@dataclass
class Draft:
    """Um draft do ponto de vista de um jogador."""

    champion: Champion
    lane: str = ""
    enemies: list[Champion] = field(default_factory=list)
    allies: list[Champion] = field(default_factory=list)
    opponent: Champion | None = None  # oponente direto de rota, se conhecido
    rotas_inimigas: dict[int, str] = field(default_factory=dict)
    rotas_confirmadas: bool = False


@dataclass
class CompProfile:
    ad: list[Champion] = field(default_factory=list)
    ap: list[Champion] = field(default_factory=list)
    tanks: list[Champion] = field(default_factory=list)
    assassins: list[Champion] = field(default_factory=list)
    healers: list[Champion] = field(default_factory=list)
    hard_cc: list[Champion] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{len(self.ad)} AD / {len(self.ap)} AP"
            + (f", {len(self.tanks)} tanque(s)" if self.tanks else "")
            + (f", {len(self.assassins)} assassino(s)" if self.assassins else "")
            + (f", {len(self.healers)} com cura" if self.healers else "")
        )


def profile_enemies(enemies: list[Champion], catalogo: CatalogoJogo) -> CompProfile:
    """Resume a composição com os atributos do Data Dragon."""
    prof = CompProfile()
    for champ in enemies:
        info = catalogo.info_campeao(champ.key)
        tags = set(info.get("tags", []))
        stats = info.get("info", {})

        magic, attack = stats.get("magic", 0), stats.get("attack", 0)
        if {"Mage"} & tags or (magic > attack and "Marksman" not in tags):
            prof.ap.append(champ)
        else:
            prof.ad.append(champ)

        if "Tank" in tags or stats.get("defense", 0) >= 7:
            prof.tanks.append(champ)
        if "Assassin" in tags:
            prof.assassins.append(champ)
        if champ.key in regras.CURADORES:
            prof.healers.append(champ)
        if champ.key in regras.CAMPEOES_COM_CC_DURO:
            prof.hard_cc.append(champ)
    return prof


# O peso mede proximidade de rota. A página de matchup já captura as ameaças do
# campeão, então outros bônus duplicariam o sinal.

def relevancia(
    enemies: list[Champion],
    *,
    minha_rota: str,
    opponent: Champion | None,
    rotas: dict[int, str],
    pesos: dict[str, float],
) -> dict[int, tuple[float, list[str]]]:
    """Retorna o peso de cada inimigo e o motivo correspondente."""
    regras.validar_pesos(pesos)
    p = pesos

    fora: dict[int, tuple[float, list[str]]] = {}
    for champ in enemies:
        rota = rotas.get(champ.cid, "")

        motivos: list[str] = []
        if opponent is not None and champ.cid == opponent.cid:
            peso = p["oponente_de_rota"]
            motivos.append("seu oponente direto de rota")
        elif minha_rota == "bottom" and rota == "support":
            peso = p["mesma_rota"]
            motivos.append("suporte inimigo — te enfrenta na rota o jogo todo")
        elif minha_rota == "support" and rota == "bottom":
            peso = p["mesma_rota"]
            motivos.append("ADC inimigo — divide sua rota o jogo todo")
        elif rota and rota == minha_rota:
            peso = p["mesma_rota"]
            motivos.append("divide sua rota")
        else:
            peso = p["outra_rota"]
            motivos.append("outra rota")

        fora[champ.cid] = (peso, motivos)
    return fora


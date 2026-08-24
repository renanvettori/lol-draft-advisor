"""Aplica runas e feitiços sem escolher páginas do jogador para apagar."""

from __future__ import annotations

from dataclasses import dataclass

from advisor.client.lcu import LCU, LCUError
from advisor.domain.modelos import CatalogoJogo, PaginaRunas

PREFIXO = "Draft Advisor"


class SemEspaco(LCUError):
    """Não há slot livre e nenhuma página nossa para reaproveitar."""

    def __init__(self, paginas: list[dict]) -> None:
        self.paginas = paginas
        nomes = "\n".join(
            f"  id={p['id']}  {p['name']!r}" + ("  (em uso)" if p.get("current") else "")
            for p in paginas
        )
        super().__init__(
            "sem slot livre para criar a página de runas, e nenhuma página deste "
            "programa para reaproveitar.\n"
            "Escolha uma para ser sobrescrita e passe o id em --pagina-runas:\n"
            + nomes
        )


@dataclass
class Resultado:
    page_id: int
    nome: str
    acao: str  # "criada", "reaproveitada" ou "sobrescrita"


def _corpo(page: PaginaRunas, nome: str, static: CatalogoJogo) -> dict:
    """Monta o payload posicional de runas esperado pela LCU."""
    if len(page.primary) != 4 or len(page.secondary) != 2 or len(page.mods) != 3:
        raise LCUError(
            f"página de runas incompleta (primária={len(page.primary)}, "
            f"secundária={len(page.secondary)}, fragmentos={len(page.mods)}) — "
            "não vou enviar algo malformado para o client"
        )

    primary_style = static.estilo_da_runa(page.primary[0])
    sub_style = static.estilo_da_runa(page.secondary[0])
    if not primary_style or not sub_style:
        raise LCUError("não consegui determinar as árvores de runa a partir dos ids")

    return {
        "name": nome[:75],
        "primaryStyleId": primary_style,
        "subStyleId": sub_style,
        "selectedPerkIds": [*page.primary, *page.secondary, *page.mods],
        "current": True,
    }


def aplicar(
    api: LCU,
    page: PaginaRunas,
    champ_name: str,
    static: CatalogoJogo,
    *,
    sobrescrever_id: int | None = None,
) -> Resultado:
    """Cria (ou atualiza) a página de runas e a deixa selecionada."""
    nome = f"{PREFIXO} — {champ_name}"
    corpo = _corpo(page, nome, static)

    paginas = api.get("/lol-perks/v1/pages") or []
    editaveis = [p for p in paginas if p.get("isEditable")]
    nossas = [p for p in editaveis if str(p.get("name", "")).startswith(PREFIXO)]

    if nossas:
        alvo = nossas[0]
        api.put(f"/lol-perks/v1/pages/{alvo['id']}", corpo)
        api.put("/lol-perks/v1/currentpage", alvo["id"])
        return Resultado(alvo["id"], nome, "reaproveitada")

    inventario = api.get("/lol-perks/v1/inventory") or {}
    if inventario.get("canAddCustomPage"):
        criada = api.post("/lol-perks/v1/pages", corpo) or {}
        return Resultado(criada.get("id", 0), nome, "criada")

    if sobrescrever_id is None:
        raise SemEspaco(editaveis)

    alvo = next((p for p in editaveis if p.get("id") == sobrescrever_id), None)
    if alvo is None:
        raise LCUError(f"página id={sobrescrever_id} não existe ou não é editável")

    api.put(f"/lol-perks/v1/pages/{sobrescrever_id}", corpo)
    api.put("/lol-perks/v1/currentpage", sobrescrever_id)
    return Resultado(sobrescrever_id, nome, "sobrescrita")


FLASH = 4


def aplicar_feiticos(api: LCU, ids: list[int], *, flash_no_d: bool = True) -> list[int]:
    """Seleciona os feitiços e, se configurado, mantém Flash na tecla D."""
    if len(ids) != 2:
        raise LCUError(f"esperava dois feitiços, recebi {ids}")

    ordenados = list(ids)
    if flash_no_d and FLASH in ordenados and ordenados[0] != FLASH:
        ordenados.reverse()

    api._request("PATCH", "/lol-champ-select/v1/session/my-selection",
                 {"spell1Id": ordenados[0], "spell2Id": ordenados[1]})
    return ordenados


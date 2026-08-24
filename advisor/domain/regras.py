"""Classificações usadas apenas no resumo visual do draft."""

CURADORES = {
    "Aatrox", "Briar", "DrMundo", "Fiora", "Ivern", "Nami", "Nasus",
    "Renata", "Seraphine", "Sett", "Sona", "Soraka", "Swain", "Sylas",
    "Taric", "Vladimir", "Warwick", "Yuumi", "Zac",
}

CAMPEOES_COM_CC_DURO = {
    "Malzahar", "Warwick", "Skarner", "Urgot", "TahmKench", "Morgana",
    "Lissandra",
}

CHAVES_RELEVANCIA = {
    "oponente_de_rota", "mesma_rota", "outra_rota",
}


def validar_pesos(pesos: dict[str, float]) -> None:
    faltando = CHAVES_RELEVANCIA - pesos.keys()
    if faltando:
        raise ValueError(
            "pesos de relevância ausentes: " + ", ".join(sorted(faltando)))


from fire.api.model import (
    PunktSamling,
)
import fire.cli


def er_punktsamling_unik(punktsamling_A: PunktSamling) -> dict[list]:
    """
    Undersøg om en Punktsamling A udgør en unik samling af punkter.

    Givet Punktsamling A (herved forstås mængden af punkter i punktsamlingen) undersøges
    der for alle andre Punktsamlinger B flg:
        1. Er A lig med B
        2. Er A en delmængde af B (Er A et "subset" af B)
        3. Er B en delmængde af A (Er A et "superset" af B)
    """
    if not isinstance(punktsamling_A, PunktSamling):
        raise TypeError("'punktsamling' er ikke en instans af PunktSamling")

    # Mængde af punkter i Punktsamling A
    punkter_A = {pkt.ident for pkt in punktsamling_A.punkter}

    alle_punktsamlinger = fire.cli.firedb.hent_alle_punktsamlinger()

    # Initialiser dict-over-list
    dol = {"Lig med": [], "Subset af": [], "Superset af": []}
    for punktsamling_B in alle_punktsamlinger:

        # Lad være med at sammenligne Punktsamlingen med sig selv
        if punktsamling_A.navn == punktsamling_B.navn:
            continue

        # Mængde af punkter i Punktsamling B
        punkter_B = {pkt.ident for pkt in punktsamling_B.punkter}

        if punkter_A == punkter_B:
            dol["Lig med"].append(punktsamling_B.navn)
        elif punkter_A.issubset(punkter_B):
            dol["Subset af"].append(punktsamling_B.navn)
        elif punkter_A.issuperset(punkter_B):
            dol["Superset af"].append(punktsamling_B.navn)

    return dol

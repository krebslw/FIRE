print("importerede cli.info._infopunkt")
import click
from sqlalchemy.orm.exc import NoResultFound

import fire.cli
from fire.cli.info_light import infolight
from fire.ident import klargør_ident_til_søgning
from fire.cli.exceptions import (
    YndefuldeFejl,
)
from fire.cli.info_light.helpers import (
    punkt_fuld_rapport,

)

# Dato-format til kommandolinie-argument.
DATE_FORMAT = "%d-%m-%Y"


@infolight.command()
@click.option(
    "-K",
    "--koord",
    default="",
    help="ts: Udskriv også tidsserier; alle: Udskriv også historiske koordinater; ingen: Udelad alle",
)
@click.option(
    "-O",
    "--obs",
    is_flag=False,
    default="",
    help="niv/alle: Udskriv observationer",
)
@click.option(
    "-D",
    "--detaljeret",
    is_flag=True,
    default=False,
    help="Udskriv også sjældent anvendte elementer",
)
@click.option(
    "-H",
    "--historik",
    is_flag=True,
    default=False,
    help="Udskriv også ikke-gældende (historiske) elementer",
)
@click.option(
    "-n",
    "--antal",
    is_flag=False,
    default=20,
    help="Begræns antallet af punkter der udskrives",
)
@fire.cli.default_options()
@click.argument("ident")
def punkt(
    ident: str,
    obs: str,
    koord: str,
    detaljeret: bool,
    historik: bool,
    antal: int,
    **kwargs,
) -> None:
    """
    Vis al tilgængelig information om et fikspunkt.

    **IDENT** kan være enhver form for navn et punkt er kendt som, blandt andet
    GNSS stationsnummer, G.I./G.M.-nummer, refnr, landsnummer, uuid osv.

    Søgningen er delvist versalfølsom, men tager højde for minuskler, udeladte
    punktummer og manglende foranstillede nuller, i ofte forekommende, let
    genkendelige tilfælde (GNSS-id, GI/GM-numre, lands- og købstadsnumre).

    Anfører man ikke specifikke tilvalg vises kun basale dele: Attributter og
    punktbeskrivelser, tilknyttede skitser og billeder, samt gældende koordinater.
    Herudover kan tilvælges yderligere information med argumenterne beskrevet herunder.

    Tilvalg ``--detaljer/-D`` udvider med sjældnere brugte informationer.

    Tilvalg ``--koord/-K`` kan sættes til ts, alle, ingen - eller kombinationer:
    fx ``ts,alle``. ``alle`` tilvælger historiske koordinater, ``ts`` tilvælger
    tidsseriekoordinater, ``ingen`` fravælger alle koordinatoplysninger.

    Koordinatlisten viser med grønt de gældende koordinater, og med rødt ældre,
    ikke-aktuelle koordinater. Samme information angives med et tegn før datoen:

    \b
        * gældende koordinat
        . ikke-aktuel koordinat
        X fejlmeldt koordinat

    Koordinates koordinatsystem angives med en SRID (Spatial Reference ID), typisk
    en EPSG-kode. Disse kan slås op med ``fire info srid``.
    Tal i parentes efter en koordinat angiver spredningen, givet i milimeter, på koordinaten.
    For fler-dimensionelle koordinater gives spredning på alle koordinatens komponenter.

    Tilvalg ``--obs/-O`` kan sættes til ``alle`` eller ``niv``. Begge tilvælger visning
    af observationer til/fra det søgte punkt. P.t. understøttes kun visning af
    nivellementsobservationer.

    Af observationslisten fremgår de væsentligste informationer om en given observation.
    Vises linjen med rødt og et foranstillet X betyder det at observationen er fejlmeldt.

    Hvis der findes skitser eller billedmateriale for et punkt angives disse
    under sektionen "Grafik" og kan vises med ``fire grafik`` kommandoen.
    """
    print("kører infolight punkt")
    ident = klargør_ident_til_søgning(ident)

    with YndefuldeFejl(NoResultFound, f"Kunne ikke finde {ident}"):
        punkter = fire.cli.firedb.hent_punkter(
            ident, inkluder_historiske_identer=historik
        )

    # Succesfuld søgning - vis hvad der blev fundet
    n = len(punkter)
    for i, punkt in enumerate(punkter):
        if i == antal:
            break
        punkt_fuld_rapport(
            punkt, punkt.ident, i + 1, n, obs, koord, detaljeret, historik
        )
    if n > antal:
        fire.cli.print(
            f"Yderligere {n-antal} punkter fundet. Brug tilvalg '-n {n}' for at vise alle."
        )

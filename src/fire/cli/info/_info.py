import datetime
import io
import itertools
import re
import textwrap
from typing import List
import zipfile

import click
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from sqlalchemy import not_, or_
from pyproj import CRS
from pyproj.exceptions import CRSError

import fire.cli
from fire.cli.info import info
from fire.ident import klargør_ident_til_søgning
from fire.io.geojson import skriv_sagsrapport_geojson
from fire.api.model import (
    EventType,
    EVENTTYPER,
    Sag,
    Sagsevent,
    Punkt,
    PunktInformation,
    PunktInformationType,
    PunktSamling,
    Koordinat,
    Observation,
    GeometriskKoteforskel,
    TrigonometriskKoteforskel,
    Boolean,
    Srid,
    Tidsserie,
    Grafik,
)
from fire.cli.click_types import Datetime
from fire.cli.exceptions import (
    AfbrydFejl,
    IntetAtGøre,
    YndefuldeFejl,
)
from fire.cli.pretty_tables import (
    klargør_celle,
    print_tabel,
    generer_rapporttabel,
)
from rich.table import Table

# Dato-format til kommandolinie-argument.
DATE_FORMAT = "%d-%m-%Y"


def observation_linje(
    obs: GeometriskKoteforskel | TrigonometriskKoteforskel,
) -> tuple[list[str], str]:
    if obs.observationstypeid > 2:
        return [], None

    if obs.slettet:
        return [], None

    metode = "G" if obs.observationstypeid == 1 else "T"
    tid = obs.observationstidspunkt.strftime("%Y-%m-%d %H:%M")

    # Kun GeometriskKoteForskel har disse to attributter.
    # Hvis observationen er Trigonometrisk skrives 0 i stedet.
    præs = getattr(obs, "præcisionsnivellement", 0)
    eta_1 = getattr(obs, "eta_l", 0.0)

    row = [
        "X" if obs.fejlmeldt else "",
        f"{metode} {præs} {tid}",
        f"{obs.koteforskel:+09.6f}",
        f"{obs.nivlængde:6.1f}",
        f"{obs.opstillinger:2}",
        obs.opstillingspunkt.ident,
        obs.sigtepunkt.ident,
        f"{obs.spredning_afstand:3.1f}",
        f"{obs.spredning_centrering:4.2f}",
        f"{eta_1:+07.2f}",
        f"{obs.gruppe:6}",
        f"{obs.objektid:6}",
    ]

    # set row styles
    style = "" if not obs.fejlmeldt else "red"

    return row, style


def koordinat_linje(koord: Koordinat) -> tuple[list[str], str]:
    """
    Konstruer koordinatoutput i overensstemmelse med koordinatens dimensionalitet,
    enhed og proveniens.
    """
    native_or_transformed = "t"
    if koord.transformeret == Boolean.FALSE:
        native_or_transformed = "n"
    tid = koord.t.strftime("%Y-%m-%d %H:%M")
    srid = f"{(koord.srid.kortnavn or koord.srid.name)}"

    # Se i proj.db: Er koordinatsystemet lineært eller vinkelbaseret?
    try:
        grader = False
        if CRS(koord.srid.name).axis_info[0].unit_name in ("degree", "radian"):
            grader = True
    except CRSError:
        # ignorer pyproj.exceptions.CRSError: Antag at ukendte koordinatsystemers enheder
        # er lineære, bortset fra specialtilfældet NAD83G
        if koord.srid.name == "GL:NAD83G":
            grader = True

    if koord.x is not None and koord.y is not None:
        dimensioner = 3 if koord.z is not None else 2
    else:
        dimensioner = 1 if koord.z is not None else 0

    if dimensioner == 1:
        xyz = f"{koord.z:.5f} ({koord.sz:.0f})"
    if dimensioner == 2:
        if grader:
            xyz = f"{koord.x:.10f}, {koord.y:.10f} ({koord.sx:.0f}, {koord.sy:.0f})"
        else:
            xyz = f"{koord.x:.4f}, {koord.y:.4f} ({koord.sx:.0f}, {koord.sy:.0f})"

    if dimensioner == 3:
        xyz = f"{koord.x:.10f}, {koord.y:.10f}, {koord.z:.5f}"
        if koord.sx is not None and koord.sy is not None and koord.sz is not None:
            xyz += f" ({koord.sx:.0f}, {koord.sy:.0f}, {koord.sz:.0f})"

    markør = "*"
    style = "green"
    if koord.registreringtil is not None:
        markør = "X" if koord.fejlmeldt else "."
        style = "red"

    row = [markør, tid, srid, native_or_transformed, xyz]

    return row, style


def punktinfo_linje(punktinfo: PunktInformation) -> tuple[list[str], str]:
    """Generér en tabelrække til punktinforapport."""
    tekst = punktinfo.tekst or ""
    # tal kan godt være 0, derfor tjekkes explicit for Noneness
    tal = punktinfo.tal if punktinfo.tal is not None else ""

    # marker slukkede punktinformationer med rød tekst og et minus tv for linjen
    style, markør = "", ""
    if punktinfo.registreringtil:
        style, markør = "red", "-"
    row = [f"{markør}{punktinfo.infotype.name}", f"{tekst}{tal}"]
    return row, style


def punktinforapport(
    punkt: Punkt, historik: bool = False, detaljeret: bool = False
) -> None:
    """
    Hjælpefunktion for 'punkt_fuld_rapport': Udskriv formateret punktinfo-tabel
    """
    tbl = generer_rapporttabel(
        title=None,
        show_header=False,
        padding=(0, 2, 0, 2),
    )

    # Tilføj Lokation og Oprettelsesdato
    try:
        for geometriobjekt in punkt.geometriobjekter:
            # marker slukkede geometriobjekter med rød tekst og et minus tv for linjen
            if geometriobjekt.registreringtil:
                if not historik:
                    continue
                tbl.add_row("-Lokation", f"{geometriobjekt.geometri}", style="red")
            else:
                tbl.add_row("Lokation", f"{geometriobjekt.geometri}")
    except Exception:
        pass

    tbl.add_row("Oprettelsesdato", f"{punkt.registreringfra}")

    # Tilføj de almindelige punktinformationer
    for info in punkt.punktinformationer:
        if info.registreringtil and not historik:
            continue
        row, style = punktinfo_linje(info)
        tbl.add_row(*row, style=style)

    # Tilføj detaljerede informationer
    if detaljeret:
        tbl.add_row("uuid", f"{punkt.id}")
        tbl.add_row("objekt-id", f"{punkt.objektid}")
        tbl.add_row("sagsid", f"{punkt.sagsevent.sagsid}")
        tbl.add_row("sagsevent-fra", f"{punkt.sagseventfraid}")
        if punkt.sagseventtilid is not None:
            tbl.add_row(f"sagsevent-til", f"{punkt.sagseventtilid}")

    print_tabel(tbl, align="left")


def koordinatrapport(
    koordinater: List[Koordinat], options: str, historik: bool
) -> None:
    """
    Hjælpefunktion for 'punkt_fuld_rapport': Udskriv formateret koordinatliste
    """
    # Sorter efter SRID, koordinattidsspunkt og registreringfra. Sidstnævnte er relevant i særlige
    # tilfælde hvor to identiske Koordinater findes i databasen, hvoraf den ene er fejlmeldt. Se
    # fx 24-09-09091 i februar 2024. De to identiske koter skyldes at 2020-koten ved en fejl ikke var
    # blevet indlæst i 2020 og derfor blev indsat på bagkant i 2024 med det resultat at den stod som
    # gældende kote i stedet for den nye 2024-kote. Ved at fejlmelde den først indlæste 2024-kote var
    # det muligt at indsætte samme kote fra 2024 igen og dermed lade den være den gældende.
    koordinater.sort(
        key=lambda x: (x.srid.name, x.t.strftime("%Y-%m-%dT%H:%M"), x.registreringfra),
        reverse=True,
    )

    ts = True if "ts" in options.split(",") else False
    alle = True if "alle" in options.split(",") else False

    tbl = generer_rapporttabel(title="--- Koordinater ---", show_header=False)
    for koord in koordinater:
        tskoord = koord.srid.name.startswith("TS:")
        if tskoord and not ts:
            continue
        if koord.registreringtil is not None:
            if not (alle or historik):
                continue

        row, style = koordinat_linje(koord)
        tbl.add_row(*row, style=style)

    print_tabel(tbl, align="left")


def observationsrapport(
    observationer_til: List[Observation],
    observationer_fra: List[Observation],
    options: str,
    opt_detaljeret: bool,
) -> None:
    """
    Hjælpefunktion for 'punkt_fuld_rapport': Udskriv formateret observationsliste
    """
    # p.t. er kun nivellementsobservationer understøttet
    if options not in ["niv", "alle"]:
        return

    n_obs_til = len(observationer_til)
    n_obs_fra = len(observationer_fra)
    if n_obs_til + n_obs_fra == 0:
        return

    if n_obs_til > 0:
        punktid = observationer_til[0].sigtepunktid
    else:
        punktid = observationer_fra[0].opstillingspunktid

    observationer = [
        obs
        for obs in observationer_fra + observationer_til
        if obs.observationstypeid in [1, 2]
    ]

    # "gruppe"-elementet er meningsfyldt for klassiske retningsmålinger
    # men kun begrænset relevant for nivellementsobservationer, hvor den
    # dog historisk er blevet populeret med journalsideinformation.
    # I disse tilfælde er det en nyttig ekstra parameter til relevanssorteringen
    # nedenfor. I tilfælde hvor "gruppe" ikke er sat sætter vi den til 0.
    # Dermed undgås sammenligning af inkompatible datatyper i sorteringen.
    for obs in observationer:
        if obs.gruppe is None:
            obs.gruppe = 0

    # Behjertet forsøg på at sortere de udvalgte observationer,
    # så de giver bedst mulig mening for brugeren: Først præs,
    # så andre, og indenfor hver gruppe baglæns kronologisk og med
    # frem/tilbage par så vidt muligt grupperet. Det er ikke nemt!
    observationer.sort(
        key=lambda x: (
            (x.value7 if x.observationstypeid == 1 else 0),
            (x.observationstidspunkt.year),
            (x.gruppe),
            (x.sigtepunktid if x.sigtepunktid != punktid else x.opstillingspunktid),
            (x.observationstidspunkt),
        ),
        reverse=True,
    )

    n_vist = len(observationer)
    if n_vist == 0:
        return

    kolonnenavne = (
        "",
        "[Trig/Geom][Præs][T]",
        "dH",
        "L",
        "N",
        "Fra",
        "Til",
        "ne",
        "d",
        "eta",
        "grp",
        "id",
    )

    rows_styles = [observation_linje(obs) for obs in observationer]

    tbl = generer_rapporttabel(
        *kolonnenavne,
        title="--- Observationer ---",
        rows_styles=rows_styles,
    )

    if not opt_detaljeret:
        print_tabel(tbl, align="left")
        return

    # Find ældste og yngste observation
    min_obs = datetime.datetime(9999, 12, 31, 0, 0, 0)
    max_obs = datetime.datetime(1, 1, 1, 0, 0, 0)
    for obs in itertools.chain(observationer_fra, observationer_til):
        if obs.observationstidspunkt < min_obs:
            min_obs = obs.observationstidspunkt
        if obs.observationstidspunkt > max_obs:
            max_obs = obs.observationstidspunkt

    tbl.caption = (
        f"  Observationer ialt:  {n_obs_til + n_obs_fra}\n"
        f"  Observationer vist:  {n_vist}\n"
        f"  Ældste observation:  {min_obs}\n"
        f"  Nyeste observation:  {max_obs}\n"
    )
    tbl.caption_style = ""
    tbl.caption_justify = "left"
    print_tabel(tbl, align="left")


def punktsamlingsrapport(punktsamlinger: list[PunktSamling], id: str = None):
    """
    Hjælpefunktion for funktionerne punkt_fuld_rapport og punktsamling.
    """

    kolonnenavne = ("Navn", "Jessenpunkt", "Antal punkter", "Antal tidsserier")
    tbl = generer_rapporttabel(
        *kolonnenavne,
        title="--- Punktsamlinger ---",
    )

    punktsamlinger = [ps for ps in punktsamlinger if ps.registreringtil is None]
    # Sortér Punktsamlinger efter Jessennummer, dernæst efter Punktsamlingsnavn
    punktsamlinger.sort(key=lambda x: (x.jessenpunkt.jessennummer, x.navn))

    for ps in punktsamlinger:
        style = ""
        if ps.jessenpunkt.id == id:
            style = "green"

        row = [
            ps.navn,
            ps.jessenpunkt.jessennummer,
            len(ps.punkter),
            len(ps.tidsserier),
        ]
        tbl.add_row(*[klargør_celle(c) for c in row], style=style)

    print_tabel(tbl, align="left")


def tidsserierapport(tidsserier: list[Tidsserie]):
    """
    Hjælpefunktion for funktionerne punkt_fuld_rapport og punktsamling.
    """

    kolonnenavne = ["Navn", "Antal datapunkter", "Type", "Referenceramme"]
    tbl = generer_rapporttabel(
        *kolonnenavne,
        title="--- Tidsserier ---",
    )

    def tidsserietype(tstype):
        if tstype == 1:
            return "GNSS"
        elif tstype == 2:
            return "Højde"

    for ts in tidsserier:
        if ts.registreringtil is not None:
            continue

        row = [ts.navn, len(ts), tidsserietype(ts.tstype), ts.referenceramme]

        tbl.add_row(*[klargør_celle(c) for c in row])

    print_tabel(tbl, align="left")


def punkt_fuld_rapport(
    punkt: Punkt,
    ident: str,
    i: int,
    n: int,
    opt_obs: str,
    opt_koord: str,
    opt_detaljeret: bool,
    opt_historik: bool,
) -> None:
    """
    Rapportgenerator for funktionen 'punkt' nedenfor.
    """

    # Header
    fire.cli.print("")
    fire.cli.print("-" * 80)
    if n > 1:
        fire.cli.print(f" PUNKT {punkt.ident} ({i}/{n})", bold=True)
    else:
        fire.cli.print(f" PUNKT {punkt.ident}", bold=True)
    fire.cli.print("-" * 80)

    # Geometri, fire-id, oprettelsesdato og PunktInformation håndteres
    # under et, da det giver et bedre indledende overblik
    punktinforapport(punkt, opt_historik, opt_detaljeret)

    if punkt.grafikker:
        tbl = generer_rapporttabel(
            show_header=False,
            title="--- Grafik ---",
            padding=(0, 2, 0, 2),
        )
        for grafik in punkt.grafikker:
            if grafik.registreringtil:
                continue
            tbl.add_row(f"{grafik.type.value.title()}", f"{grafik.filnavn}")

        fire.cli.print("")
        print_tabel(tbl, align="left")

    # Koordinater og observationer klares af specialiserede hjælpefunktioner
    if "ingen" not in opt_koord.split(","):
        fire.cli.print("")
        koordinatrapport(punkt.koordinater, opt_koord, opt_historik)

    if opt_obs != "":
        fire.cli.print("")
        observationsrapport(
            punkt.observationer_til, punkt.observationer_fra, opt_obs, opt_detaljeret
        )

    if punkt.punktsamlinger:
        fire.cli.print("")
        punktsamlingsrapport(punkt.punktsamlinger, punkt.id)

    if punkt.tidsserier:
        fire.cli.print("")
        tidsserierapport(punkt.tidsserier)


@info.command()
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


@info.command()
@click.option(
    "-T",
    "--ts",
    is_flag=True,
    default=False,
    help="Udskriv også tidsrækkedefinitioner",
)
@fire.cli.default_options()
@click.argument("srid", required=False)
def srid(srid: str, ts: bool, **kwargs):
    """
    Information om et givent SRID (Spatial Reference ID).

    Eksempler på SRID'er: EPSG:25832, DK:SYS34, TS:81013

    Anføres SRID ikke gives liste af mulige SRID. Som standard uden lokale
    tidsseriekoordinatsystemer.

    Tilvalg ``-T/--ts`` kan kun vælges uden angiven SRID. Udvider listen med
    lokale tidsseriekoordinatsystemer.
    """
    if not srid:
        if ts:
            srid_db = fire.cli.firedb.session.query(Srid).order_by(Srid.name).all()
        else:
            srid_db = (
                fire.cli.firedb.session.query(Srid)
                .filter(not_(Srid.name.like("TS:%")))
                .order_by(Srid.name)
                .all()
            )

        for srid_item in srid_db:
            fire.cli.print(f"{srid_item.name:20}" + srid_item.beskrivelse)

    else:
        srid_name = srid

        with YndefuldeFejl(NoResultFound, f"{srid_name} ikke fundet!"):
            srid = fire.cli.firedb.hent_srid(srid_name)

        fire.cli.print("--- SRID ---", bold=True)
        fire.cli.print(f" Navn:       :  {srid.name}")
        fire.cli.print(f" Kort navn:  :  {srid.kortnavn or ''}")
        fire.cli.print(f" Beskrivelse :  {srid.beskrivelse}")


@info.command()
@fire.cli.default_options()
@click.argument("infotype", required=False, default="")
@click.option(
    "-s",
    "--søg",
    is_flag=True,
    default=False,
    help="Generel søgning i både typenavn og beskrivelse",
)
def infotype(infotype: str, søg: bool, **kwargs):
    """
    Information om en punktinformationstype.

    Eksempler på punktinformationstyper: ``IDENT:GNSS``, ``AFM:diverse``,
    ``ATTR:beskrivelse``.

    Angives **INFOTYPE** ikke vises en liste med alle tilgængelige punktinfotyper.
    Denne liste kan snævres ind ved at angive starten af et navn på en punktinfotype,
    fx "IDENT" eller "attr".

    Med tilvalg ``--søg/-s`` vises punktinfotyper og tilhørende beskrivelser,
    for alle de punktinfotyper, som matcher INFOTYPE et vilkårligt sted i
    enten navn eller beskrivelse.
    """
    with YndefuldeFejl(NoResultFound, f"{infotype} ikke fundet!"):
        if søg:
            punktinfotyper = (
                fire.cli.firedb.session.query(PunktInformationType)
                .filter(
                    or_(
                        PunktInformationType.name.ilike(f"%{infotype}%"),
                        PunktInformationType.beskrivelse.ilike(f"%{infotype}%"),
                    )
                )
                .order_by(PunktInformationType.name)
                .all()
            )
        else:
            punktinfotyper = (
                fire.cli.firedb.session.query(PunktInformationType)
                .filter(PunktInformationType.name.ilike(f"{infotype}%"))
                .order_by(PunktInformationType.name)
                .all()
            )

        if not punktinfotyper:
            raise NoResultFound

    if len(punktinfotyper) == 1:
        pit = punktinfotyper[0]
        fire.cli.print("--- PUNKTINFOTYPE ---", bold=True)
        fire.cli.print(f"  Navn        :  {pit.name}")
        fire.cli.print(f"  Beskrivelse :  {pit.beskrivelse}")
        fire.cli.print(f"  Type        :  {pit.anvendelse}")
        return

    if infotype == "":
        fire.cli.print("Følgende punktinfotyper er tilgængelige:\n")
    else:
        fire.cli.print(f'"{infotype}" matcher følgende punktinfotyper:\n')

    if not søg:
        for punktinfotype in punktinfotyper:
            fire.cli.print(punktinfotype.name)
        return

    # undgå at max() bomber ved manglende match
    if len(punktinfotyper) == 0:
        fire.cli.print("...")
        return

    bredde = max([len(p.name) for p in punktinfotyper]) + 2
    for punktinfotype in punktinfotyper:
        besk = punktinfotype.beskrivelse.replace("-\n", "").replace("\n", " ").strip()
        fire.cli.print(
            f"{punktinfotype.infotypeid:{-4}} {punktinfotype.name:{bredde}} {besk}"
        )


@info.command()
@fire.cli.default_options()
@click.argument("obstype", required=False)
def obstype(obstype: str, **kwargs):
    """
    Information om en given observationstype.

    Anføres **OBSTYPE** ikke gives liste af mulige obstyper.
    """
    if not obstype:
        obstyper = fire.cli.firedb.hent_observationstyper()
        for obstype in obstyper:
            beskrivelse = textwrap.shorten(
                obstype.beskrivelse, width=70, placeholder="..."
            )
            fire.cli.print(f"{obstype.name:30}{beskrivelse}")

        return 0

    ot = fire.cli.firedb.hent_observationstype(obstype)
    if ot is None:
        AfbrydFejl(f"{obstype} ikke fundet!")

    fire.cli.print("--- OBSERVATIONSTYPE ---", bold=True)
    fire.cli.print(f"  Navn        :  {ot.name}")
    fire.cli.print(f"  Beskrivelse :  {ot.beskrivelse}")

    for navn, værdi in sorted(vars(ot).items()):
        if navn.startswith("value") and værdi is not None:
            fire.cli.print(f"  {navn.replace('value','Værdi')}      :  {værdi}")

    fire.cli.print(f"  Sigtepunkt? :  {ot.sigtepunkt.value.title()}")


def _optæl_punkter_i_sagsevents(sagsevent_liste: list[Sagsevent]) -> dict[set]:
    """
    Laver en optælling af unikke punkter som er berørt af en liste af sagseventets.

    Der grupperes på kategorier som giver mening ift. kommunal afrapportering.

    Returner en dict med unikke punktid'er for hver af følgende eventtyper:

    Oprettet: Alle nyetablerede punkter
    Tabtgået: Alle tabtmeldte punkter
    Genfundet: Alle genfundne punkter
    Beregnet: Alle punkter med nyberegnede koordinater
    Observeret: Alle observerede punkter
    Besøgt: Alle punkter som har fået redigeret Punktinfo eller indgår i nogen af
    ovenstående kategorier.

    Fx. vil et Sagsevent som har redigeret punktbeskrivelsen og oprettet attributten
    NET:5D for punktet med id 'aabbccdd', samt genfundet punket 'eeffgghh' returnere
    dicten:

    {
        'oprettet': {},
        'tabtgået': {},
        'genfundet': {'eeffgghh'},
        'beregnet': {},
        'observeret': {},
        'besøgt': {'aabbccdd', 'eeffgghh'},
    }

    """

    # Tag sagsevents fra input-liste og gruppér dem
    aggregeret_sagsevent = _grupper_sagsevents(sagsevent_liste)

    stats = dict(
        oprettet=set(),
        tabtgået=set(),
        genfundet=set(),
        beregnet=set(),
        observeret=set(),
        besøgt=set(),
    )

    stats["oprettet"] = {p.id for p in aggregeret_sagsevent["punkter"]}

    for pi in aggregeret_sagsevent["punktinformationer"]:
        stats["besøgt"].add(pi.punktid)

        # Alle dem hvor man har tilføjet attributten ATTR:tabtgået registreres som tabtgået
        if pi.infotype.name == "ATTR:tabtgået":
            stats["tabtgået"].add(pi.punktid)

    for pi in aggregeret_sagsevent["punktinformationer_slettede"]:
        stats["besøgt"].add(pi.punktid)

        # Alle dem hvor man har fjernet attributten ATTR:tabtgået registreres som genfundet
        if pi.infotype.name == "ATTR:tabtgået":
            stats["genfundet"].add(pi.punktid)

    # Fratræk overlap mellem genfundne og tabtgåede
    overlap = stats["tabtgået"].intersection(stats["genfundet"])
    stats["tabtgået"].difference_update(overlap)
    stats["genfundet"].difference_update(overlap)

    stats["beregnet"] = {k.punktid for k in aggregeret_sagsevent["koordinater"]}

    stats["observeret"] = {
        op
        for o in aggregeret_sagsevent["observationer"]
        for op in [o.sigtepunktid, o.opstillingspunktid]
    }

    # Oprettede, beregnede eller observerede punkter tæller også som besøgt.
    stats["besøgt"].update(stats["oprettet"])
    stats["besøgt"].update(stats["beregnet"])
    stats["besøgt"].update(stats["observeret"])

    return stats


def _grupper_sagsevents(sagsevent_liste: list[Sagsevent]) -> dict[set]:
    """
    Samler alle FikspunktregisterObjekter der blev indsat eller slettet af Sagen.

    Der returneres en `dict` som indeholder sættet af indsatte eller slettede
    FikspunktregisterObjekter for hver af de nedenstående objekttyper:

    {
        punkter : ...
        geometriobjekter : ...
        beregninger: ...
        koordinater: ...
        observationer: ...
        punktinformationer: ...
        grafikker: ...
        punktsamlinger: ...
        tidsserier: ...
        punkter_slettede: ...
        geometriobjekter_slettede: ...
        beregninger_slettede: ...
        koordinater_slettede: ...
        observationer_slettede: ...
        punktinformationer_slettede: ...
        grafikker_slettede: ...
        punktsamlinger_slettede: ...
        tidsserier_slettede: ...
    }

    Der fjernes overlap mellem indsatte og slettede Objekter. Fx. hvis
    Punktinformationen "NET:5D" først er blevet indsat ved en fejl og dernæst slettet,
    så vil den information ikke fremgå af oversigten.

    (Dog er det lidt mere besværligt "den anden vej", da det indebærer en gruppering på
    punktinfotypen). Dvs. hvis punktinformationen findes i forvejen, og den så slettes ved
    en fejl, og dernæst tilføjes igen. Dette VIL fremgå af oversigten. Dog foretages der
    netop en gruppering på ATTR:tabtgået, så denne vil fremtræde helt korrekt.

    """
    # Initialisér dict
    fikspunktregisterobjekter = {
        obj: set()
        for _, objekter in EVENTTYPER.items()
        for obj in objekter
        if obj is not None
    }

    for sagsevent in sagsevent_liste:
        for dataobjekt in EVENTTYPER[sagsevent.eventtype]:
            if dataobjekt is None:
                continue
            fikspunktregisterobjekter[dataobjekt].update(
                set(getattr(sagsevent, dataobjekt))
            )

            # Det er muligt at indsætte/redigere en punktinformation som findes i forvejen.
            # Når dette sker vil sagseventet have eventtype=PUNKTINFO_TILFOEJET, men både
            # være mappet til "punktinformationer" og "punktinformationer_slettede".
            # Nedenstående medtager de slettede punktinfos.
            if sagsevent.eventtype == EventType.PUNKTINFO_TILFOEJET:
                fikspunktregisterobjekter["punktinformationer_slettede"].update(
                    set(getattr(sagsevent, "punktinformationer_slettede"))
                )

    # Træk overlap mellem oprettede og slettede objekter fra (det betyder at fx en punktinformation både er blevet tilføjet og slettet)
    for k, v in fikspunktregisterobjekter.items():
        try:
            overlap = fikspunktregisterobjekter[k].intersection(
                fikspunktregisterobjekter[f"{k}_slettede"]
            )
        except KeyError:
            continue
        fikspunktregisterobjekter[k].difference_update(overlap)
        fikspunktregisterobjekter[f"{k}_slettede"].difference_update(overlap)

    return fikspunktregisterobjekter


@info.command()
@fire.cli.default_options()
@click.argument("sagsid", required=False)
@click.option(
    "-df",
    "--fra",
    help=f"Hent sager fra og med denne dato. Angives på formen {DATE_FORMAT}.",
    required=False,
    type=Datetime(format=DATE_FORMAT),
)
@click.option(
    "-dt",
    "--til",
    help=f"Hent sager til, men ikke med, denne dato. Angives på formen {DATE_FORMAT}.",
    required=False,
    type=Datetime(format=DATE_FORMAT),
)
@click.option(
    "-a",
    "--aktive",
    is_flag=True,
    default=False,
    help="Hent kun aktive sager. Som standard hentes alle sager (også lukkede).",
)
@click.option(
    "-r",
    "--rapport",
    type=str,
    default=None,
    is_flag=False,
    flag_value="",
    help="Udskriv rapport over fremsøgte sager. Gives et navn på rapporten skrives også en geojson-fil som oversigt.",
)
def sag(
    sagsid: str,
    fra: datetime.datetime,
    til: datetime.datetime,
    aktive: bool,
    rapport: str,
    **kwargs,
):
    """
    Fremsøg information om en eller flere sager.

    Fremsøger sager ud fra de angivne filterkriterier, og viser en liste over sagerne.
    Hvis kun én sag findes som resultat af søgningen, vises uddybende detaljer om sagen.

    **SAGSID** bruges til at søge på sagens id eller som fritekstsøgning på sagens navn
    eller beskrivelse.

    Derudover kan der søges på et givet tidsrum med ``-df/--fra`` og ``-dt/--til``. Flaget
    ``-a/--aktive`` gør så søgningen kun viser de aktive sager.

    Anføres ingen filterkriterier ikke listes alle sager.

    Endeligt kan man med ``-r/--rapport`` vælge at få vist en simpel optælling af
    punkterne i de(n) fremsøgte sag(er). Optællingen grupperer punkterne på kategorier som
    giver mening ift. kommunal afrapportering:

    \b
        Oprettet    : Antal nyetablerede punkter
        Tabtgået    : Antal tabtmeldte punkter
        Genfundet   : Antal genfundne punkter
        Beregnet    : Antal punkter med nyberegnede koordinater
        Observeret  : Antal observerede punkter
        Besøgt      : Antal punkter som har fået redigeret Punktinfo
                      eller indgår i nogen af ovenstående kategorier.

    **NB!** Optællingen kan ved store sager eller mange fremsøgte sager godt tage lidt tid.
    Angiver man et filnavn ``--rapport sagsrapport.geojson``, skrives en rapporten som geojson med det angivne filnavn.

    **EKSEMPEL**

    Vis alle aktive sager fra 2023::

        fire info sag -a -df "01-01-2023" -dt "01-01-2024"

    Vis alle sager indeholdende søgeteksten "KDI"::

        fire info sag KDI

    Fremsøg en enkelt sag og få vist uddybende information samt optælling::

        fire info sag 2024_DMI_DROGDEN --rapport

    Vis alle sager indeholdende søgeteksten "2024_VEDL" og lav samlet optælling::

        fire info sag 2024_VEDL --rapport "2024_VEDLIGEHOLD_rapport.geojson"

    """
    sager = []
    sag = None
    try:
        sag = fire.cli.firedb.hent_sag(sagsid)
    except (NoResultFound, MultipleResultsFound):

        with YndefuldeFejl(NoResultFound, f"Kunne ikke finde {sagsid}"):
            if sagsid or fra or til or aktive:
                sager = fire.cli.firedb.hent_sager(
                    søgetekst=sagsid, aktive=aktive, tid_fra=fra, tid_til=til
                )

        if len(sager) == 1:
            sag = sager[0]

    if sag:
        fire.cli.print(
            "------------------------- SAG -------------------------", bold=True
        )
        fire.cli.print(f"  Sagsid        : {sag.id}")
        fire.cli.print(f"  Oprettet      : {sag.registreringfra}")
        fire.cli.print(f"  Sagsbehandler : {sag.behandler}")
        if sag.aktiv:
            status = "Aktiv"
        else:
            status = "Lukket"
        fire.cli.print(f"  Status        : {status}")
        fire.cli.print("  Beskrivelse   :\n")
        beskrivelse = textwrap.fill(
            sag.beskrivelse.strip(),
            width=80,
            initial_indent=" " * 4,
            subsequent_indent=" " * 4,
        )
        fire.cli.print(f"{beskrivelse}\n")

        fire.cli.print(f"\n  Sagsevents    :\n")
        for sagsevent in sag.sagsevents:
            try:
                beskrivelse = sagsevent.beskrivelse
                max_beskrivelseslængde = 40
                if len(beskrivelse) > max_beskrivelseslængde:
                    beskrivelse = beskrivelse[0:max_beskrivelseslængde] + "..."

            except IndexError:
                beskrivelse = ""
            eventtype = (
                str(sagsevent.eventtype).replace("EventType.", "").replace("OE", "Ø")
            )
            tid = sagsevent.registreringfra.strftime("%Y-%m-%d")
            sagseventid = sagsevent.id[0:8]
            fire.cli.print(f"[{tid}|{sagseventid}] {eventtype}: {beskrivelse}")

        # hvis --rapport er sat, så tæller vi sagen op
        if rapport is None:
            return

        fire.cli.print(f"\n  Sagsoptælling :\n")
        stats = _optæl_punkter_i_sagsevents(sag.sagsevents)
        for k, v in stats.items():
            fire.cli.print(f"    Antal {k}: {len(v)}")

        # hvis --rapport "filnavn" er sat så skriver vi også en geojson fil ud
        if rapport == "":
            return

        punktider = list(set().union(*stats.values()))
        punkter = fire.cli.firedb.hent_punkter_fra_uuid_liste(punktider)
        skriv_sagsrapport_geojson(rapport, punkter, stats)

        return

    if not sager:
        sager = fire.cli.firedb.hent_alle_sager()
        # Lav aldrig rapport-overblik over alle sager!
        rapport = False

    fire.cli.print("Sagsid     Behandler           Beskrivelse", bold=True)
    fire.cli.print("---------  ------------------  -----------")
    for sag in sager:
        beskrivelse = sag.beskrivelse[0:70].strip().replace("\n", " ").replace("\r", "")
        fire.cli.print(f"{sag.id[0:8]}:  {sag.behandler:20}{beskrivelse}...")

    # hvis --rapport er sat, så tæller vi sagerne op
    if rapport is None:
        return

    fire.cli.print(f"\n--- Optælling af alle fremsøgte sager ---")
    alle_sagsevents = [se for sag in sager for se in sag.sagsevents]
    stats = _optæl_punkter_i_sagsevents(alle_sagsevents)

    for k, v in stats.items():
        print(f"Antal {k}: {len(v)}")

    # hvis --rapport "filnavn" er sat så skriver vi også en geojson fil ud
    if rapport == "":
        return

    punktider = list(set().union(*stats.values()))
    punkter = fire.cli.firedb.hent_punkter_fra_uuid_liste(punktider)
    skriv_sagsrapport_geojson(rapport, punkter, stats)


@info.command()
@fire.cli.default_options()
@click.argument("sagseventid", required=True)
def sagsevent(sagseventid: str, **kwargs) -> None:
    """
    Information om et sagsevent.
    """

    # Hver type FikspunktsregisterObjekt kan tilknyttes to slags Sagsevents,
    # oprettelse og nedlukning. De skal præsenteres på omtrent samme måde.
    # Nedenstående interne funktioner benyttes til dette.
    def _koordinatoversigt(koordinater: list[Koordinat]) -> None:
        tbl = Table(box=None)
        for koordinat in koordinater:
            row, style = koordinat_linje(koordinat)
            # drop 1. kolonne som indeholder markøren
            tbl.add_row(koordinat.punkt.ident, *row[1:])
        print_tabel(tbl, align="left")
        fire.cli.print("\n")

    def _observationsoversigt(observationer: list[Observation]) -> None:
        niv_obstyper = (1, 2)
        observationstyper = [o.observationstypeid for o in observationer]
        ikke_niv_observationer = all(
            obstype not in niv_obstyper for obstype in observationstyper
        )
        if ikke_niv_observationer:
            fire.cli.print(
                "Sagseventen indeholder observationer, der ikke er målt med nivellement."
            )
            fire.cli.print("Disse observationer kan på nuværende tidspunkt ikke vises.")
        else:
            observationsrapport(
                observationer_til=observationer,
                observationer_fra=[],
                options="niv",
                opt_detaljeret=False,
            )

    def _punktoversigt(punkter: list[Punkt]) -> None:
        for punkt in punkter:
            fire.cli.print(f" PUNKT {punkt.ident} ({punkt.id})", bold=True)
            fire.cli.print(f"  Lokation  {punkt.geometriobjekter[-1].geometri}")
        fire.cli.print("\n")

    def _punktinfooversigt(
        punktinformationer: list[PunktInformation], historik: bool
    ) -> None:
        # PunktInformationer grupperes efter Punkt
        punkter = set(punktinfo.punkt for punktinfo in punktinformationer)
        punktinfo_oversigt = {punkt: [] for punkt in punkter}

        for punktinfo in punktinformationer:
            punktinfo_oversigt[punktinfo.punkt].append(punktinfo)

        for punkt, punktinformationer in punktinfo_oversigt.items():
            tbl = generer_rapporttabel(
                title=punkt.ident,
                show_header=False,
            )
            for info in punktinformationer:
                if info.registreringtil and not historik:
                    continue
                # vi bruger ikke stilarten i denne sagseventrapport.
                row, style = punktinfo_linje(info)
                tbl.add_row(*row)

            print_tabel(tbl, align="left")
            fire.cli.print("\n")

    def _grafikoversigt(grafikker: list[Grafik]) -> None:
        fire.cli.print(f"{'Filnavn':30} Type")
        fire.cli.print(f"{'-'*29:30} --------------")

        for grafik in grafikker:
            fire.cli.print(f"{grafik.filnavn:30} {grafik.type}")

    def _header(tekst: str, bold=False) -> None:
        max_bredde = 80
        spacer_bredde = (max_bredde - len(tekst) - 2) // 2 + 1
        fire.cli.print(
            f"{'-'*spacer_bredde} {tekst} {'-'*spacer_bredde}"[0:80], bold=bold
        )

    with (
        YndefuldeFejl(NoResultFound, f'"{sagseventid}" ikke fundet!'),
        YndefuldeFejl(
            MultipleResultsFound, f'Partielt UUID "{sagseventid}" ikke unikt!'
        ),
    ):
        event = fire.cli.firedb.hent_sagsevent(sagseventid)

    fire.cli.print("\n")
    _header("SAGSEVENT", bold=True)
    fire.cli.print(f"  Sagseventid   : {event.id}")
    fire.cli.print(f"  Sagseventtype : {event.eventtype.name}")
    fire.cli.print(f"  Oprettet      : {event.registreringfra}")
    fire.cli.print(f"  Sagsid        : {event.sag.id}")
    if len(event.beskrivelse) > 45:
        fire.cli.print("  Beskrivelse   :\n")
        fire.cli.print(event.beskrivelse)
    else:
        fire.cli.print(f"  Beskrivelse   : {event.beskrivelse}")
    fire.cli.print("\n")

    if event.eventtype == EventType.KOMMENTAR:
        materialer = [m.materiale for si in event.sagseventinfos for m in si.materialer]
        htmler = [h.html for si in event.sagseventinfos for h in si.htmler]

        if materialer:
            _header("Tilknyttet sagsmateriale")
            for materiale in materialer:
                blob = io.BytesIO(materiale)
                with zipfile.ZipFile(blob, "r") as zipped_files:
                    zipped_files.printdir()
                fire.cli.print("\n")

        if htmler:
            _header("Tilknyttede HTML-filer")
            for html in htmler:
                match = re.search("<title>(.*?)</title>", html)
                title = match.group(1) if match else "Ingen HTML titel"
                fire.cli.print(title)

    if event.koordinater:
        _header("Tilføjede koordinater")
        _koordinatoversigt(event.koordinater)

    if event.koordinater_slettede:
        _header("Afregistrerede koordinater")
        _koordinatoversigt(event.koordinater_slettede)

    if event.observationer:
        _header("Tilføjede observationer")
        _observationsoversigt(event.observationer)

    if event.observationer_slettede:
        _header("Afregistrerede observationer")
        _observationsoversigt(event.observationer_slettede)

    if event.punktinformationer:
        _header("Tilføjede punktinformationer")
        _punktinfooversigt(event.punktinformationer, historik=False)

    if event.punktinformationer_slettede:
        _header("Afregistrerede punktinformationer")
        _punktinfooversigt(event.punktinformationer_slettede, historik=True)

    if event.punkter:
        _header("Tilføjet punkt")
        _punktoversigt(event.punkter)

    if event.punkter_slettede:
        _header("Afregistreret punkt")
        _punktoversigt(event.punkter_slettede)

    if event.grafikker:
        _header("Tilføjet grafik")
        _grafikoversigt(event.grafikker)

    if event.grafikker_slettede:
        _header("Afregistreret grafik")
        _grafikoversigt(event.grafikker_slettede)

    if event.punktsamlinger:
        _header("Tilføjede punktsamlinger")
        punktsamlingsrapport(event.punktsamlinger)

    if event.punktsamlinger_slettede:
        _header("Afregistrerede punktsamlinger")
        punktsamlingsrapport(event.punktsamlinger_slettede)

    if event.tidsserier:
        _header("Tilføjede tidsserier")
        tidsserierapport(event.tidsserier)

    if event.tidsserier_slettede:
        _header("Afregistrerede tidsserier")
        tidsserierapport(event.tidsserier_slettede)


@info.command()
@fire.cli.default_options()
@click.argument("punktsamling", required=False)
def punktsamling(punktsamling: str, **kwargs):
    """
    Information om en punktsamling.

    Anføres **PUNKTSAMLING** ikke listes alle aktive punktsamlinger.
    I listen over punkter i punktsamlingen er Jessenpunktet highlightet.
    """
    if not punktsamling:
        punktsamlinger = fire.cli.firedb.hent_alle_punktsamlinger()
        if not punktsamlinger:
            raise IntetAtGøre("Der findes ingen punktsamlinger i databasen.")

        punktsamlingsrapport(punktsamlinger)

        return

    with YndefuldeFejl(NoResultFound, f"{punktsamling} ikke fundet!"):
        punktsamling = fire.cli.firedb.hent_punktsamling(punktsamling)

    fire.cli.print(
        "------------------------- PUNKTSAMLING -------------------------", bold=True
    )
    fire.cli.print(f"  Navn          : {punktsamling.navn}")
    fire.cli.print(f"  Formål        : {punktsamling.formål}")
    fire.cli.print(f"  Jessenpunkt   : {punktsamling.jessenpunkt.ident}")
    fire.cli.print(f"  Jessennummer  : {punktsamling.jessenpunkt.jessennummer}")
    fire.cli.print(f"  Jessenkote    : {punktsamling.jessenkote} m")
    fire.cli.print(f"  Antal punkter : {len(punktsamling.punkter)}")

    fire.cli.print(f"--- Punkter ---")

    if not punktsamling.punkter:
        fire.cli.print(f"  Der er ingen Punkter i Punktsamlingen !!!")
    for punkt in punktsamling.punkter:
        farve = "white"
        if punkt.id == punktsamling.jessenpunkt.id:
            farve = "green"
        fire.cli.print(f"  {punkt.ident}", fg=farve)

    fire.cli.print(f"--- Tidsserier ---")
    if not punktsamling.tidsserier:
        fire.cli.print(f"  Punktsamlingen har ingen tilknyttede tidsserier.")
        return

    tidsserierapport(punktsamling.tidsserier)

    return

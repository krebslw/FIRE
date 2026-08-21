print("importerede cli.info_light.helpers")
import datetime
import itertools

from pyproj import CRS
from pyproj.exceptions import CRSError

from fire.cli import (
    print as fire_print
)
from fire.cli.pretty_tables import (
    klargør_celle,
    print_tabel,
    generer_rapporttabel,
)

def punkt_fuld_rapport(
    punkt: "Punkt",
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
    fire_print("")
    fire_print("-" * 80)
    if n > 1:
        fire_print(f" PUNKT {punkt.ident} ({i}/{n})", bold=True)
    else:
        fire_print(f" PUNKT {punkt.ident}", bold=True)
    fire_print("-" * 80)

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

        fire_print("")
        print_tabel(tbl, align="left")

    # Koordinater og observationer klares af specialiserede hjælpefunktioner
    if "ingen" not in opt_koord.split(","):
        fire_print("")
        koordinatrapport(punkt.koordinater, opt_koord, opt_historik)

    if opt_obs != "":
        fire_print("")
        observationsrapport(
            punkt.observationer_til, punkt.observationer_fra, opt_obs, opt_detaljeret
        )

    if punkt.punktsamlinger:
        fire_print("")
        punktsamlingsrapport(punkt.punktsamlinger, punkt.id)

    if punkt.tidsserier:
        fire_print("")
        tidsserierapport(punkt.tidsserier)


def observation_linje(
    obs: "GeometriskKoteforskel | TrigonometriskKoteforskel",
) -> tuple[list[str], str]:
    if obs.observationstypeid > 2:
        return [], None

    if obs.slettet:
        return [], None

    metode = "G" if obs.observationstypeid == 1 else "T"
    tid = obs.observationstidspunkt.strftime("%Y-%m-%d %H:%M")

    # Kun GeometriskKoteForskel har disse to attributter.
    # Hvis observationen er Trigonometrisk skrives 0 i stedet.
    præs = int(getattr(obs, "præcisionsnivellement", 0))
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


def koordinat_linje(koord: "Koordinat") -> tuple[list[str], str]:
    """
    Konstruer koordinatoutput i overensstemmelse med koordinatens dimensionalitet,
    enhed og proveniens.
    """
    import enum
    class Boolean(enum.Enum):
        TRUE = "true"
        FALSE = "false"

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


def punktinfo_linje(punktinfo: "PunktInformation") -> tuple[list[str], str]:
    """Generér en tabelrække til punktinforapport."""
    tekst = (punktinfo.tekst or "").rstrip(" \n")
    # tal kan godt være 0, derfor tjekkes explicit for Noneness
    tal = punktinfo.tal if punktinfo.tal is not None else ""

    # marker slukkede punktinformationer med rød tekst og et minus tv for linjen
    style, markør = "", ""
    if punktinfo.registreringtil:
        style, markør = "red", "-"
    row = [f"{markør}{punktinfo.infotype.name}", f"{tekst}{tal}"]
    return row, style


def punktinforapport(
    punkt: "Punkt", historik: bool = False, detaljeret: bool = False
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
    koordinater: list["Koordinat"], options: str, historik: bool
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
    observationer_til: list["Observation"],
    observationer_fra: list["Observation"],
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


def punktsamlingsrapport(punktsamlinger: list["PunktSamling"], id: str = None):
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


def tidsserierapport(tidsserier: list["Tidsserie"]):
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
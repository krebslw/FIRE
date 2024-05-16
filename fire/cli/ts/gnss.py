from datetime import datetime

import click
import pandas as pd
from pathlib import Path
from pyproj import Transformer
from rich.table import Table
from rich.console import Console
from rich import box
from sqlalchemy import func
from sqlalchemy.exc import NoResultFound

import fire.cli
from fire.api.model import (
    Tidsserie,
    GNSSTidsserie,
    Punkt,
)
from fire.api.model.tidsserier import (
    TidsserieEnsemble,
)
from fire.cli.ts._plot_gnss import (
    plot_gnss_ts,
    plot_gnss_analyse,
    plot_data,
    plot_fit,
    plot_konfidensbånd,
    GNSS_TS_PLOTTING_LABELS,
)
from fire.cli.ts import (
    _find_tidsserie,
    _print_tidsserieoversigt,
)

from . import ts


GNSS_TS_PARAMETRE = {
    "t": "t",
    "x": "x",
    "sx": "sx",
    "y": "y",
    "sy": "sy",
    "z": "z",
    "sz": "sz",
    "X": "X",
    "Y": "Y",
    "Z": "Z",
    "n": "n",
    "e": "e",
    "u": "u",
    "decimalår": "decimalår",
    "obslængde": "obslængde",
    "kkxx": "koordinatkovarians_xx",
    "kkxy": "koordinatkovarians_xy",
    "kkxz": "koordinatkovarians_xz",
    "kkyy": "koordinatkovarians_yy",
    "kkyz": "koordinatkovarians_yz",
    "kkzz": "koordinatkovarians_zz",
    "rkxx": "residualkovarians_xx",
    "rkxy": "residualkovarians_xy",
    "rkxz": "residualkovarians_xz",
    "rkyy": "residualkovarians_yy",
    "rkyz": "residualkovarians_yz",
    "rkzz": "residualkovarians_zz",
}

GNSS_TS_ANALYSERBARE_PARAMETRE = {
    "x": "x",
    "y": "y",
    "z": "z",
    "X": "X",
    "Y": "Y",
    "Z": "Z",
    "n": "n",
    "e": "e",
    "u": "u",
}

DEFAULT_STI_UPLIFT_DATA = Path(__file__).parents[3] / Path("data/uplift")


@ts.command()
@click.argument("objekt", required=False, type=str)
@click.option(
    "--parametre",
    "-p",
    required=False,
    type=str,
    default="t,x,sx,y,sy,z,sz",
    help="""Vælg hvilke parametre i tidsserien der skal udtrækkes. Som standard
sat til 't,x,sx,y,sy,z,sz'. Bruges værdien 'alle' udtrækkes alle mulige parametre
i tidsserien.  Se ``fire ts gnss --help`` for yderligere detaljer.""",
)
@click.option(
    "--fil",
    "-f",
    required=False,
    type=click.Path(writable=True),
    help="Skriv den udtrukne tidsserie til Excel fil.",
)
@fire.cli.default_options()
def gnss(objekt: str, parametre: str, fil: click.Path, **kwargs) -> None:
    """
    Udtræk en GNSS tidsserie.


    "OBJEKT" sættes til enten et punkt eller et specifik navngiven tidsserie.
    Hvis "OBJEKT" er et punkt udskrives en oversigt over de tilgængelige
    tidsserier til dette punkt. Hvis 'OBJEKT' er en tidsserie udskrives
    tidsserien på skærmen. Hvilke parametre der udskrives kan specificeres
    i en kommasepareret liste med ``--parametre``. Følgende parametre kan vælges::

    \b
        t               Tidspunkt for koordinatobservation
        x               Koordinatens x-komponent (geocentrisk)
        sx              x-komponentens spredning (i mm)
        y               Koordinatens y-komponent (geocentrisk)
        sy              y-komponentens spredning (i mm)
        z               Koordinatens z-komponent (geocentrisk)
        sz              z-komponentens spredning (i mm)
        X               Koordinatens x-komponent (geocentrisk, normaliseret)
        Y               Koordinatens y-komponent (geocentrisk, normaliseret)
        Z               Koordinatens z-komponent (geocentrisk, normaliseret)
        n               Normaliseret nordlig komponent (topocentrisk)
        e               Normaliseret østlig komponent (topocentrisk)
        u               Normaliseret vertikal komponent (topocentrisk)
        decimalår       Tidspunkt for koordinatobservation i decimalår
        obslængde       Observationslængde givet i timer
        kkxx            Koordinatkovariansmatricens XX-komponent
        kkxy            Koordinatkovariansmatricens XY-komponent
        kkxz            Koordinatkovariansmatricens XZ-komponent
        kkyy            Koordinatkovariansmatricens YY-komponent
        kkyz            Koordinatkovariansmatricens YZ-komponent
        kkzz            Koordinatkovariansmatricens ZZ-komponent
        rkxx            Residualkovariansmatricens XX-komponent
        rkxy            Residualkovariansmatricens XY-komponent
        rkxz            Residualkovariansmatricens XZ-komponent
        rkyy            Residualkovariansmatricens YY-komponent
        rkyz            Residualkovariansmatricens YZ-komponent
        rkzz            Residualkovariansmatricens ZZ-komponent

    Tidsserien kan skrives til en fil ved brug af ``--fil``, der resulterer i
    en csv-fil på den angivne placering. Denne fil kan efterfølgende åbnes
    i Excel, eller et andet passende program, til videre analyse.


    \b
    **EKSEMPLER**

    Vis alle tidsserier for punktet RDIO::

        fire ts gnss RDIO

    Vis tidsserien 'RDIO_5D_IGb08' med standardparametre::

        fire ts gnss RDIO_5D_IGb08

    Vis tidsserie med brugerdefinerede parametre::

        fire ts gnss RDIO_5D_IGb08 --parametre decimalår,n,e,u,sx,sy,sz

    Gem tidsserie med samtlige tilgængelige parametre::

        fire ts gnss RDIO_5D_IGb08 -p alle -f RDIO_5D_IGb08.xlsx
    """
    if not objekt:
        _print_tidsserieoversigt(GNSSTidsserie)
        raise SystemExit

    # Prøv først med at søg efter specifik tidsserie
    try:
        tidsserie = _find_tidsserie(GNSSTidsserie, objekt)
    except NoResultFound:
        try:
            punkt = fire.cli.firedb.hent_punkt(objekt)
        except NoResultFound:
            raise SystemExit("Punkt eller tidsserie ikke fundet")

        _print_tidsserieoversigt(GNSSTidsserie, punkt)
        raise SystemExit

    if parametre.lower() == "alle":
        parametre = ",".join(GNSS_TS_PARAMETRE.keys())

    parametre = parametre.split(",")
    overskrifter = []
    kolonner = []
    for p in parametre:
        if p not in GNSS_TS_PARAMETRE.keys():
            raise SystemExit(f"Ukendt tidsserieparameter '{p}'")

        overskrifter.append(p)
        kolonner.append(tidsserie.__getattribute__(GNSS_TS_PARAMETRE[p]))

    tabel = Table(*overskrifter, box=box.SIMPLE)
    data = list(zip(*kolonner))

    def klargør_celle(input):
        if isinstance(input, datetime):
            return str(input)
        if isinstance(input, float):
            return f"{input:.4f}"
        if not input:
            return ""

    for række in data:
        tabel.add_row(
            *[klargør_celle(celle) if celle is not None else "" for celle in række]
        )

    console = Console()
    console.print(tabel)

    if not fil:
        raise SystemExit

    data = {
        overskrift: kolonne for (overskrift, kolonne) in zip(overskrifter, kolonner)
    }
    df = pd.DataFrame(data)
    df.to_excel(fil, index=False)


@ts.command()
@click.argument("tidsserie", required=True, type=str)
@click.option(
    "--plottype",
    "-t",
    required=False,
    type=click.Choice(["rå", "fit", "konf"]),
    default="rå",
    help="Hvilken type plot vil man se?",
)
@click.option(
    "--parametre",
    "-p",
    required=False,
    type=str,
    default=None,
    help="Hvilken parameter skal plottes? Vælges flere plottes max de tre første.",
)
@fire.cli.default_options()
def plot_gnss(tidsserie: str, plottype: str, parametre: str, **kwargs) -> None:
    """
    Plot en GNSS tidsserie.

    Et simpelt plot der som standard viser udviklingen i nord, øst og op retningerne over tid.
    Vælges plottypen ``konf`` vises som standard kun Op-retningen.
    Plottes kun én enkelt tidsserieparameter vises for plottyperne ``fit`` og ``konf`` også
    værdien af fittets hældning.

    "TIDSSERIE" er et GNSS-tidsserie ID fra FIRE. Eksisterende GNSS-tidsserier kan
    fremsøges med kommandoen ``fire ts gnss <punktnummer>``.
    Hvilke parametre der plottes kan specificeres i en kommasepareret liste med ``--parametre``.
    Højst 3 parametre plottes. Følgende parametre kan vælges::

    \b
        t               Tidspunkt for koordinatobservation
        x               Koordinatens x-komponent (geocentrisk)
        y               Koordinatens y-komponent (geocentrisk)
        z               Koordinatens z-komponent (geocentrisk)
        X               Koordinatens x-komponent (geocentrisk, normaliseret)
        Y               Koordinatens y-komponent (geocentrisk, normaliseret)
        Z               Koordinatens z-komponent (geocentrisk, normaliseret)
        n               Normaliseret nordlig komponent (topocentrisk)
        e               Normaliseret østlig komponent (topocentrisk)
        u               Normaliseret vertikal komponent (topocentrisk)
        decimalår       Tidspunkt for koordinatobservation i decimalår

    Typen af plot som vises kan vælges med ``--plottype``. Følgende plottyper kan vælges::

    \b
        rå              Plot rå data
        fit             Plot lineær regression oven på de rå data
        konf            Plot lineær regression med konfidensbånd

    \f
    **EKSEMPLER**

    Plot af 5D-tidsserie for BUDP::

        fire ts plot-gnss BUDP_5D_IGb08

    Resulterer i visning af nedenstående plot.

    .. image:: figures/fire_ts_plot_gnss_BUDP_5D_IGb08.png
        :width: 800
        :alt: Eksempel på plot af 5D-tidsserie for BUDP.

    Plot af 5D-tidsserie for SMID::

        fire ts plot-gnss SMID_5D_IGb08 -p X,Y -t fit

    Resulterer i visning af nedenstående plot.

    .. image:: figures/fire_ts_plot_gnss_SMID_5D_IGb08_XY_fit.png
        :width: 800
        :alt: Eksempel på plot af 5D-tidsserie for SMID.

    Plot af 5D-tidsserie for TEJH::

        fire ts plot-gnss TEJH_5D_IGb08 -t konf

    Resulterer i visning af nedenstående plot.

    .. image:: figures/fire_ts_plot_gnss_TEJH_5D_IGb08_konf.png
        :width: 800
        :alt: Eksempel på plot af 5D-tidsserie for TEJH.

    """
    # Dynamisk default værdi baseret på plottype.
    # Se https://stackoverflow.com/questions/51846634/click-dynamic-defaults-for-prompts-based-on-other-options for andre muligheder
    if parametre is None:
        if plottype == "konf":
            parametre = "u"
        else:
            parametre = "n,e,u"

    plot_funktioner = {
        "rå": plot_data,
        "fit": plot_fit,
        "konf": plot_konfidensbånd,
    }

    try:
        tidsserie = _find_tidsserie(GNSSTidsserie, tidsserie)
    except NoResultFound:
        raise SystemExit("Tidsserie ikke fundet")

    parametre = parametre.split(",")

    for parm in parametre:
        if parm not in GNSS_TS_ANALYSERBARE_PARAMETRE.keys():
            raise SystemExit(f"Ukendt tidsserieparameter '{parm}'")

    parametre = [GNSS_TS_ANALYSERBARE_PARAMETRE[parm] for parm in parametre]

    plot_gnss_ts(tidsserie, plot_funktioner[plottype], parametre)


@ts.command()
@click.argument(
    "ts-liste",
    required=False,
    type=str,
)
@click.option(
    "--ts-fil",
    required=False,
    type=click.Path(),
    help="Sti til fil med liste af tidsserier som skal analyseres. TidsserieID'erne i \
filen skal være adskilt af linjeskift. (\\\\n)",
)
@click.option(
    "--parameter",
    required=False,
    type=str,
    default="u",
    help="Vælg hvilken tidsserieparameter der skal undersøges, fx u for ellipsoidehøjde.",
)
@click.option(
    "--ofil",
    "-o",
    required=False,
    type=click.Path(writable=True),
    help="Skriv beregnet tidsseriestatistik til csv-fil.",
)
@click.option(
    "--uplift-station",
    required=False,
    type=click.Path(writable=False),
    help="Sti til uplift-data for hver station. Hvis de(n) valgte station ikke \
findes, interpoleres uplift-raten ud fra ``--uplift-grid``. Formatet af filen \
skal være ``GNSSNR, LON, LAT, UPLIFTRATE \\n``.",
)
@click.option(
    "--uplift-grid",
    required=False,
    type=click.Path(writable=False),
    default=DEFAULT_STI_UPLIFT_DATA / Path("dtu2016_abs.tif"),
    help='Sti til griddet uplift-data. NB! Default-modellen "DTU 2016" af Per Knudsen \
dækker området fra 54.1-58°N og 7.7-13.1°E og er dermed ikke gyldig over Bornholm.',
)
@click.option(
    "--min-antal-punkter",
    required=False,
    type=int,
    default=3,
    help="Minimum antal punkter i tidsserien.",
)
@click.option(
    "--alpha",
    required=False,
    type=float,
    default=0.05,
    help="Signifikansniveau for statistiske tests og konfidensintervaller.",
)
@click.option(
    "--binsize",
    required=False,
    type=int,
    default=14,
    help="Hvis antal dage mellem datapunkter er mindre end binsize findes gennemsnit af \
datapunkterne.",
)
@click.option(
    "--grad",
    required=False,
    type=int,
    default=1,
    help="Vælg graden af polynomiet som fittes til data. Bruges sjældent.",
)
@click.option(
    "--referenceramme",
    required=False,
    type=str,
    default="IGb08",
    help="Vælg tidseriernes referenceramme.",
)
@click.option(
    "--alle",
    is_flag=True,
    default=False,
    help="Sættes dette flag, bliver ``--ts-liste`` og ``--ts-fil`` ignoreret og alle GNSS-stationer \
med 5D tidsserier i den valgte referenceramme analyseres.",
)
@click.option(
    "--plot/--no-plot",
    is_flag=True,
    default=True,
    help="Vælg om plots skal vises eller ej.",
)
@fire.cli.default_options()
def analyse_gnss(
    ts_liste: str,
    ts_fil: click.Path,
    parameter: str,
    referenceramme: str,
    uplift_station: click.Path,
    uplift_grid: click.Path,
    ofil: click.Path,
    min_antal_punkter: int,
    alpha: float,
    binsize: int,
    grad: int,
    alle: bool,
    plot: bool,
    **kwargs,
):
    """
    Analysér tidsserie for én eller flere GNSS stationer.

    Der beregnes som udgangspunkt et lineært fit til tidsserierne, der sammenlignes med en
    uplift-model og derefter vises i et detaljeret plot med konfidensbånd og diverse andre
    kvalitetsparametre for fittet. Resultaterne gemmes i csv-format hvis en sti angives
    med ``--ofil``.

    Alle tidsserieparametre som er indeholdt i FIRE kan analyseres. Af størst relevans er
    Op-retningen (``u``), men der kan også vælges de andre geografiske dimensioner nord og
    øst, samt de geocentriske x, y eller z. Vælger man at analysere Op-retningen, så
    sammenligner programmet hældningen af den fittede linje med en reference-hældning
    givet ved uplift-modellen "DTU 2016" af Per Knudsen. En alternativ uplift-model kan
    angives enten for hvert punkt på listeform eller i griddet format (tif-fil).

    Idéen med at sammenligne med en uplift-model er, at identificere eventuelle lokale
    bevægelser som ikke indfanges af uplift-modellen.

    Sammenligningen foretages ved statistisk hypotesetest, som vurderer sandsynligheden
    for om den modellerede hældning er lig referencehældningen. Hertil anvendes
    signifikansniveauet ``alpha``.

    Konfidensintervaller- og bånd for regressionsparametrene hhv. -linjen anvender
    ligeledes signifikansniveauet ``alpha``.

    Analyseres mere end 1 tidsserie betegnes samlingen af disse som et tidsserie-ensemble
    og der beregnes en samlet usikkerhed af ensemblets observationer. Den "samlede"
    usikkerhed anvendes så til genberegning af statistiske tests og parametre. Kun
    tidsserier som er i samme ``referenceramme`` kan analyseres (default er IGb08).


    **Tuning**:

    Analyseresultaterne kan tunes med parametrene::

    \b
        binsize             Tag gennemsnit af datapunkter som er tættere på hinanden end
                            binsize. For detaljer se dokumentation af
                            GNSSTidsserie.binning.
    \b
        min_antal_punkter   Minimum antal punkter i tidsserien.
    \b
        alpha               Signifikansniveau for konfidensintervaller og hypotesetests.

    \f
    **Rationale bag binning:**

    Tidsserierne består af data ujævnt spredt i tid. Derfor kan man komme ud for at en
    tidsserie består en gruppe af data som er tæt på hinanden i tid, samt af nogle få
    punkter som ligger mere spredt. Tidsperioden med den lille gruppe punkter som ligger
    tæt vil derfor have en større vægt en resten af punkterne, når man estimerer sin
    lineære model. Binning-proceduren er derfor en måde at reducere data/downsample de
    perioder hvor der er mange punkter. Derudover vil midlingen af punkterne inden for en
    "bin" også udjævne tilfældige fejl i data.

    Bemærk at der **ikke** er tale om interpolation eller gridding af data.

    **Rationale bag tidsserie-ensembler:**

    Idet at man på kort tidsskala (år) antager en lineær trend i et givent punkts
    bevægelse (inklusive modelleret landbevægelse og lokale sætninger), kan afvigelserne
    (residualerne) mellem observationerne og den fittede linje, tolkes som
    måleusikkerheden forbundet med observationerne. (*NB! Tager ikke højde for eventuelle
    periodiske signaler eller (sjovt nok) ulinære tendenser.*) Dette kræver, at
    observationerne som indgår i tidsserien så vidt muligt er målt på samme måde og efter
    samme standarder, herunder GNSS-antenne/modtager, måletid etc.

    Denne antagelse er vigtig for at kunne analysere et tidsserie-ensemble som helhed.
    Idéen med dette er, at bruge residualerne fra alle tidsserierne i ensemblet til at
    estimere en generel, *samlet* måleusikkerhed for observationerne i ensemblet. (se også
    https://en.wikipedia.org/wiki/Pooled_variance). *NB! Igen er det vigtigt at man sikrer
    sig at hver observation i hver tidsserie som indgår i ensemblet er målt på samme
    måde.*

    Idet flere observationer indgår i estimeringen af denne samlede varians, vil denne
    være "bedre bestemt" end variansen for den enkelte tidsserne, og dette betyder at man
    med større statistisk sikkerhed kan drage konklusioner om GNSS-punkternes bevægelser.

    **Formler bag analyse-gnss:**

    Generelt søges der på et lineært ligningssystem et estimat:
    :math:`\\hat{\\beta}=\\begin{bmatrix} \\hat{\\beta}_0 & \\hat{\\beta}_1 & ··· &
    \\hat{\\beta}_{M-1}\\end{bmatrix}^T`, hvor :math:`M` er antallet af modelparametre (i
    kildekoden bruges betegnelsen ``ddof``, efter det engelske "delta degrees of freedom",
    for at skabe konsistens med de anvendte biblioteker numpy og scipy).

    Det lineære ligningssystem repræsenteres på matrixform som:

    .. math::
        \\mathbf{A}\\,\\beta = \\mathbf{y}

    Det følgende tager udgangspunkt i, at der fittes en ret linje, dvs. :math:`M=2`,
    hvilket er programmets standardindstilling. I så fald ser designmatricen
    :math:`\\mathbf{A}` ud på følgende måde:

    .. math::
        \\mathbf{A}= \\begin{bmatrix}
        1 & x_1 \\\\
        1 & x_2 \\\\
        ⋮  &  ⋮  \\\\
        1 & x_N
        \\end{bmatrix}
    hvor :math:`{x_i}` er den forklarende variabel og :math:`{N}` er antallet af
    datapunkter.

    Observationerne er givet ved vektoren :math:`\\mathbf{y}`:

    .. math::
        \\mathbf{y}= \\begin{bmatrix} y_1 \\\\ y_2 \\\\ ⋮ \\\\ y_N \\end{bmatrix}

    Residualerne er da:

    .. math::
        \\mathbf{r}=\\mathbf{A}\\mathbf{x} -\\mathbf{b}

    Summen af kvadrerede residualer betegnes som:

    .. math::
        \\text{SSR} = \\mathbf{r}^T \\, \\mathbf{r}

    Løsningen vurderes ud fra bestemmelseskoefficienten :math:`{R^2}`:

    .. math::
        R^2=1-\\frac{\\text{SSR}}{\\sum_i\\left(y_i - \\bar{y} \\right)^2}

    Antallet af frihedsgrader angives :math:`\\text{dof}`:

    .. math::
        \\text{dof} = N-M

    Den estimerede varians af residualerne :math:`\\sigma_0^2` bestemmes ud fra
    :math:`\\text{MSE}` (Mean Squared Error):

    .. math::
        \\sigma_0^2 = \\text{MSE} = \\frac{\\text{SSR}}{\\text{dof}}

    Kovariansmatricen af de estimerede parametre :math:`\\mathbf{\\Sigma} (\\hat{\\beta})`
    er bestemt ved:

    .. math::
        \\mathbf{\\Sigma} = \\sigma_0^2\\,(\\mathbf{A}^T\\mathbf{A})^{-1} =
        \\begin{bmatrix}
        \\sigma_{\\hat{\\beta}_0}^2 & \\text{Cov}(\\hat{\\beta}_0,\\hat{\\beta}_1) \\\\
        \\text{Cov}(\\hat{\\beta}_1, \\hat{\\beta}_0) & \\sigma_{\\hat{\\beta}_1}^2
        \\end{bmatrix}

    Konfidensintervallet :math:`\\text{KI}` for de estimerede parametre kan nu beregnes
    med signifikansniveau :math:`\\alpha` som:

    .. math::
        \\text{KI} = \\hat{\\beta}_i \\pm T_{1-\\alpha/2} \\, \\sigma_{\\hat{\\beta}_i}

    hvor :math:`T_{1-\\alpha/2}` er :math:`100·(1-\\alpha/2)` -fraktilen for en
    t-fordeling med :math:`\\text{dof}` antal frihedsgrader.

    **Konfidensbånd**

    Prædiktioner med modellen for et vilkårligt prædiktionspunkt :math:`x_p` er givet ved:

    .. math::
        y_p = \\hat{\\beta}_0 + \\hat{\\beta}_1\\,x_p

    Et mål for sikkerheden af prædiktionen er *konfidensbåndet*. Denne beregnes for
    punktet :math:`x_p` som:

    .. math::
        y_p \\pm T_{1-\\alpha/2} \\,
        \\left(
            \\begin{bmatrix} 1 & x_p \\end{bmatrix}
            \\mathbf{\\Sigma}
            \\begin{bmatrix} 1 & x_p \\end{bmatrix}^T
        \\right)^{1/2}

    **Hypotesetest**

    Hypotesetests foretages med følgende nulhypotese:

        *Den modellerede terrænhastighed* :math:`\\hat{\\beta}_1` *er lig
        reference-hastigheden* :math:`v`

    For Op-retningen er :math:`v` givet ved en uplift-model. Den alternative hypotese er
    nulhypotesens inverse:

        *Den modellerede terrænhastighed* :math:`\\hat{\\beta}_1` *er forskellig fra
        reference-hastigheden* :math:`v`

    Dette formuleres matematisk som:

    .. math::
        H_0: \\hat{\\beta_1} = v

        H_1: \\hat{\\beta_1} \\neq v

    Test-scoren betegnes enten som :math:`t` eller :math:`z` afhængigt af om der foretages
    t- eller z-test. Begge test-scorer beregnes som:

    .. math::
        \\frac{\\hat{\\beta_1} - v }{\\sigma_{\\hat{\\beta_1}}}

    Nulhypotesen :math:`H_0` accepteres hvis :math:`t\\lt T_{1-\\alpha/2}` (eller
    :math:`z\\lt Z_{1-\\alpha/2}`). Ellers forkastes nulhypotesen og den alternative
    hypotese må accepteres.


    **Samlet varians**

    Den samlede varians :math:`\\sigma_{samlet}^2` beregnes som et vægtet gennemsnit af
    den estimerede varians :math:`\\sigma_{0,j}^2` for hver tidsserie
    :math:`j=1\\,..N_{ts}` som indgår i ensemblet:

    .. math::
        \\sigma_{samlet}^2 = \\frac{\\sum_{j=1}^{N_{ts}} \\text{dof}_j \\,
        \\sigma_{0,j}^2}{\\sum_{j=1}^{N_{ts}} \\text{dof}_j} =
        \\frac{\\sum_{j=1}^{N_{ts}} \\text{SSR}_j}{\\sum_{j=1}^{N_{ts}} \\text{dof}_j}

    hvor :math:`\\text{dof}_j` er antallet af frihedsgrader for hver tidsserie :math:`j`.
    Den samlede varians kan nu erstatte :math:`\\sigma_0^2` i de ovenstående formler,
    hvorved de statistiske størrelsers "samlede" udgave opnås. Dette indebærer antagelsen
    om, at :math:`\\sigma_{samlet}^2` er estimatet af *populationens* varians og ikke
    *sample*-variansen som er :math:`\\sigma_{0}^2`. Dette gør os i stand til, i
    hypotesetest og konfidensintervaller at anvende en normalfordeling med fraktilen
    :math:`Z_{1-\\alpha/2}` som er uafhængig af antal frihedsgrader, i stedet for en
    t-fordeling med fraktilen :math:`T_{1-\\alpha/2}`.

    """
    # denne funktion regner altid på 5D punkter. Kan evt. udvides.
    tidsseriegruppe = "5D"

    # skaler data så der regnes og plottes i [mm] i stedet for [m]
    skalafaktor = 1e3

    # Map parameter alias til rigtigt navn igennem GNSS_TS_ANALYSERBARE_PARAMETRE
    try:
        parameter = GNSS_TS_ANALYSERBARE_PARAMETRE[parameter]
    except KeyError:
        raise SystemExit(f"Kan ikke analysere parameter '{parameter}'")

    # Opret Tidsserieensemble
    tsensemble = TidsserieEnsemble(
        GNSSTidsserie,
        min_antal_punkter=min_antal_punkter,
        tidsseriegruppe=tidsseriegruppe,
        referenceramme=referenceramme,
    )

    # Hent alle tidsserier i FIRE som passer til søgningen
    query = fire.cli.firedb.session.query(GNSSTidsserie).filter(
        GNSSTidsserie._registreringtil == None,
        GNSSTidsserie.referenceramme == referenceramme,
    )

    # Filtrér på de givne tidsserienavne
    if not alle:
        if not ts_fil and not ts_liste:
            raise SystemExit("Ingen tidsserier angivet.")

        tidsserienavne = []

        if ts_fil:
            with open(ts_fil, "r") as f:
                lines = list(f)
            ts_fra_fil = [line.strip() for line in lines]
            tidsserienavne += ts_fra_fil

        if ts_liste:
            ts_fra_liste = ts_liste.split(",")
            tidsserienavne += ts_fra_liste

        query = query.filter(GNSSTidsserie.navn.in_(tidsserienavne))

    tidsserier = query.all()

    # Filtrér desuden på tidsseriegruppe og min_antal_punkter, da de ikke kan filtreres via SQL
    tidsserier = [
        ts
        for ts in tidsserier
        if (
            ts.tidsseriegruppe == tidsseriegruppe
            and len(ts) >= min_antal_punkter
        )
    ]

    if not tidsserier:
        raise SystemExit("Fandt ingen tidsserier")

    # Læs uplift-værdier som brugeren eksplicit har givet pr. station.
    uplift_rate_station = {}
    if uplift_station:
        with open(uplift_station) as f:
            lines = list(f)
            lines = [line.split(",") for line in lines]
            uplift_rate_station = {
                line[0].strip(): float(line[3].strip()) for line in lines
            }

    # Definer interpolator for uplift-grid.
    projstr = f"+proj=vgridshift +grids={uplift_grid} +multiplier=1"
    interpolator = Transformer.from_pipeline(projstr)

    # Find reference værdier for uplift:
    uplift_reference = {}
    for ts in tidsserier:
        # Indlæs reference værdi hvis givet på listeform
        if ts.punkt.gnss_navn in uplift_rate_station:
            uplift_reference[ts.navn] = uplift_rate_station[ts.punkt.gnss_navn]
            continue

        # Ellers interpolér
        lon, lat = ts.punkt.geometri.koordinater

        _, _, uplift_rate_interpoleret = interpolator.transform(lon, lat, 0)

        uplift_reference[ts.navn] = uplift_rate_interpoleret

    ts: GNSSTidsserie
    for ts in tidsserier:
        y = [skalafaktor * yy for yy in getattr(ts, parameter)]
        ts.forbered_lineær_regression(ts.decimalår, y, grad=grad, binsize=binsize)

        if parameter == "u":
            ts.linreg.hældning_reference = uplift_reference[ts.navn]

        try:
            ts.beregn_lineær_regression()
        except ValueError as e:
            print(f"Fejl ved løsning af tidsserien {ts.navn}:\n{e}")
            continue

        tsensemble.tilføj_tidsserie(ts)

    try:
        tsensemble.beregn_samlet_varians()
    except ValueError as e:
        raise SystemExit(e)

    # Gem statistik
    if ofil:
        outstr = tsensemble.generer_statistik_streng_ensemble(alpha=alpha)
        with open(ofil, "w") as f:
            f.write(outstr)

    if not plot:
        return

    # Plot analyseresultater
    for _, ts in tsensemble.tidsserier.items():
        plot_gnss_analyse(
            GNSS_TS_PLOTTING_LABELS[parameter], ts.linreg, alpha, er_samlet=True
        )


from fire.api.model import (Koordinat, Srid)
import numpy as np
import matplotlib.pyplot as plt
import os
def ts_skriv_gama_inputfil(projektnavn, fastholdte, estimerede_punkter, observationer):
    """
    Min egen version af "skriv_gama_inputfil", der kører in-memory.
    Kan bruges som udgangspunkt til senere refaktorisering..
    """

    xmlstr = str(f"<?xml version='1.0' ?><gama-local>\n"
        f"<network angles='left-handed' axes-xy='en' epoch='0.0'>\n"
        f"<parameters\n"
        f"    algorithm='gso' angles='400' conf-pr='0.95'\n"
        f"    cov-band='0' ellipsoid='grs80' latitude='55.7' sigma-act='aposteriori'\n"
        f"    sigma-apr='1.0' tol-abs='1000.0'\n"
        f"/>\n\n"
        f"<description>\n"
        f"    Nivellementsprojekt {ascii(projektnavn)}\n"  # Gama kaster op over Windows-1252 tegn > 127
        f"</description>\n"
        f"<points-observations>\n\n"
        "\n\n<!-- Fixed -->\n\n"
        )

    # Fastholdte punkter
    for punkt, kote in fastholdte.items():
        xmlstr += f"<point fix='Z' id='{punkt}' z='{kote}'/>\n"

    # Punkter til udjævning
    xmlstr += "\n\n<!-- Adjusted -->\n\n"
    for punkt in estimerede_punkter:
        xmlstr += f"<point adj='z' id='{punkt}'/>\n"

    # Observationer
    xmlstr += "<height-differences>\n"
    for sluk, fra, til, delta_H, L, type, opst, sigma, delta, journal in zip(
        observationer.sluk,
        observationer.fra,
        observationer.til,
        observationer.delta_H,
        observationer.L,
        observationer.type,
        observationer.opst,
        observationer.sigma,
        observationer.delta,
        observationer.journal,
    ):
        if sluk == "x":
            continue
        xmlstr += str(
            f"<dh from='{fra}' to='{til}' "
            f"val='{delta_H:+.6f}' "
            f"dist='{L:.5f}' stdev='{niv._regn.spredning(type, L, opst, sigma, delta):.5f}' "
            f"extern='{journal}'/>\n"
        )

    # Postambel
    xmlstr += str(
        "</height-differences>\n"
        "</points-observations>\n"
        "</network>\n"
        "</gama-local>\n"
    )

    return xmlstr

def udjævn_observationer_fra_sagevent(sei: str, projektnavn: str, fastholdte: dict):

    obs = fire.cli.firedb.session.query(Observation).filter(
        Observation._registreringtil == None,
        Observation.sagseventfraid == sei
    ).all()

    # Konverter observationer til list-of-dicts, som kan indlæses som pandas dataframe.
    obs_dict = [{"Journal":o.gruppe,
        "Sluk":None,
            "Fra": o.opstillingspunkt.ident,
            "Til": o.sigtepunkt.ident,
            "ΔH": o.koteforskel,
            "L": o.nivlængde,
            "Opst": o.opstillinger,
            "σ": o.spredning_afstand,
            "δ": o.spredning_centrering,
            "Kommentar": None,
            "Hvornår": o.observationstidspunkt,
            "T": None,
            "Sky": None,
            "Sol": None,
            "Vind": None,
            "Sigt": None,
            "Kilde": None,
            "Type": NivMetode(o.observationstypeid).name, # her antages at observationstypeid fra databasen er hardcoded og lig med enum-værdien.
            "uuid": o.id,
        } for o in obs]

    obs_df = pd.DataFrame(obs_dict) # den her skal ind i netanalysen

    observerede_punkter = set(list(obs_df["Fra"]) + list(obs_df["Til"]))

    (net, singulære) = niv._netoversigt.netgraf(obs_df, observerede_punkter, tuple(fastholdte.keys()))
    forbundne_punkter = tuple(sorted(net["Punkt"]))
    estimerede_punkter = tuple(sorted(set(forbundne_punkter) - set(fastholdte)))

    # Beregningstidspunktet skal svare til seneste observation
    # Tager nu højde for at nogle af observationerne ikke skal med forbi de ikke er i samme net som jessenpunktet.
    filter_forbundne = obs_df["Fra"].isin(forbundne_punkter)
    tidspunkt = max(obs_df[filter_forbundne]["Hvornår"])

    observationer = niv._regn.obs_til_dataklasse(obs_df)

    niv._regn.skriv_gama_inputfil(projektnavn, fastholdte, estimerede_punkter, observationer)

    # Kør GNU Gama
    htmlrapportnavn = niv._regn.gama_udjævn(projektnavn, False)

    punkter, koter, varianser = niv._regn.læs_gama_output(projektnavn)


    # Ryd op i filer
    os.remove(f"{projektnavn}.xml")
    os.remove(f"{projektnavn}-resultat.xml")
    os.remove(htmlrapportnavn)

    return punkter, koter, varianser, tidspunkt


from fire.api.model import (Koordinat, Srid, Observation, GeometriskKoteforskel, PunktInformation, PunktInformationType)
from sqlalchemy import or_, extract
from fire.cli import niv
from fire.api.niv.enums import NivMetode
import subprocess
import xmltodict
@ts.command()
@click.argument(
    "jessenpunkt_ident",
    required=False,
    type=str,
)
def adjniv(jessenpunkt_ident):

    # jessenpunkt = fire.cli.firedb.hent_punkt(jessenpunkt_ident)

    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1636')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1646')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1686')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1677')
    jessenpunkt = fire.cli.firedb.hent_punkt('K-35-09011')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.2111')

    fastholdte ={jessenpunkt.ident:6.0887,} # TODO: Mangler måde at finde fastholdt kote.

    # Grupper observationer pr sagsevent
    sagseventider = fire.cli.firedb.session.query(Observation.sagseventfraid).filter(
            Observation._registreringtil == None,
            or_(Observation.opstillingspunktid == jessenpunkt.id,
                Observation.sigtepunktid == jessenpunkt.id,
            ),
            # For ikke at få store sagsevents med, hvor observationer fra mange kampagner blev lagt i samtidigt.
            # Dette er imidlertid fixet med netanalyse.
            # extract('year', Observation.observationstidspunkt) >= 2000
        ).distinct().all()

    # Listegymnastik
    sagseventider = [sei[0] for sei in sagseventider]


    ### Ufærdigt forsøg på at finde Interessepunkter aka Points of interest aka POI ###

    # obs_nær_jessen = fire.cli.firedb.hent_observationer_naer_geometri(jessenpunkt.geometri.geometri, 200)
    # sigtepkt_nær_jessen = {o.sigtepunkt for o in obs_nær_jessen}
    # opstillingspkt_nær_jessen = {o.opstillingspunkt for o in obs_nær_jessen}
    # interessepunkter = sigtepkt_nær_jessen.union(opstillingspkt_nær_jessen)

    # interessepunkter = [p for p in interessepunkter if 'G.I.' in p.ident]

    data = {}
    for i, sei in enumerate(sagseventider):
        try:
            punkter, koter, varianser, tidspunkt = udjævn_observationer_fra_sagevent(sei, i, fastholdte)
        except Exception as e:
            print(f"Fejl ved udjævning af observationer fra sagsevent {sei}.")
            print(e)
            continue

        # Data indlæses for hvert punkt som en list-of-lists, i stil med:
        data: dict[str, list[list[pd.Timestamp,str,str]]]
        for punkt, kote, varians in zip(punkter, koter, varianser):
            try:
                data[punkt] = data[punkt] + [[tidspunkt, kote, varians]]
            except KeyError:
                data[punkt] = [[tidspunkt, kote, varians]]

    # GRIM plotting
    plt.figure()
    for key,val in data.items():

        # plotter kun GI punkter. Hænger sammen med ovenstående afsnit om POI.
        if "G.I." not in key:
            continue

        # NB! Kan løses meget smartere med Dataframe eller noget andet.

        val = np.array(val)
        x = val[:,0]
        xx = x[np.where(x!=datetime(1900,1,1))]
        idx_sorted = np.argsort(xx,)
        xx = xx[idx_sorted]

        y = val[:,1]
        yy = y[np.where(x!=datetime(1900,1,1))]
        yy = yy[idx_sorted]
        yy = yy-np.mean(yy)

        plt.plot(
        xx,
        yy,
        "-o",
        markersize=4,
        label = key
        )

    plt.legend()
    plt.grid()
    plt.show()




    return
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
    HøjdeTidsserie,
    Punkt,
)
from fire.api.model.tidsserier import (
    TidsserieEnsemble,
)

from fire.cli.ts import (
    _find_tidsserie,
    _print_tidsserieoversigt,
    _udtræk_tidsserie,
)
from ._plot_gnss import *

from . import ts

HTS_PARAMETRE = {
    "t": "t",
    "kote":"kote",
    "sz": "sz",
    "decimalår": "decimalår",
}


@ts.command()
@click.argument("objekt", required=False, type=str)
@click.option(
    "--parametre",
    "-p",
    required=False,
    type=str,
    default="t,kote,sz,decimalår",
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
def hts(objekt: str, parametre: str, fil: click.Path, **kwargs) -> None:
    """
    Udtræk en GNSS tidsserie.


    "OBJEKT" sættes til enten et punkt eller et specifik navngiven tidsserie.
    Hvis "OBJEKT" er et punkt udskrives en oversigt over de tilgængelige
    tidsserier til dette punkt. Hvis 'OBJEKT' er en tidsserie udskrives
    tidsserien på skærmen. Hvilke parametre der udskrives kan specificeres
    i en kommasepareret liste med ``--parametre``. Følgende parametre kan vælges::

    \b
        t               Tidspunkt for koordinatobservation
        kote            Koordinatens x-komponent (geocentrisk)
        sz              z-komponentens (kotens) spredning (i mm)
        decimalår       Tidspunkt for koordinatobservation i decimalår

    Tidsserien kan skrives til en fil ved brug af ``--fil``, der resulterer i
    en csv-fil på den angivne placering. Denne fil kan efterfølgende åbnes
    i Excel, eller et andet passende program, til videre analyse.

    \b
    **EKSEMPLER**

    Vis alle tidsserier for punktet RDIO::

        fire ts gnss RDIO

    Vis tidsserien (med det lange navn som skal ændres!):
    "Højdetidsserie for punkt G.I.2133 ift. Jessenpunkt 81066"
    med standardparametre::

        fire ts gnss "Højdetidsserie for punkt G.I.2133 ift. Jessenpunkt 81066"

    Vis tidsserie med brugerdefinerede parametre::

        fire ts gnss "Højdetidsserie for punkt G.I.2133 ift. Jessenpunkt 81066" --parametre decimalår,kote,sz

    Gem tidsserie med samtlige tilgængelige parametre::

        fire ts gnss "Højdetidsserie for punkt G.I.2133 ift. Jessenpunkt 81066" -p alle -f RDIO_HTS_81066.xlsx
    """
    _udtræk_tidsserie(objekt, HøjdeTidsserie, HTS_PARAMETRE, parametre, fil)

    return

@ts.command()
@click.argument("objekt", required=True, type=str)
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
    default="kote",
    help="Hvilken parameter skal plottes?",
)
@fire.cli.default_options()
def plot_hts(objekt: str, plottype: str, parametre: str, **kwargs) -> None:
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
        kote            Koordinatens x-komponent (geocentrisk)
        sz              z-komponentens (kotens) spredning (i mm)
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
    plot_funktioner = {
        "rå": plot_data,
        "fit": plot_fit,
        "konf": plot_konfidensbånd,
    }

    # try:
    #     tidsserie = _find_tidsserie(HøjdeTidsserie, tidsserie)
    # except NoResultFound:
    #     raise SystemExit("Tidsserie ikke fundet")

    # Prøv først med at søg efter specifik tidsserie
    try:
        tidsserie = _find_tidsserie(HøjdeTidsserie, objekt)
    except NoResultFound:
        try:
            punktsamling = fire.cli.firedb.hent_punktsamling(objekt)
            tidsserier = punktsamling.tidsserier
            fig = plt.figure()
            plt.suptitle(punktsamling.navn)
            for ts in tidsserier:
                x = np.array(ts.decimalår)
                idx_sorted = np.argsort(x,)
                x = x[idx_sorted]

                y = np.array(ts.kote)
                y = y[idx_sorted]
                y = y-np.mean(y)

                plt.plot(
                x,
                y,
                "-o",
                markersize=4,
                label = ts.punkt.ident
                )
            plt.show()

        except NoResultFound:
            raise SystemExit("Tidsserie eller Punktsamling ikke fundet")

        raise SystemExit


    parametre = parametre.split(",")

    for parm in parametre:
        if parm not in HTS_PARAMETRE.keys():
            raise SystemExit(f"Ukendt tidsserieparameter '{parm}'")

    parametre = [HTS_PARAMETRE[parm] for parm in parametre]

    plot_gnss_ts(tidsserie, plot_funktioner[plottype], parametre, y_enhed="mm")



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
    # fire.cli._set_database("","","test")
    # jessenpunkt = fire.cli.firedb.hent_punkt(jessenpunkt_ident)

    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1636')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1646')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1686')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.1677')
    jessenpunkt = fire.cli.firedb.hent_punkt('GED2')
    # jessenpunkt = fire.cli.firedb.hent_punkt('G.I.2111')
    print(jessenpunkt.ident)


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

    print(sagseventider)
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
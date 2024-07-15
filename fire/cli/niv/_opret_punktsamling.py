import re
import getpass
from datetime import datetime
from math import trunc, isnan

import click
import pandas as pd
from pyproj import Proj, Geod

from sqlalchemy.exc import (
    DatabaseError,
    NoResultFound,
    IntegrityError,
)
from fire import uuid

from fire.io.regneark import (
    nyt_ark,
    arkdef,
)
import fire.io.dataframe as frame


from fire.api.model import (
    Punkt,
    PunktSamling,
    Koordinat,
    Tidsserie,
    HøjdeTidsserie,
)

import fire.cli
from fire.cli.niv._udtræk_revision import LOKATION_DEFAULT
from fire.cli.niv import (
    bekræft,
    find_faneblad,
    find_sag,
    find_sagsgang,
    niv,
    skriv_ark,
    opret_region_punktinfo,
    er_projekt_okay,
)


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


@niv.command()
@fire.cli.default_options()
@click.argument(
    "projektnavn",
    nargs=1,
    type=str,
)
@click.option(
    "--sagsbehandler",
    default=getpass.getuser(),
    type=str,
    help="Angiv andet brugernavn end den aktuelt indloggede",
)
@click.option(
    "--punktsamlingsnavn",
    default = "",
    type=str,
    help="Angiv punktsamlingens navn",
)
def opret_punktsamling(
    # jessenpunkt_ident: str,
    # navn: str,
    # formål: str,
    projektnavn: str,
    sagsbehandler: str,
    punktsamlingsnavn: str,
    **kwargs,
) -> None:
    """
    Opretter et Punktsamlings-ark på sagen, som efterfølgende kan redigeres.

    Derefter kan punktsamlingen lægges i databasen med ilæg-punktsamling!

    """
    er_projekt_okay(projektnavn)

    # Opbyg Punktsamling ud fra Punktoversigten
    punktoversigt = find_faneblad(projektnavn, "Punktoversigt", arkdef.PUNKTOVERSIGT)

    # Valider oplysningerne om Punktsamlingen baseret på Punktoversigt-arket
    jessenpunkt_ident, jessenpunkt = valider_punktsamling(punktoversigt)

    # Prøv at hente punktsamlingen ud fra givet navn, hvis den findes
    pktsamlinger: list[PunktSamling] = []
    if punktsamlingsnavn:
        try:
            pktsamlinger = fire.cli.firedb.hent_punktsamling(punktsamlingsnavn)
        except NoResultFound:
            fire.cli.print(f"Ingen punktsamlinger fundet ved navn {punktsamlingsnavn}")
        else:
            # Sikr at den fundne Punktsamling også har korrekt Jessenpunkt
            pktsamlinger = [ps for ps in pktsamlinger if ps.jessenpunktid ==  jessenpunkt.id]

    # Hvis intet Punktsamlingsnavn er givet, eller ingen Punktsamlinger blev fundet, så
    # finder vi alle punktsamlinger hvor jessenpunkt indgar
    if not pktsamlinger:
        pktsamlinger = jessenpunkt.punktsamlinger
        pktsamlinger = [ps for ps in pktsamlinger if ps.jessenpunktid ==  jessenpunkt.id]

    pktsamlinger: list[PunktSamling]
    if pktsamlinger:
        # Vi fandt nogle punktsamlinger!
        # TODO: Her kan man måske bruge regnearksfunktionaliteten "til_nyt_ark"

        # Punktsamlingsdata
        ps_data = {
            (
                ps.navn,
                jessenpunkt_ident,
                ps.jessenpunkt.jessennummer,
                ps.jessenkoordinat.z,
                ps.formål,
            )
            for ps in pktsamlinger
        }

        # Højdetidsseriedata
        hts_data: set[tuple] = set()
        for ps in pktsamlinger:
            print(f"========================== Behandler punktsamling '{ps.navn}' ==========================")
            # 1) Tilføj punkter som allerede findes i Punktsamlingen

            # 1.1) Start med at gå ud fra puntksamlingens tidsserier
            punkter_med_tidsserie = set()
            for ts in ps.tidsserier:
                punkter_med_tidsserie.add(ts.punkt.ident)
                hts_data.add(
                    (
                        ps.navn,
                        ts.punkt.ident,
                        ("x" if ts.punkt==ps.jessenpunkt else ""),
                        ts.navn,
                        ts.formål,
                        ts.referenceramme,
                    )
                )
            print(f"Punkter i PS med tidsserie: {punkter_med_tidsserie}")
            # 1.2) Derefter tager vi de resterende punkter i punktsamlingen
            #      som ikke nødvendigvis har en tidsserie. Fx ved nyoprettede
            #      Punktsamlinger.

            tilføjede_punkter = punkter_med_tidsserie.copy()
            for pkt in ps.punkter:

                if pkt.ident in tilføjede_punkter:
                    continue

                tilføjede_punkter.add(pkt.ident)

                # Debug print
                print(f"Punkt {pkt.ident} er med i Punktsamling {ps.navn} men har ingen tidsserier.")

                hts_data.add(
                    (
                        ps.navn,
                        pkt.ident,
                        ("x" if pkt==ps.jessenpunkt else ""),
                        "", # navn
                        "", # formål
                        "Jessen", # ref system
                    )
                )
            print(f"Punkter i PS uden tidsserie: {tilføjede_punkter-punkter_med_tidsserie}")
            print(f"Tilføjede punkter : {tilføjede_punkter}")


            # 2) Tilføj punkterne fra Punktoversigten, som ikke allerede er tilføjet.

            # TODO: Overvej om dette er nødvendigt. Fx kan der godt være målt til punkter
            # som ikke nødvendigvis skal med i punktgruppen.

            # Looop over punktoversigt
            for idx, row in punktoversigt.iterrows():

                # Prøv at hente punktet fra db og find punktets kanoniske ident
                # Grunden er igen at Punkt-kolonnen i Punktoversigten ikke nødvendigvis
                # indeholder den kanoniske ident, hvilket er den som bruges ovenfor når
                # vi trækker punkterne ud af db via tidsserie eller punktsamling.
                try:
                    pkt = fire.cli.firedb.hent_punkt(row["Punkt"])
                except NoResultFound:
                    pkt_ident = row["Punkt"]
                else:
                    pkt_ident = pkt.ident

                # Hvis vi allerede har tilføjet punktet fordi det findes som en del
                # af punktsamlingen i databasen.
                if pkt_ident in tilføjede_punkter:
                    continue

                # Ellers må det være et nyt punkt som skal føjes til punktsamlingen!
                hts_data.add(
                    (
                        ps.navn,
                        pkt_ident,
                        row["Fasthold"],
                        "", # navn
                        "", # formål
                        "Jessen", # ref system
                    )
                )

    else:
        # Hvis vi stadig ikke kan finde nogen Punktsamlinger, så må det være fordi vi er ved
        # at oprette en helt ny punktsamling

        # Indsæt i arket
        ps_data = {
            (
                punktsamlingsnavn,
                jessenpunkt_ident,
                jessenpunkt.jessennummer,
                punktoversigt["Kote"][punktoversigt["Punkt"]==jessenpunkt_ident].iloc[0], # Jessenkote
                "", # Formål
            )
        }


        hts_data = {
            (
                punktsamlingsnavn,
                row["Punkt"],
                row["Fasthold"],
                "", # navn
                "", # formål
                "Jessen", # ref system
            )
            for idx, row in punktoversigt.iterrows()
         }


    # Opret ark som skal gemmes.
    punktsamling = pd.DataFrame.from_records(data=list(ps_data), columns = arkdef.PUNKTGRUPPE)

    højdetidsserie = pd.DataFrame.from_records(data=list(hts_data), columns = arkdef.HØJDETIDSSERIE)

    # Sorter højdetidsserie-arket
    højdetidsserie.sort_values(by=["Punktgruppenavn", "Er Jessenpunkt", "Tidsserienavn", "Punkt"], ascending = [True, False, False, True], inplace=True)

    resultater = {
        "Punktgruppe": punktsamling,
        "Højdetidsserier": højdetidsserie
    }

    if skriv_ark(projektnavn, resultater):
        fire.cli.print(
            f"Punktsamlings-ark oprettet. Udfyld nu Punktsamlingsnavn, Formål og Jessenkote "
            f"eller kontrollér at oplysningerne er korrekte."
        )
        fire.cli.åbn_fil(f"{projektnavn}.xlsx")



    # TODO: Måske er vi ligeglade med Kotesystem her når der oprettes Punktsamlinger.
    # TODO: Kotesystem kan i princippet godt være andet (fx LRL eller andet)?

    # fastholdt_kote = punktoversigt.at[jessenpunkt, "Kote"]
    # if pd.isna(fastholdt_kote):
    #     fire.cli.print(
    #         "FEJL: Ingen fastholdt kote",
    #         fg="white",
    #         bg="red",
    #         bold=True,
    #         )
    #     raise SystemExit(1)
    # print(fastholdt_kote)

    return



@niv.command()
@fire.cli.default_options()
@click.argument(
    "projektnavn",
    nargs=1,
    type=str,
)
@click.option(
    "--sagsbehandler",
    default=getpass.getuser(),
    type=str,
    help="Angiv andet brugernavn end den aktuelt indloggede",
)
@click.option(
    "--punktsamlingsnavn",
    default = "",
    type=str,
    help="Angiv punktsamlingens navn",
)
def ilæg_punktsamling(
    # jessenpunkt_ident: str,
    # navn: str,
    # formål: str,
    projektnavn: str,
    sagsbehandler: str,
    punktsamlingsnavn: str,
    **kwargs,
) -> None:

    er_projekt_okay(projektnavn)
    sag = find_sag(projektnavn)
    sagsgang = find_sagsgang(projektnavn)

    fire.cli.print(f"Sags/projekt-navn: {projektnavn}  ({sag.id})")
    fire.cli.print(f"Sagsbehandler:     {sagsbehandler}")

    # Læs arkene
    punktgruppe_ark = find_faneblad(projektnavn, "Punktgruppe", arkdef.PUNKTGRUPPE)
    hts_ark = find_faneblad(projektnavn, "Højdetidsserier", arkdef.HØJDETIDSSERIE)
    # hts_ark = hts_ark.set_index("Punktgruppenavn")

    # hent kotesystem. Lige nu understøttes kun jessen-system.
    # Mest pga. kolonnenavne i database (jessenkoordinat/kote).
    # Kunne ellers godt have punktsamlinger i andre kotesystemer
    kotesystem = fire.cli.firedb.hent_srid("TS:jessen")

    # Initialisér variable som bruges til logning
    koord_til_oprettelse = list()
    pktsamling_til_redigering = list()
    pktsamling_til_oprettelse = list()
    antal_punkter_i_pktsamling_til_oprettelse = 0
    antal_punkter_i_pktsamling_til_redigering = 0

    for index, punktgruppedata in punktgruppe_ark.iterrows():

        # ================= 1. INDLEDENDE HENTNING AF DATA FRA ARK OG DATABASE =================

        punktgruppenavn = punktgruppedata["Punktgruppenavn"]
        angivet_jessenkote = punktgruppedata["Jessenkote"]
        formål = punktgruppedata["Formål"]

        fire.cli.print(f"Behandler punktgruppe {punktgruppenavn}")

        jessenpunkt = fire.cli.firedb.hent_punkt(punktgruppedata["Jessenpunkt"])

        punktliste = list(hts_ark["Punkt"][hts_ark["Punktgruppenavn"]==punktgruppenavn])
        punkter_i_punktgruppe = fire.cli.firedb.hent_punkt_liste(punktliste)

        # ================= 2A. REDIGER EKSISTERENDE PUNKTGRUPPE =================

        try:
            eksisterende_punktsamling = fire.cli.firedb.hent_punktsamling(punktgruppenavn)
        except NoResultFound:
            # Gør ikke noget. Gå videre til 2B for at oprette ny
            pass
        else:
            fire.cli.print(
                f"Punktgruppe {punktgruppenavn} findes i forvejen. \n"
                f"Brug 'rediger-punktsamling' til at redigere oplysninger om punktsamlinger."
            )
            # Læs punkter og opdater listen.
            punkter_i_eksisterende_punktsamling = set(eksisterende_punktsamling.punkter)

            punkter_til_tilføjelse = set(punkter_i_punktgruppe) - punkter_i_eksisterende_punktsamling

            # Opdaterer eksisterende punktsamling med nye punkter
            eksisterende_punktsamling.punkter.extend(punkter_til_tilføjelse)

            # Ved ikke om vi skal opdatere formål. Dette indsætter ny historik (T2)-række i i Punktsamling, som leder
            # til ny objektid og så går der kludder i mappingen til Punktsamling_Punkt?
            # Medmindre vi rent faktisk opdaterer Formål-feltet (som med T1 historik), så er der ikke noget problem.
            # TODO: Snak med Evers om SQL Alchemy igen.

            flag = 0
            if  eksisterende_punktsamling.formål != formål:
                flag = 1
                eksisterende_punktsamling.formål = formål
            elif len(punkter_til_tilføjelse) > 0:
                flag = 1

            if flag == 1:
                pktsamling_til_redigering.append(eksisterende_punktsamling)
                antal_punkter_i_pktsamling_til_redigering += len(punkter_til_tilføjelse)

            continue


        # ================= 2B. OPRET NY PUNKTGRUPPE =================

        try:
            # Filterer med vilje ikke på RegistreringTil = None, idet jessenpunktet godt
            # kan have tidsserier i andre punktsamlinger, hvis tidsserie-koordinater også
            # har SRID'en TS:jessen.
            # RegistreringTil = None vil kun finde det nyeste koord. som altså kan ændre
            # kote.
            # Der forventes kun ét resultat, men søgningen kan i edge-cases returnere
            # flere koordinater med identisk z-værdi, hvorfor der bare tages den først
            # fundne, som også burde være den første i tid.
            jessenkoordinat = [k
                        for k in jessenpunkt.koordinater
                        if k.srid == kotesystem and k.z ==  angivet_jessenkote
                        ][0]
        except IndexError:
            fire.cli.print(
                f"BEMÆRK: Jessenkote ikke fundet i databasen. \n"
                f"Forsøger at oprette nyt Jessenkoordinat med koten {angivet_jessenkote} [m]",
                fg="black",
                bg="yellow",
            )

            jessenkoordinat = Koordinat(
                punkt = jessenpunkt,
                srid = kotesystem,
                # hvilket tidspunkt skal den nye jessenkote gælde fra?
                # default er "current_timestamp"
                # t=None,
                z = angivet_jessenkote,
                sz = 0,
                )
            koord_til_oprettelse.append(jessenkoordinat)
        else:
            jessenkote = jessenkoordinat.z

        # Opretter ny ny punktsamling
        ny_punktsamling = PunktSamling(
            navn = punktgruppenavn,
            jessenpunkt = jessenpunkt,
            jessenkoordinat = jessenkoordinat,
            # TODO: Tidsserier oprettes med anden funktionalitet.
            # Ellers tror jeg den her funktion bliver overloaded.
            # tidsserier = None,
            formål = formål,
            punkter = punkter_i_punktgruppe,
        )

        pktsamling_til_oprettelse.append(ny_punktsamling)
        antal_punkter_i_pktsamling_til_oprettelse += len(punkter_i_punktgruppe)

    if not (koord_til_oprettelse or pktsamling_til_redigering or pktsamling_til_oprettelse):
        fire.cli.print(f"Ingen punktsamlinger at oprette eller redigere. Afbryder!", fg="yellow", bold=True)
        return

    # ================= 3A. SAGSEVENT REDIGER PUNKTSAMLING =================
    if pktsamling_til_redigering:
        psnavne = "'" + "', '".join([ps.navn for ps in pktsamling_til_redigering]) + "'"
        sagsevent_rediger_punktsamlinger = sag.ny_sagsevent(
            id=uuid(),
            beskrivelse=f"Redigering af punktsamlingerne {psnavne}",
            punktsamlinger = pktsamling_til_redigering,
        )
        fire.cli.firedb.indset_sagsevent(sagsevent_rediger_punktsamlinger, commit=False)
        try:
            fire.cli.firedb.session.flush()
        except Exception as ex:
            # rul tilbage hvis databasen smider en exception
            fire.cli.firedb.session.rollback()
            raise ex

        # Generer dokumentation til fanebladet "Sagsgang"
        sagsgangslinje = {
            "Dato": sagsevent_rediger_punktsamlinger.registreringfra,
            "Hvem": sagsbehandler,
            "Hændelse": "Punktsamling modificeret",
            "Tekst": sagsevent_rediger_punktsamlinger.sagseventinfos[0].beskrivelse,
            "uuid": sagsevent_rediger_punktsamlinger.id,
        }
        sagsgang = frame.append(sagsgang, sagsgangslinje)



    # ================= 3B. SAGSEVENT OPRET PUNKTSAMLING =================
    # === DEL 3B.1: Opret Jessenkoordinat som ikke findes i forvejen ===
    if koord_til_oprettelse:

        jessenpunkter = "'" + "', '".join([k.punkt.ident for k in koord_til_oprettelse]) + "'"
        sagsevent_nye_jessenkoter = sag.ny_sagsevent(
            id=uuid(),
            # TODO: Anvend kotesystem.shortname når denne er implementeret
            beskrivelse=f"Indsættelse af ny {kotesystem.name}-kote for punkterne {jessenpunkter}",
            koordinater = koord_til_oprettelse,
        )
        fire.cli.firedb.indset_sagsevent(sagsevent_nye_jessenkoter, commit=False)
        try:
            fire.cli.firedb.session.flush()
        except Exception as ex:
            # rul tilbage hvis databasen smider en exception
            fire.cli.firedb.session.rollback()
            raise ex

        # Generer dokumentation til fanebladet "Sagsgang"
        sagsgangslinje = {
            "Dato": sagsevent_nye_jessenkoter.registreringfra,
            "Hvem": sagsbehandler,
            "Hændelse": "Jessenkote(r) indsat",
            "Tekst": sagsevent_nye_jessenkoter.sagseventinfos[0].beskrivelse,
            "uuid": sagsevent_nye_jessenkoter.id,
        }
        sagsgang = frame.append(sagsgang, sagsgangslinje)

    if pktsamling_til_oprettelse:
        # === DEL 3B.2: Opret Punktsamlingen ===
        psnavne = "'" + "', '".join([ps.navn for ps in pktsamling_til_oprettelse]) + "'"
        sagsevent_opret_punktsamlinger = sag.ny_sagsevent(
            id=uuid(),
            beskrivelse=f"Oprettelse af punktsamlingerne {psnavne}",
            punktsamlinger = pktsamling_til_oprettelse,
        )
        fire.cli.firedb.indset_sagsevent(sagsevent_opret_punktsamlinger, commit=False)
        try:
            fire.cli.firedb.session.flush()
        except Exception as ex:
            # rul tilbage hvis databasen smider en exception
            fire.cli.firedb.session.rollback()
            raise ex

        # Generer dokumentation til fanebladet "Sagsgang"
        sagsgangslinje = {
            "Dato": sagsevent_opret_punktsamlinger.registreringfra,
            "Hvem": sagsbehandler,
            "Hændelse": "Punktsamling(er) oprettet",
            "Tekst": sagsevent_opret_punktsamlinger.sagseventinfos[0].beskrivelse,
            "uuid": sagsevent_opret_punktsamlinger.id,
        }
        sagsgang = frame.append(sagsgang, sagsgangslinje)


    indsæt_kote_tekst = f"- indsætte {len(koord_til_oprettelse)} {kotesystem.name}-kote(r)"
    opret_tekst = f"- oprette {len(pktsamling_til_oprettelse)} nye punktsamlinger med i alt {antal_punkter_i_pktsamling_til_oprettelse} punkter"
    tilføj_tekst = f"- tilføje {antal_punkter_i_pktsamling_til_redigering} punkter fordelt på {len(pktsamling_til_redigering)} eksisterende punktsamlinger"
    # ret_tekst = f"- rette {len(nye_lokationer)} formålsbeskrivelse"

    fire.cli.print("")
    fire.cli.print("-" * 50)
    fire.cli.print("Punktsamlinger færdigbehandlet, klar til at")
    fire.cli.print(indsæt_kote_tekst)
    fire.cli.print(opret_tekst)
    fire.cli.print(tilføj_tekst)

    spørgsmål = click.style(f"Er du sikker på du vil indsætte ovenstående i ", fg="white", bg="red")
    spørgsmål += click.style(f"{fire.cli.firedb.db}", fg="white", bg="red", bold=True)
    spørgsmål += click.style("-databasen?", fg="white", bg="red")

    if bekræft(spørgsmål):
        # Bordet fanger!
        fire.cli.firedb.session.commit()

        # Skriver opdateret sagsgang til excel-ark
        resultater = {"Sagsgang": sagsgang}
        if skriv_ark(projektnavn, resultater):
            fire.cli.print(f"Punktsamlinger registreret.")
    else:
        fire.cli.firedb.session.rollback()

    return

    # sagsevent_punktsamlinger = sag.ny_sagsevent(
    #     punktsamlinger=ps,
    #     beskrivelse="fire niv opret-punktsamling: Opret tom Punktsamling",
    # )

    # fire.cli.firedb.indset_sagsevent(sagsevent_punktsamlinger, commit=False)
    # try:
    #     fire.cli.firedb.session.flush()
    # except IntegrityError as ex:
    #     # Hvis man forsøger at indsætte Punktsamling med navn som findes i forvejen
    #     fire.cli.firedb.session.rollback()
    #     # fejlende_punkt = fire.cli.firedb.hent_punkt(ex.params["punktid"])
    #     # TODO: Implementer bedre fejlrapportering.
    #     fire.cli.print("Fejl ved indsættelse af Punktsamlinger.")



@niv.command()
@fire.cli.default_options()
@click.argument(
    "projektnavn",
    nargs=1,
    type=str,
)
@click.option(
    "--sagsbehandler",
    default=getpass.getuser(),
    type=str,
    help="Angiv andet brugernavn end den aktuelt indloggede",
)
def ilæg_tidsserie(
    # jessenpunkt_ident: str,
    # navn: str,
    # formål: str,
    projektnavn: str,
    sagsbehandler: str,
    # punktsamlingsnavn: str,
    **kwargs,
) -> None:
    """
    Ilæg en ny Højdetidsserie eller rediger en eksisterende (kan kun redigere "Formål")

    Anvender arket Højdetidsserier.
    """

    er_projekt_okay(projektnavn)
    sag = find_sag(projektnavn)
    sagsgang = find_sagsgang(projektnavn)

    fire.cli.print(f"Sags/projekt-navn: {projektnavn}  ({sag.id})")
    fire.cli.print(f"Sagsbehandler:     {sagsbehandler}")

    # Læs arkene
    # punktgruppe_ark = find_faneblad(projektnavn, "Punktgruppe", arkdef.PUNKTGRUPPE)
    hts_ark = find_faneblad(projektnavn, "Højdetidsserier", arkdef.HØJDETIDSSERIE)


    # hent kotesystem. Lige nu understøttes kun jessen-system.
    # Mest pga. kolonnenavne i database (jessenkoordinat/kote).
    # Kunne ellers godt have punktsamlinger i andre kotesystemer
    kotesystem = fire.cli.firedb.hent_srid("TS:jessen")

    ts_til_redigering=[]
    ts_til_oprettelse=[]
    for index, row in hts_ark.iterrows():
        try:
            ts = fire.cli.firedb.hent_tidsserie(row["Tidsserienavn"])
        except NoResultFound:
            fire.cli.print(f"Kunne ikke finde tidsserie: {row['Tidsserienavn']}. Opretter ny tidsserie.")

            # Her smides fejl hvis punkt eller punktgruppe ikke kan findes!
            punkt = fire.cli.firedb.hent_punkt(row["Punkt"])
            ps = fire.cli.firedb.hent_punktsamling(row["Punktgruppenavn"])


            # Hvis punktet er jessenpunkt, så oprettes tidsserien med punktsamlingens jessenpunkt.
            # Ellers er tidsserien bare tom
            koordinat = []
            if ps.jessenpunkt == punkt:
                koordinat = [ps.jessenkoordinat,]

            ts = HøjdeTidsserie(
                navn = row["Tidsserienavn"],
                punkt = punkt,
                punktsamling = ps,
                formål = row["Formål"],
                referenceramme = "Jessen",
                srid = kotesystem,
                # De her to behøves ikke
                # tstype=2,
                koordinater = koordinat,
            )
            ts_til_oprettelse.append(ts)
            pass
        else:
            if ts.formål == row["Formål"]:
                continue
            ts.formål == row["Formål"]
            ts_til_redigering.append(ts)


    #================= 3A. SAGSEVENT REDIGER TIDSSERIE =================
    if ts_til_redigering:
        tsnavne = "'" + "', '".join([ts.navn for ts in ts_til_redigering]) + "'"
        sagsevent_rediger_tidsserier = sag.ny_sagsevent(
            id=uuid(),
            beskrivelse=f"Redigering af tidsserierne {tsnavne}",
            tidsserier = ts_til_redigering,
        )
        fire.cli.firedb.indset_sagsevent(sagsevent_rediger_tidsserier, commit=False)
        try:
            fire.cli.firedb.session.flush()
        except Exception as ex:
            # rul tilbage hvis databasen smider en exception
            fire.cli.firedb.session.rollback()
            raise ex

        # Generer dokumentation til fanebladet "Sagsgang"
        sagsgangslinje = {
            "Dato": sagsevent_rediger_tidsserier.registreringfra,
            "Hvem": sagsbehandler,
            "Hændelse": "Tidsserie modificeret",
            "Tekst": sagsevent_rediger_tidsserier.sagseventinfos[0].beskrivelse,
            "uuid": sagsevent_rediger_tidsserier.id,
        }
        sagsgang = frame.append(sagsgang, sagsgangslinje)

    #================= 3B. SAGSEVENT OPRET TIDSSERIE =================
    if ts_til_oprettelse:
        tsnavne = "'" + "', '".join([ts.navn for ts in ts_til_oprettelse]) + "'"
        sagsevent_opret_tidsserier = sag.ny_sagsevent(
            id=uuid(),
            beskrivelse=f"Oprettelse af tidsserierne {tsnavne}",
            tidsserier = ts_til_oprettelse,
        )
        fire.cli.firedb.indset_sagsevent(sagsevent_opret_tidsserier, commit=False)
        try:
            fire.cli.firedb.session.flush()
        except Exception as ex:
            # rul tilbage hvis databasen smider en exception
            fire.cli.firedb.session.rollback()
            raise ex

        # Generer dokumentation til fanebladet "Sagsgang"
        sagsgangslinje = {
            "Dato": sagsevent_opret_tidsserier.registreringfra,
            "Hvem": sagsbehandler,
            "Hændelse": "Tidsserie oprettet",
            "Tekst": sagsevent_opret_tidsserier.sagseventinfos[0].beskrivelse,
            "uuid": sagsevent_opret_tidsserier.id,
        }
        sagsgang = frame.append(sagsgang, sagsgangslinje)

    # indsæt_kote_tekst = f"- indsætte {len(koord_til_oprettelse)} {kotesystem.name}-kote(r)"
    opret_tekst = f"- oprette {len(ts_til_oprettelse)} nye højdetidsserier"
    ret_tekst = f"- rette formål på {len(ts_til_redigering)} højdetidsserier"

    fire.cli.print("")
    fire.cli.print("-" * 50)
    fire.cli.print("Tidsserier færdigbehandlet, klar til at")
    fire.cli.print(opret_tekst)
    fire.cli.print(ret_tekst)

    spørgsmål = click.style(f"Er du sikker på du vil indsætte ovenstående i ", fg="white", bg="red")
    spørgsmål += click.style(f"{fire.cli.firedb.db}", fg="white", bg="red", bold=True)
    spørgsmål += click.style("-databasen?", fg="white", bg="red")

    if bekræft(spørgsmål):
        # Bordet fanger!
        fire.cli.firedb.session.commit()

        # Skriver opdateret sagsgang til excel-ark
        resultater = {"Sagsgang": sagsgang}
        if skriv_ark(projektnavn, resultater):
            fire.cli.print(f"Tidsserier registreret.")
    else:
        fire.cli.firedb.session.rollback()

    return












def find_jessenpunkt(punktoversigt: pd.DataFrame):
    """
    Finder Jessenpunktet ud fra oplysningerne i Punktoversigten.

    Returnerer oplysninger om det validerede jessenpunkt.
    """

    # Tjek om der er anvendt Jessen-system
    # Denne er et sanity-tjek -- Man skal ville det hvis man vil oprette punktsamlinger!
    if len(set(punktoversigt["System"])) > 1:
        fire.cli.print(
            "FEJL: Flere forskellige højdereferencesystemer er angivet i Punktoversigt!",
            fg="white",
            bg="red",
            bold=True,
        )
        raise SystemExit(1)

    kotesystem = punktoversigt["System"].iloc[0]
    if kotesystem != "Jessen":
        fire.cli.print(
            "FEJL: Kotesystem skal være 'Jessen'",
            fg="white",
            bg="red",
            bold=True,
        )
        raise SystemExit(1)

    # Tjek om der kun er ét fastholdt punkt, og gør brugeren opmærksom på hvis punktet
    # ikke har et Jessennummer.
    fastholdte_punkter = punktoversigt["Punkt"][punktoversigt["Fasthold"] == "x"]
    fastholdte_koter = punktoversigt["Kote"][punktoversigt["Fasthold"] == "x"]

    if len(fastholdte_punkter)!=1:
        fire.cli.print(
            "FEJL: Punktsamlinger kræver netop ét fastholdt Jessenpunkt.",
            fg="white",
            bg="red",
            bold=True,
        )
        raise SystemExit(1)

    if pd.isna(fastholdte_koter).any():
        fire.cli.print(
            "FEJL: Fastholdt punkt har ikke nogen fastholdt kote!",
            fg="white",
            bg="red",
            bold=True,
        )
        raise SystemExit(1)

    jessenpunkt_ident = fastholdte_punkter.iloc[0]
    jessenpunkt_kote = fastholdte_koter.iloc[0]

    try:
        jessenpunkt = fire.cli.firedb.hent_punkt(jessenpunkt_ident)
    except NoResultFound:
        fire.cli.print(
            f"FEJL: Kunne ikke finde Jessenpunktet {jessenpunkt_ident} i databasen!",
            fg="white",
            bg="red",
            bold=True,
        )
        raise SystemExit(1)

    if not jessenpunkt.jessennummer:
        fire.cli.print(
            f"FEJL: Fastholdt Jessenpunkt {jessenpunkt.ident} har intet Jessennummer. "
            "Jessennummer kan oprettes igennem Punktrevision ved indsættelse af IDENT:jessen og NET:jessen.",
            fg="black",
            bg="yellow",
            )
        raise SystemExit(1)

    return jessenpunkt_kote, jessenpunkt


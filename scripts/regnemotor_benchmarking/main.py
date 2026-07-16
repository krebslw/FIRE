import csv
import tempfile
import subprocess
import shutil

import numpy as np

from dataclasses import asdict, dataclass, fields
from pathlib import Path
from sqlalchemy.sql import text
from time import perf_counter
from zipfile import ZipFile


from fire.api import FireDb
from fire.api.niv.datatyper import (
    NivKote
)
from fire.api.niv.regnemotor import (
    RegneMotor,
    SmartRegn,
    GamaRegn,
    ValideringFejl,
)
from fire.cli.pretty_tables import (gem_til_excel)
from fire.cli.niv import (
    find_faneblad,
)
from fire.io.regneark import arkdef


FIREDB = FireDb(db="prod")

@dataclass
class Valideringsresultat:
    status: str
    n_fastholdte: int
    n_beregnede: int
    smart_tid: float
    gama_tid: float
    tidsforskel_s: float
    tidsforskel_pct: float

    def header(self):
        return [str(field.name) for field in fields(self)]

    def row(self):
        return [getattr(self, field.name) for field in fields(self)]


def ny_resultatmappe():
    """Opret mappe ny til valideringsresultater"""
    sti = Path(r"C:\FIRE-DEV\scripts\regnemotor_benchmarking")
    j = 1
    while True:
        mappe = Path(f"run{j}")
        try:
            mappe_dest = (sti/mappe)
            mappe_dest.mkdir(parents=True)
            break
        except FileExistsError:
            j += 1
    return mappe_dest

def valider_fra_Fdrev(gem_alle_sager: bool = False):
    """
    Brug alle læsbare niv-ark fra F-drevet som grundlag for benchmarking
    """
    nivopgaver = Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver")

    resultatmappe = ny_resultatmappe()

    def _loop_over_mapper(pattern: str = ""):
        år = ["2001"] + list(str(i) for i in range(2015,2029))

        for å in år:
            path = nivopgaver / Path(å)
            for p in path.rglob(f"{pattern or '*'}.xlsx"):
                if p.is_dir():
                    continue

                # Only read excel files that dont end with -revision or -ex
                if not p.suffix == ".xlsx" or p.stem.endswith("-revision") or p.stem.endswith("-ex"):
                    continue

                yield p

    n_alle=0
    n_læsbar=0
    benchmark_results=[]

    for i, p in enumerate(_loop_over_mapper()):
    # for i, p in enumerate([
    #     Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver\2020\VEDL_SLAGELSE\TEST_db\2020_VEDL_SLAGELSE.xlsx"),
    #     Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver\2021\HAVN_SKIVE\Rene\2021_skive_havn.xlsx"),
    #     Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver\2022\KDI_VESTKYST_NORD\DEL BEREGNINGER\VISBY-KLINKBY\2022_VISBY_KLINKBY.xlsx"),
    #     Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver\2025\NIVEAU_NYBORG\ALLE_OBS_FRA_FIRE\2025_NIVEAU_NYBORG.xlsx"),
    #     Path(r"F:\GDL\Data\GEO\BC\Niv_Opgaver\2021\FJERN_NAER_FYNO\2021_FJERN_NAER_FYNO.xlsx"),
    #     Path(r"C:\FIRE-DEV\scripts\regnemotor_benchmarking\deepdive\2021_FJERN_NAER_FYNO.xlsx"),
    #     Path(r"C:\FIRE-DEV\scripts\regnemotor_benchmarking\deepdive\selfloop\selfloop.xlsx"),
    #     Path(r"C:\FIRE-DEV\scripts\regnemotor_benchmarking\deepdive\subnet\subnet.xlsx"),
    #     # Path(r"C:\FIRE-DEV\tester\3prs\3prs.xlsx"),
    # ]):
        print(f"{p}")

        # Remove suffix
        projektnavn = p.with_suffix("")

        # Try to read the excel file. If not readable, we just move on
        observationer = find_faneblad(projektnavn, "Observationer", arkdef.OBSERVATIONER, ignore_failure=True)
        arbejdssæt = læs_arbejdssæt(projektnavn)

        n_alle+=1
        if observationer is None or arbejdssæt is None:
            continue
        n_læsbar+=1

        with tempfile.TemporaryDirectory() as tmpdir:

            # ændr projektnavn, så gama vil bruge den nye mappe i stedet
            projektnavn_stem = projektnavn.stem
            projektnavn = Path(tmpdir) / Path(projektnavn_stem)

            # Catch all errors, so we dont ruin a run
            try:
                valideringsresultat = niv_regn_light(projektnavn, observationer, arbejdssæt)
            except ValideringFejl as e:
                # Her fanger vi ValideringFejl, dvs. hvis der er noget galt med input
                # data
                print(e)
                valideringsresultat = Valideringsresultat(
                    status = e,
                    n_fastholdte = 0,
                    n_beregnede = 0,
                    smart_tid = 0,
                    gama_tid = 0,
                    tidsforskel_s = 0,
                    tidsforskel_pct = 0,
                )
            else:
                if valideringsresultat is None:
                    continue

                # Flyt html rapporter for sager som ikke er OK ud af temp-mappen, så vi kan
                # gennemse dem bagefter
                if valideringsresultat.status != "OK" or gem_alle_sager:
                    gama_html = Path(f"{projektnavn}-resultat.html")
                    smart_html = Path(f"{projektnavn}-smart-resultat.html")

                    # Opret endnu en mappe til den specifikke sag som vi vil logge.
                    # Sagsnavnet prependes med indexet, da mange sager hedder det samme.
                    mappe_dest = resultatmappe / Path(f"{i}_{projektnavn_stem}")
                    mappe_dest.mkdir(parents=True)

                    shutil.copy(gama_html, mappe_dest/gama_html.name)
                    shutil.copy(smart_html, mappe_dest/smart_html.name)

            benchmark_results.append((projektnavn_stem, valideringsresultat))

    print(f"kunne læse {n_læsbar} ud af {n_alle}")

    # Save as xlsx
    if not benchmark_results:
        return
    sti = resultatmappe / Path("rmbm_Fdrev.xlsx")
    header = ["sagsnavn"]+benchmark_results[0][1].header()
    rows = [[projektnavn]+res.row()
        for projektnavn, res in benchmark_results
    ]
    gem_til_excel(header, rows, sti)




def valider_fra_fire():
    """
    Brug niv-regneark fra FIRE som grundlag for benchmarking
    """

    sql = text(
        "SELECT objektid, sagseventinfoobjektid, materiale " \
        "FROM SAGSEVENTINFO_MATERIALE "
    )
    cursor = FIREDB.session.execute(sql)

    n_læsbar = 0
    n_alle = 0
    benchmark_results: list[dict] = []
    for row in cursor:
        zip = row[2]
        filename = "projektnavn"

        # open temporary dir
        with tempfile.TemporaryDirectory() as tmpdir:

            pth = Path(tmpdir) / Path(filename + ".zip")

            # TODO: can probably be done in-memory with io-module

            # save zip file, so we can read it with pandas
            with open(pth, "wb") as f:
                f.write(zip)

            with ZipFile(pth) as zf:
                zf.extractall(tmpdir)

            # the zip-file can contain files of these sorts (see cli.niv._luk_sag):
            # f"{projektnavn}.xlsx",
            # f"{projektnavn}-revision.xlsx",
            # f"{projektnavn}.xml",
            # f"{projektnavn}-resultat.xml",
            # f"{projektnavn}-resultat-endelig.html",
            # f"{projektnavn}-observationer.geojson",
            # f"{projektnavn}-punkter.geojson",
            #
            # We are only interested in the first one
            all_files = [_.name for _ in Path(tmpdir).glob("*")]
            projektnavn = [_.stem for _ in Path(tmpdir).glob("*") if _.suffix == ".xlsx" and not _.stem.endswith("-revision")]
            if not projektnavn:
                print(f"No excel files in {all_files}")
                continue

            projektnavn_stem = projektnavn[0]
            projektnavn = Path(tmpdir) / Path(projektnavn_stem)

            # now we are ready to use logic from "fire niv regn"
            observationer = find_faneblad(projektnavn, "Observationer", arkdef.OBSERVATIONER, ignore_failure=True)

            # read tabs from worksheet in prioritized order
            arbejdssæt = læs_arbejdssæt(projektnavn)

            n_alle+=1
            if observationer is None or arbejdssæt is None:
                print(f"Kunne ikke læse {projektnavn}")
                continue
            n_læsbar+=1

            try:
                valideringsresultat = niv_regn_light(projektnavn, observationer, arbejdssæt)
            except Exception as e:

                print(e)
                valideringsresultat = Valideringsresultat(
                    status = e,
                    n_fastholdte = 0,
                    n_beregnede = 0,
                    smart_tid = 0,
                    gama_tid = 0,
                    tidsforskel_s = 0,
                    tidsforskel_pct = 0,
                )

            if valideringsresultat is None:
                continue


            benchmark_results.append(
                dict(sagsnavn=projektnavn_stem, **valideringsresultat.to_dict())
            )

    # Save as csv
    keys = benchmark_results[0].keys()

    sti = Path(r"C:\FIRE-DEV\scripts\regnemotor_benchmarking") / Path("rmbm_fire_results.csv")
    with open(sti, 'w', newline='') as output_file:
        dict_writer = csv.DictWriter(output_file, keys)
        dict_writer.writeheader()
        dict_writer.writerows(benchmark_results)


    print(f"kunne læse {n_læsbar} ud af {n_alle}")


def læs_arbejdssæt(projektnavn):
    """Read tabs from worksheet in prioritized order"""
    faneblade = ["Resultat", "Endelig beregning", "Kontrolberegning", "Punktoversigt"]
    for fb in faneblade:
        arbejdssæt = find_faneblad(projektnavn, fb, arkdef.PUNKTOVERSIGT, ignore_failure=True)
        if arbejdssæt is not None:
            return arbejdssæt

    return None


def niv_regn_light(projektnavn, observationer, punkter) -> Valideringsresultat | None:
    """Imiter udjævning via `niv regn`"""

    # Inden regnemotoren sættes i gang tages der højde for slukkede observationer
    observationer_uden_slukkede = observationer[observationer["Sluk"] != "x"]

    # Start 2 motorer hver for sig, med samme initielle parametre
    gama = GamaRegn.fra_dataframe(
        observationer_uden_slukkede, punkter, projektnavn=projektnavn,
    )
    initialiser_motor(gama)

    smart = SmartRegn.fra_dataframe(
        observationer_uden_slukkede, punkter, projektnavn=projektnavn,
    )
    initialiser_motor(smart)

    # Udjævn, tag tid, og sammenlign
    valideringsresultat = regnemotor_benchmarking(gama, smart)

    if valideringsresultat.status != "OK":
        # kote_diffs = [(sk.H-gk.H) for sk in smart.nye_koter for gk in gama.nye_koter if gk.punkt == sk.punkt]
        print(valideringsresultat.status)
        # for sk in smart.nye_koter:
        #     for gk in gama.nye_koter:
        #         if gk.punkt == sk.punkt:
        #             print(f"{sk.punkt:<10}: smart {sk.H:.3f}    gama {gk.H:.3f}    diff {gk.H-sk.H:.3f}")

    return valideringsresultat


def initialiser_motor(motor: RegneMotor):
    """
    Initialisér en motor

    Der køres nogle validerings-tjeks samt netanalysen.
    Netanalysen sætter nogle interne parametre i motoren som skal bruges
    når udjævningen foretages
    """

    # Kan smide en ValideringFejl, som bør blive fanget længere oppe
    motor.valider_fastholdte()

    # Analyser net
    motor.netanalyse()


def regnemotor_benchmarking(
    gama: GamaRegn,
    smart: SmartRegn,
):
    """
    Udjævn, tag tid, og sammenlign

    Antager at motorerne er initialiseret på samme måde!
    """
    t0 = perf_counter()
    # NOTE: Nu tager vi tid på hele gama, inklusiv i/o forbundet med skrivning/læsning af xml filer
    # gama.skriv_gama_inputfil()
    # # Tag kun tid på selve gama-kaldet (som dog også læser og skriver en fil)
    # gama.kald_gama()
    # gama.nye_koter = gama.læs_gama_outputfil()
    gama.udjævn()
    gama_tid = perf_counter()-t0

    t0 = perf_counter()
    smart.udjævn()
    smart_tid = perf_counter()-t0

    print(f"{smart_tid=:.6f}")
    print(f"{gama_tid=:.6f}")
    print(f"Forskel [s] {gama_tid-smart_tid:.4f}")
    print(f"Forskel [%] {100*gama_tid/smart_tid:.4f}")

    try:
        valider_udjævningsresultater(gama.nye_koter, smart.nye_koter)
    except AssertionError as ae:
        status = ae
    else:
        status = "OK"

    return Valideringsresultat(
        status = status,
        n_fastholdte = len(gama.fastholdte),
        n_beregnede = len(gama.estimerbare_punkter),
        smart_tid = smart_tid,
        gama_tid = gama_tid,
        tidsforskel_s = gama_tid-smart_tid,
        tidsforskel_pct = 100*gama_tid/smart_tid,
    )


def valider_udjævningsresultater(
    gama_koter: list[NivKote],
    smart_koter: list[NivKote],
):
    """Sammenlign to lister af udjævningsresultater"""
    assert len(smart_koter) == len(gama_koter), "Resultatsæt har ikke samme antal punkter"

    punkter = {nk.punkt for nk in smart_koter}
    gama_punkter = {gk.punkt for gk in gama_koter}

    assert gama_punkter == punkter, "Resultatsæt har ikke de samme punkter"

    # Først tjek ALLE koter
    raise_kotediff_err = False
    kotediffs =[]
    for ny_kote in smart_koter:
        pkt = ny_kote.punkt
        for gama_kote in gama_koter:
            if pkt == gama_kote.punkt:
                break

        assert ny_kote.dato == gama_kote.dato, "Datoer forskellige"
        if not np.isclose(ny_kote.H , gama_kote.H):
            raise_kotediff_err = True
            kotediffs.append(f"{(ny_kote.H-gama_kote.H)*1000:.6f} mm")

    if raise_kotediff_err:
        raise AssertionError("smart kotediffs:\n"+"\n".join(kotediffs))

    # derefter tjekkes spredninger. Hvis en hvilken som helst kote er forkert opdages dette før spredningerne
    for ny_kote in smart_koter:
        pkt = ny_kote.punkt
        for gama_kote in gama_koter:
            if pkt == gama_kote.punkt:
                break
        assert np.isclose(ny_kote.spredning , gama_kote.spredning, atol=1e-4), f"Smart spredning={ny_kote.spredning}, gama spredning={gama_kote.spredning}"


    return


if __name__ == "__main__":
    # valider_fra_fire()
    valider_fra_Fdrev(gem_alle_sager=False)
    # mat = np.array([[1,1],[1,1]])

    # breakpoint()
    ...
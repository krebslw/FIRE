"""Modul til håndtering af excetions og warnings i FIRE's cli-lag"""
from contextlib import contextmanager

from fire.cli import firedb
from fire.cli import print as click_print
import click


class AfbrydFejl(SystemExit):
    """
    Standardklasse til fejlbeskeder der skal forårsage en programafbrydelse

    Fejlbeskeden formatteres ens på tværs af cli-laget med hvid-på-rød skrift, præfixeret
    med "FEJL".

    En `bitekst` kan specificeres til at give brugeren yderligere info. Biteksten vises
    med default formattering.

    `med_rollback=True` sørger for at rulle den fælles `firedb.session` tilbage.
    """

    def __init__(self, tekst: str = "", bitekst: str = "", med_rollback: bool = True):

        if med_rollback:
            firedb.session.rollback()

        # Hvis fejlbesked er tom, skrives bare "FEJL!" i stedet for "FEJL: "
        # Men det er nok dårlig praksis at lade fejlbeskeden være tom. Idet mindste
        # bør mulig_årsag i så fald være udfyldt.
        præfix = "FEJL: " if tekst else "FEJL!"

        self.besked = click.style(
            f"{præfix}{tekst}",
            fg="white",
            bg="red",
            bold=True,
        )
        self.besked += click.style(
            f"\n{bitekst}"
        )

        # Besked gives videre til SystemExit, som en ANSI-formatteret string.
        # Beskeden printes kun rigtigt, hvis den er det eneste argument til
        # SystemExit. Dvs. at
        # super().__init__(self.besked, "eksta_argument")
        # ville ødelægge formatteringen!
        super().__init__(self.besked)


class IntetAtGøre(SystemExit):
    """
    Hejses når kommandolinjeværktøjer indser at der er intet at foretage sig.
    """

    def __init__(self, tekst: str, *args, **kwargs):
        self.besked = click.style(f"{tekst}", fg="yellow", bold=True)
        super().__init__(self.besked)


@contextmanager
def YndefuldeFejl(
    exception: Exception | tuple[Exception],
    fejltekst: str = "",
    med_årsag: bool = False,
    med_rollback: bool = True,
):
    """Try-except contextmananger til pæne fejlmeddelelser

    Til det simple (men udbredte) tilfælde, hvor der ikke tages videre stilling til
    fejlen, men blot skal hejses en "alternativ" fejlmeddelse, og evt. rulles tilbage.

    Credit: https://stackoverflow.com/a/74218501
    """
    try:
        yield
    except exception as ex:
        # Hvis fejltekst er tom, skrives årsagen altid
        med_årsag = med_årsag if fejltekst else True

        # Mulig årsag kan sættes til den Exception som blev fanget
        mulig_årsag = f"Mulig årsag: {type(ex).__name__}: {ex}" if med_årsag else ""

        # Mulig årsag sættes som sekundært argument, som passes videre til SystemExit,
        # og som derfor printes med default formattering.
        raise AfbrydFejl(fejltekst, mulig_årsag, med_rollback=med_rollback)

def bemærk(tekst: str):
    click_print(
        f"BEMÆRK: {tekst}",
        fg="yellow",
        bold=True,
    )


def advarsel(tekst: str, præfix="ADVARSEL: "):
    click_print(
        f"{præfix}{tekst}",
        fg="yellow",
        bold=True,
    )

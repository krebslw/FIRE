"""Modul til håndtering af excetions og warnings i FIRE's cli-lag"""

from contextlib import contextmanager

from fire.cli import firedb
from fire.cli import print as click_print


class Afbryd(SystemExit):
    """
    Standardklasse til fejlbeskeder der skal forårsage en programafbrydelse

    Fejlbeskeden formatteres ens på tværs af cli-laget med hvid-på-rød skrift, præfixeret
    med "FEJL".

    Yderligere args/kwargs gives videre til SystemExit. Dvs. at disse bliver printet med
    default formattering, hvilket kan være nyttigt hvis man gerne vil give yderligere
    information til brugeren omkring fejlen.
    """

    def __init__(self, tekst: str = "", *args, med_rollback: bool = False, **kwargs):
        # Hvis fejlbesked er tom, skrives bare "FEJL!" i stedet for "FEJL: "
        # Men det er nok dårlig praksis at lade fejlbeskeden være tom. Idet mindste
        # bør mulig_årsag i så fald være udfyldt.
        præfix = "FEJL: " if tekst else "FEJL!"

        click_print(
            f"{præfix}{tekst}",
            fg="white",
            bg="red",
            bold=True,
        )

        if med_rollback:
            firedb.session.rollback()

        super().__init__(*args, **kwargs)


class NothingToDo(SystemExit):
    """
    Hejses når kommandolinjeværktøjer indser at der er intet at foretage sig.
    """

    def __init__(self, tekst: str, *args, **kwargs):
        click_print(f"{tekst}", fg="yellow", bold=True)

        super().__init__(*args, **kwargs)


@contextmanager
def YndefuldeFejl(
    exception: Exception | tuple[Exception],
    fejltekst: str = "",
    *args,
    med_årsag: bool = False,
    med_rollback: bool = False,
    **kwargs,
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
        raise Afbryd(fejltekst, mulig_årsag, *args, med_rollback=med_rollback, **kwargs)


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

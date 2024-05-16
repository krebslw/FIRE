import click

import fire.cli
from fire.api.model import (
    Tidsserie,
    GNSSTidsserie,
    HøjdeTidsserie,
    Punkt,
)
from rich.table import Table
from rich.console import Console
from rich import box
from sqlalchemy import func
from sqlalchemy.exc import NoResultFound

@click.group()
def ts():
    """
    Håndtering af koordinattidsserier.
    """
    pass

def _print_tidsserieoversigt(tidsserieklasse: type, punkt: Punkt = None):
    """
    Oversigt over tidsserier af en bestemt types

    raises:     SystemExit
    """
    def identgnss(punkt: Punkt):
            return punkt.gnss_navn

    def identident(punkt: Punkt):
            return punkt.ident

    if tidsserieklasse==GNSSTidsserie:
        foretrukken_ident = identgnss
    else:
        foretrukken_ident = identident

    if punkt:
        tidsserier = [ts for ts in punkt.tidsserier if isinstance(ts, tidsserieklasse)]
    else:
        tidsserier = (
            fire.cli.firedb.session.query(tidsserieklasse)
            .filter(tidsserieklasse._registreringtil == None)
            .all()
        )  # NOQA

    if not tidsserier:
        raise SystemExit("Fandt ingen tidsserier")

    tabel = Table("Ident", "Tidsserie ID", "Referenceramme", box=box.SIMPLE)

    # Sorter tidsserier efter punkt
    tidsserier.sort(key = lambda ts: (foretrukken_ident(ts.punkt)))

    tidsserier = tidsserier[:100]
    for ts in tidsserier:
        tabel.add_row(foretrukken_ident(ts.punkt), ts.navn, ts.referenceramme)


    console = Console()
    console.print(tabel)


def _find_tidsserie(tidsserieklasse: type, tidsserienavn: str) -> Tidsserie:
    """
    Find en navngiven tidsserie

    raises:     NoResultFound
    """
    tidsserie = (
        fire.cli.firedb.session.query(tidsserieklasse)
        .filter(
            tidsserieklasse._registreringtil == None,
            func.lower(tidsserieklasse.navn) == func.lower(tidsserienavn),
        )
        .one()
    )  # NOQA

    return tidsserie


from .gnss import gnss
from .hts import hts

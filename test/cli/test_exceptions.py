import pytest
from sqlalchemy import inspect

from fire.api import FireDb
from fire.api.model import Punkt

from fire.cli.exceptions import (
    AfbrydFejl,
    IntetAtGøre,
    YndefuldeFejl,
)

def test_IntetAtGøre_printer_rigtigt():
    besked = "Intet at gøre. Afbryder..."
    with pytest.raises(SystemExit, match=besked):
        raise IntetAtGøre(besked)

def test_AfbrydFejl_printer_rigtigt():
    besked1 = "primær fejlbesked"
    besked2 = "sekundær hjælpetekst"
    with pytest.raises(SystemExit, match=besked1):
        raise AfbrydFejl(besked1, besked2)

    with pytest.raises(SystemExit, match=besked2):
        raise AfbrydFejl(besked1, besked2)


def test_AfbrydFejl_ruller_tilbage(firedb: FireDb, punkt: Punkt):
    # Flush punkt til ci-databasen
    firedb.session.flush()
    insp = inspect(punkt)
    assert insp.persistent is True

    # Rejs fejlen uden at afbryde test-suiten
    with pytest.raises(SystemExit):
        raise AfbrydFejl

    # Tjek sessionen blev rullet tilbage, idet
    # punktet nu bør være i "transient" tilstand
    insp = inspect(punkt)
    assert insp.persistent is False
    assert insp.transient is True

def test_YndefuldeFejl():

    # Tjek at der hejses en AfbrydFejl, når der opstår en forventet ValueError
    with pytest.raises(AfbrydFejl, match="Forventer en ValueError"):
        with YndefuldeFejl(ValueError, "Forventer en ValueError"):
            raise ValueError("Forkert værdi")

    # Sættes med_årsag=True, skal årsagen "Forkert værdi" være med i fejlbeskeden
    with pytest.raises(AfbrydFejl, match="Forkert værdi"):
        with YndefuldeFejl(ValueError, "Forventer en ValueError", med_årsag=True):
            raise ValueError("Forkert værdi")

    # Tjek at en uventet TypeError stadig bobler op til overfladen
    with pytest.raises(TypeError):
        with YndefuldeFejl(ValueError, "Forventer en ValueError"):
            raise TypeError("Forkert type")

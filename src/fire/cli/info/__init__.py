print("importerede cli.info.__init__")
import click


@click.group()
def info():
    """
    Information om objekter i FIRE
    """
    pass


# Udstil kommandoer
from fire.cli.info._info import (
    punkt,
    punktsamling,
    srid,
    obstype,
    infotype,
    sag,
    sagsevent,
)
from fire.cli.info._infopunkt import punkt
from fire.cli.info._koordinater import (
    koordinater
)

# ... og visse hjælpefunktioner som bruges andre steder
from fire.cli.info._info import (
    punktinforapport,
)

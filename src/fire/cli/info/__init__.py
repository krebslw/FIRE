print("importerede cli.info.__init__")
import shlex

import click
from fire.cli.exceptions import AfbrydFejl


@click.group()
@click.pass_context
@click.option(
    "-I",
    "--interaktiv",
    help=f"Start en interaktiv session op",
    is_flag = True,
    required=False,
    type = bool,
)
def info(ctx: click.Context, interaktiv: bool):
    """
    Information om objekter i FIRE
    """

    if not interaktiv:
        return

    kommando: str = ctx.invoked_subcommand

    # Hvis kommando ikke er en gyldig sub-kommando af fire info,
    # vil det blive fanget længere oppe, så burde ikke være nogen
    # fare for KeyError her.
    subkommando: click.Command = ctx.command.commands[kommando]

    # TODO: gør så brugeren fx kun skal specificere options én gang.
    # Så man heller gang ikke skal skrive fx:
    # -DHOalle -Kts,alle --db prod <FIKSPUNKTSNR>
    print(f"Starter interaktiv session med 'fire info {kommando}'")
    print(f"Afbryd med CTRL+C")
    while True:

        brugerinput = click.prompt(f"fire info {kommando} ", prompt_suffix = "")
        try:
            # Lav en ny kontekst baseret på oprindelig kontekst og brugerinput
            # Brugerinput splittes og parsing overlades til click's make_context
            ny_ctx = subkommando.make_context(
                info_name = f"Interaktiv version af {kommando}",
                args = shlex.split(brugerinput, " "),
            )

            ny_ctx.command.callback(**ny_ctx.params)
        except Exception as exc:
            print(exc)
        except AfbrydFejl as exc:
            # SystemExits, smidt igennem AfbrydFejl bliver også fanget og printet (inkl
            # click formattering)
            print(exc)


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
from fire.cli.info._koordinater import (
    koordinater
)

# ... og visse hjælpefunktioner som bruges andre steder
from fire.cli.info._info import (
    punktinforapport,
)

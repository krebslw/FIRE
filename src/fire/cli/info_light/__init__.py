print("importerede cli.info_light.__init__")
import click


@click.group()
@click.option("--profile", is_flag=True)
def infolight(profile: bool):
    """
    Information om objekter i FIRE
    """
    print("kørte cli.infolight.infolight click gruppe")
    if profile:
        import cProfile
        import pstats
        import io
        import atexit

        print("Profiling...")
        pr = cProfile.Profile()
        pr.enable()

        def exit():
            pr.disable()
            print("Profiling completed")
            s = io.StringIO()
            pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats()
            print(s.getvalue())

        atexit.register(exit)


# Udstil kommandoer
from fire.cli.info_light._infopunkt import (
    punkt,
)

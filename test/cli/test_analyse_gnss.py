from contextlib import contextmanager
import gc
import os
from pathlib import Path

from click.testing import CliRunner
import pytest

from fire.cli.ts import ts
from fire.api.model.tidsserier import PolynomialRegression

@contextmanager
def isoleret_filsystem(mappe):
    oprindelig_mappe = os.getcwd()
    try:
        os.chdir(mappe)
        yield
    finally:
        os.chdir(oprindelig_mappe)

# CLI
@pytest.mark.parametrize(
    "options",
    [
        (["Findes ikke"]),
        (["--referenceramme", "IGb14", "RDIO_5D_IGb08"]),
        (["--min-antal-punkter", "20", "RDIO_5D_IGb08"]),
        (["--parameter", "test", "RDIO_5D_IGb08"]),
        (["--no-plot", "RDIO_5D_IGb08"]),
    ],
)
def test_cli_analyse_gnss_fejler(tmp_path, mocker, options):
    """Test at fire ts analyse-gnss fejler ved forkert input"""
    runner = CliRunner()

    with isoleret_filsystem(tmp_path):
        mocker.patch("matplotlib.pyplot.show", return_value=None)
        result = runner.invoke(
            ts,
            [
                "analyse-gnss",
            ]
            + options,
        )
        assert result.exit_code != 0

    # analyse-gnss opretter PolynomieRegression attributter på tidsserierne, så disse
    # slettes igen, da det senere testes at de ikke eksisterer
    for obj in gc.get_objects():
        if isinstance(obj, PolynomialRegression):
            del obj


@pytest.mark.parametrize(
    "options, tjek_sti",
    [
        (["--plot", "--referenceramme", "IGb08", "RDIO_5D_IGb08"], "."),
        (
            ["--plot", "--fil", "test_statistik.xlsx", "RDIO_5D_IGb08"],
            "test_statistik.xlsx",
        ),
        (["--plot", "--parameter", "e", "RDIO_5D_IGb08"], "."),
        (["--plot", "--grad", "2", "RDIO_5D_IGb08"], "."),
    ],
)
def test_cli_analyse_gnss_kører(firedb, tmp_path, mocker, options, tjek_sti):
    """Test at fire ts analyse-gnss kan køre ved korrekt input"""
    runner = CliRunner()

    with isoleret_filsystem(tmp_path):
        mocker.patch("matplotlib.pyplot.show", return_value=None)
        result = runner.invoke(
            ts,
            [
                "analyse-gnss",
            ]
            + options,
        )

        assert result.exit_code == 0
        assert Path(tjek_sti).exists()

    # analyse-gnss opretter PolynomieRegression attributter på tidsserierne, så disse
    # slettes igen, da det senere testes at de ikke eksisterer
    for obj in gc.get_objects():
        if isinstance(obj, PolynomialRegression):
            del obj

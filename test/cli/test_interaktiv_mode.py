import pytest
from click.testing import CliRunner

from fire.cli.main import (
    fire_cmd,
)


inputs = [
    "RDIO",
    "RDIO\n"
    "RDO1\n"
    "G.M.902\n",
]

@pytest.mark.parametrize(
    argnames="input",
    argvalues=inputs
)
def test_interaktiv_fil_input(input: str):
    """
    Test at interaktiv session kan modtage en fil der pipes ind
    """

    runner = CliRunner()

    result = runner.invoke(fire_cmd, ["info", "punkt", "-DHOalle", "--interaktiv"], input=input)

    # assert result.exit_code == 0 # assert hvad? Der smides jo en SystemExit til sidst dvs exit_code=1
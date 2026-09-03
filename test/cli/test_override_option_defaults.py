from click.testing import CliRunner

from fire.cli.main import (
    fire_cmd,
)


def test_override_option_defaults():
    """
    Test at option defaults kan overrides med miljøvariable
    """

    envvars = {
        "FIRE_INFO_PUNKT_OBS": "alle",
        "FIRE_INFO_PUNKT_DETALJERET": "True",
        "FIRE_INFO_PUNKT_HISTORIK": "True",
    }

    # Kør samme kommando på to forskellige måder.
    # En med options sat explicit, og én via miljøvariable der overskriver defaults
    runner = CliRunner()
    result = runner.invoke(fire_cmd, ["info", "punkt", "-DHOalle", "RDIO"])
    print(result.output)
    assert result.exit_code == 0

    runner = CliRunner(env=envvars)
    result2 = runner.invoke(fire_cmd, ["info", "punkt", "RDIO"], env=envvars)
    print(result2.output)
    assert result2.exit_code == 0

    assert result.output == result2.output, "Output fra `fire info punkt` er ikke ens"

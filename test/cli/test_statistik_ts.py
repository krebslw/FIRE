import numpy as np
import pytest

from fire.api.model.tidsserier import PolynomieRegression1D
from fire.cli.ts.statistik_ts import (
    Statistik,
    Statistik_GNSS,
    Statistik_GNSS_Samlet,
    Statistik_HTS,
    beregn_statistik_til_gnss_rapport,
    beregn_statistik_til_hts_rapport,
)


def test_beregn_statistik_til_gnss_rapport(gnsstidsserie):

    x = np.linspace(-1, 1, 1000)
    lr = PolynomieRegression1D(x, x)
    lr.solve()
    statistik = beregn_statistik_til_gnss_rapport(
        gnsstidsserie, alpha=0.05, reference_hældning=0
    )

    assert isinstance(statistik, Statistik_GNSS)

    statistik = beregn_statistik_til_gnss_rapport(
        gnsstidsserie, alpha=0.05, reference_hældning=0, er_samlet=True
    )

    assert isinstance(statistik, Statistik_GNSS_Samlet)


def test_beregn_statistik_til_hts_rapport(højdetidsserie):

    x = np.linspace(-1, 1, 1000)
    lr = PolynomieRegression1D(x, x)
    lr.solve()
    statistik = beregn_statistik_til_hts_rapport(højdetidsserie)

    assert isinstance(statistik, Statistik_HTS)

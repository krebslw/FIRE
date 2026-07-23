from dataclasses import dataclass, fields, asdict
from datetime import datetime

import numpy as np

from fire.api.model import (
    Tidsserie,
    GNSSTidsserie,
    HøjdeTidsserie,
    Punkt,
)
from fire.api.statistik import (
    compute_confidence_interval_t_distribution,
    compute_confidence_interval_normal_distribution,
    Ttest,
    Ztest,
)

@dataclass
class Statistik:
    TidsserieID: str
    Ident: str
    N: int
    dof: int
    ddof: int
    grad: int
    R2: float
    var_0: float
    std_0: float
    hældning: float
    var_hældning: float
    std_hældning: float
    ki_hældning_nedre: float
    ki_hældning_øvre: float
    mex: float
    mey: float

    def header(self):
        return [str(field.name) for field in fields(self)]

    def row(self):
        return [getattr(self, field.name) for field in fields(self)]


@dataclass
class StatistikGnss(Statistik):
    N_binned: int
    reference_hældning: float
    T_test_H0accepteret: bool
    T_test_score: float
    T_test_alpha: float
    T_test_kritiskværdi: float


@dataclass
class StatistikGnssSamlet(StatistikGnss):
    var_samlet: float
    std_samlet: float
    var_hældning_samlet: float
    std_hældning_samlet: float
    ki_hældning_nedre_samlet: float
    ki_hældning_øvre_samlet: float
    Z_test_H0accepteret: bool
    Z_test_score: float
    Z_test_alpha: float
    Z_test_kritiskværdi: float


@dataclass
class StatistikHts(Statistik):
    Start: datetime
    Slut: datetime
    er_bevægelse_signifikant: bool
    alpha_bevægelse_signifikant: float


def beregn_statistik_til_gnss_rapport(
    tidsserie: GNSSTidsserie,
    alpha: float,
    reference_hældning: float,
    er_samlet: bool = False,
) -> StatistikGnss:
    """
    Metode til samlet beregning af statistik for en GNSS tidsserie

    Resultaterne gemmes i dataklassen `StatistikGnss`.
    """
    linreg = tidsserie.linreg

    # Er ikke samlet
    var_theta = linreg.var_theta[1]
    std_theta = np.sqrt(var_theta)

    # konfidensinterval
    delta_ki = compute_confidence_interval_t_distribution(std_theta, linreg.dof, alpha)
    konfidensinterval =  linreg.theta + np.outer([-1, 1], delta_ki)

    # hypotesetest
    H0 = reference_hældning - linreg.theta[1]
    T_test = Ttest(std_theta, linreg.dof, H0, alpha)


    statistik = StatistikGnss(
        TidsserieID=tidsserie.navn,
        Ident=tidsserie.punkt.gnss_navn,
        N=len(tidsserie),
        N_binned=linreg.N,
        dof=linreg.dof,
        ddof=linreg.ddof,
        grad=linreg.degree,
        R2=linreg.R2,
        var_0=linreg.MSE,
        std_0=np.sqrt(linreg.MSE),
        reference_hældning=reference_hældning,
        hældning=linreg.theta[1],
        var_hældning=var_theta,
        std_hældning=std_theta,
        ki_hældning_nedre=konfidensinterval[0, 1],
        ki_hældning_øvre=konfidensinterval[1, 1],
        mex=linreg.mex,
        mey=linreg.mey,
        T_test_H0accepteret=T_test.H0accepted,
        T_test_score=T_test.score,
        T_test_alpha=T_test.alpha,
        T_test_kritiskværdi=T_test.critical_value,
    )

    # er_samlet
    if not er_samlet:
        return statistik

    # set reference variance to the estimated variance (which is based on all the
    # timeseries) and re-compute model parameter variances
    linreg.var0_hat = linreg.var_samlet
    var_theta_samlet = linreg.var_theta[1]
    std_theta_samlet = np.sqrt(var_theta_samlet)

    # konfidensinterval
    delta_ki = compute_confidence_interval_normal_distribution(std_theta_samlet, alpha)
    konfidensinterval_samlet =  linreg.theta + np.outer([-1, 1], delta_ki)

    # hypotesetest
    H0 = reference_hældning - linreg.theta[1]
    Z_test = Ztest(std_theta_samlet, H0, alpha)

    statistik_samlet = StatistikGnssSamlet(
        **asdict(statistik),
        var_samlet=linreg.var_samlet,
        std_samlet=np.sqrt(linreg.var_samlet),
        var_hældning_samlet=var_theta_samlet,
        std_hældning_samlet=std_theta_samlet,
        ki_hældning_nedre_samlet=konfidensinterval_samlet[0, 1],
        ki_hældning_øvre_samlet=konfidensinterval_samlet[1, 1],
        Z_test_H0accepteret=Z_test.H0accepted,
        Z_test_score=Z_test.score,
        Z_test_alpha=Z_test.alpha,
        Z_test_kritiskværdi=Z_test.critical_value,
    )
    return statistik_samlet


def beregn_statistik_til_hts_rapport(tidsserie: HøjdeTidsserie) -> StatistikHts:
    """
    Metode til samlet beregning af statistik for en HøjdeTidsserie

    Kalder den lineære regressions beregningsmetoder og returnerer de nødvendige
    statistik-parametre til brug i rapportering.

    NB! Konfidensintervaller, Trend-test og stabilitetstest foretages med default
    værdier for signifikansniveau, men der skal muligvis gives mulighed for at kunne
    indstille på dem.

    """
    linreg = tidsserie.linreg

    trend_test = tidsserie.signifikant_trend_test()

    # Er ikke samlet
    var_theta = linreg.var_theta[1]
    std_theta = np.sqrt(var_theta)

    # konfidensinterval
    delta_ki = compute_confidence_interval_t_distribution(std_theta, linreg.dof)
    konfidensinterval =  linreg.theta + np.outer([-1, 1], delta_ki)

    statistik = StatistikHts(
        TidsserieID=tidsserie.navn,
        Ident=tidsserie.punkt.ident,
        N=len(tidsserie),
        dof=linreg.dof,
        ddof=linreg.ddof,
        grad=linreg.degree,
        R2=linreg.R2,
        var_0=linreg.MSE,
        std_0=np.sqrt(linreg.MSE),
        hældning=linreg.theta[1],
        var_hældning=var_theta,
        std_hældning=std_theta,
        ki_hældning_nedre=konfidensinterval[0, 1],
        ki_hældning_øvre=konfidensinterval[1, 1],
        mex=linreg.mex,
        mey=linreg.mey,
        Start=tidsserie.t[0],
        Slut=tidsserie.t[-1],
        er_bevægelse_signifikant=not trend_test.H0accepted,
        alpha_bevægelse_signifikant=trend_test.alpha,
    )

    return statistik

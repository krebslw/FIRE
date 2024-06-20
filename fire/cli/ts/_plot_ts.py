from typing import Callable

import matplotlib.pyplot as plt
from matplotlib.ticker import FormatStrFormatter
import numpy as np

from fire.api.model import (
    Tidsserie,
    GNSSTidsserie,
    HøjdeTidsserie,
)

from fire.api.model.tidsserier import PolynomieRegression1D


TS_PLOTTING_LABELS = {
    "t": "Dato",
    "x": "x",
    "y": "y",
    "z": "z",
    "kote": "Kote",
    "X": "X",
    "Y": "Y",
    "Z": "Z",
    "n": "Nord",
    "e": "Øst",
    "u": "Op",
    "decimalår": "År",
}

ENHEDER_SKALAFAKTOR = {
    "m":1,
    "mm":1e3,
    "μm":1e6,
    "micron":1e6,
}


def plot_ts(
    ts: Tidsserie, plot_funktion: Callable, parametre: list = ["n", "e", "u"], y_enhed: str = "m"
):
    """
    Plotter en Tidsserie.

    Denne funktion håndterer figuropsætningen, og kalder ``plot_funktion``, som
    forventes at foretage selve plottingen af data.
    """
    n_parm = min(len(parametre), 3)

    skalafaktor = ENHEDER_SKALAFAKTOR[y_enhed]

    ax = plt.figure()
    plt.suptitle(ts.navn)

    for i, parm in enumerate(parametre, start=1):
        if i > 3:
            break

        y = [skalafaktor * yy for yy in getattr(ts, parm)]

        try:
            label = TS_PLOTTING_LABELS[parm]
        except KeyError:
            label = parm

        ax = plt.subplot(int(f"{n_parm}{1}{i}"))
        plot_funktion(ts.decimalår, y, y_enhed=y_enhed)
        plt.ylabel(f"{label} [{y_enhed}]")
        plt.grid()

    # Vis kun xlabel for nederste subplot
    plt.xlabel("År")

    # Vis kun legend hvis der er noget at vise (ellers vises en tom boks),
    # samt hvis der kun er ét plot i figuren (ellers bliver det for gnidret)
    handles, labels = ax.get_legend_handles_labels()
    if labels and n_parm == 1:
        plt.legend(handles, labels)

    plt.show()


def plot_gnss_analyse(
    label: str,
    tidsserie: GNSSTidsserie,
    alpha: float = 0.05,
    er_samlet: bool = False,
):
    """
    Plot resultaterne af en GNSS-analyse.

    Hvis regressionen er en del af et TidsserieEnsemble kan "samlet" statistik
    plottes hvis flaget ``er_samlet`` sættes.

    ``alpha`` bestemmer signifkansniveauet for konfidensbånd til fittet samt for hypo-
    tesetests.

    Reference-hældningen vises som en linje der skærer regressionslinjen i punktet (mex,
    mey), som er punktet i midten af tidsserien (middelepoken).
    """
    linreg = tidsserie.linreg

    # Prædiktioner og intervaller
    x_præd = np.linspace(linreg.x[0], linreg.x[-1], 1000)
    y_præd = linreg.beregn_prædiktioner(x_præd)

    konfidensbånd = linreg.beregn_konfidensbånd(
        x_præd,
        y_præd,
        alpha=alpha,
        er_samlet=False,
    )

    konfidensbånd_samlet = linreg.beregn_konfidensbånd(
        x_præd,
        y_præd,
        alpha=alpha,
        er_samlet=True,
    )

    # Uplift
    uplift_rate = linreg.hældning_reference
    uplift_fit = uplift_rate * (x_præd - linreg.mex) + linreg.mey

    # Hypotesetest
    H0 = uplift_rate - linreg.beta[1]

    T_test = linreg.beregn_hypotesetest(H0=H0, alpha=alpha)
    Z_test = linreg.beregn_hypotesetest(H0=H0, alpha=alpha, er_samlet=True)

    # Plotting
    plt.rcParams["figure.autolayout"] = True
    plt.figure(figsize=(12, 9))
    ax = plt.subplot(111)
    ax.scatter(linreg.x, linreg.y, marker="*", color="black", label="GNSS Observation")

    ax.plot(
        x_præd,
        y_præd,
        "r",
        label=f"Hældning af fit: {linreg.beta[1]:.3f} [mm/år]",
    )
    ax.plot(
        x_præd,
        uplift_fit,
        "k",
        label=f"Uplift-rate: {uplift_rate:.3f} [mm/år]",
    )

    # Konfidensbånd
    ax.plot(x_præd, konfidensbånd[0, :], color="green")
    ax.plot(x_præd, konfidensbånd[1, :], color="green", label="95% Konfidensbånd")

    # Konfidensbånd (samlet)
    if er_samlet:
        ax.plot(
            x_præd,
            konfidensbånd_samlet[0, :],
            color="blue",
        )
        ax.plot(
            x_præd,
            konfidensbånd_samlet[1, :],
            color="blue",
            label="95% Konfidensbånd (samlet)",
        )

    ax.scatter(
        linreg.mex,
        linreg.mey,
        marker="o",
        facecolors="none",
        edgecolors="blue",
        label="Middelepoke",
    )

    ax.set_title(
        f"Tidsserie: {tidsserie.navn}    R$^2$ = {linreg.R2:.2f}   N = {len(tidsserie.decimalår)}   N$\\mathregular{{_{{binned}}}}$ = {linreg.N}"
    )
    ax.set_xlabel("Dato")
    ax.set_ylabel(label)

    ax.yaxis.set_major_formatter(FormatStrFormatter("%.3f"))

    ax.grid()
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.2, -0.15),
        fancybox=True,
        shadow=True,
        ncol=1,
    )

    # T-test resultater til visning
    t_tekst = f"|t| = {T_test.score:.2f}\nt$\\mathregular{{_{{crit}}}}$ = {T_test.kritiskværdi:.2f}\n"

    if T_test.H0accepteret:
        t_tekst += f"H$_{{0}}$ accepteret ved {T_test.alpha*100}% signifikansniveau"
    else:
        t_tekst += f"H$_{{0}}$ forkastet ved {T_test.alpha*100}% signifikansniveau"

    # Z-test resultater til visning
    z_tekst = f"|z| = {Z_test.score:.2f}\nz$\\mathregular{{_{{crit}}}}$ = {Z_test.kritiskværdi:.2f}\n"

    if Z_test.H0accepteret:
        z_tekst += f"H$_{{0}}$ accepteret ved {Z_test.alpha*100}% signifikansniveau (samlet)"
    else:
        z_tekst += f"H$_{{0}}$ forkastet ved {Z_test.alpha*100}% signifikansniveau (samlet)"

    # Standardafvigelse data til visning
    std_tekst = f"Std. af data = {np.sqrt(linreg.var0):.2f} mm\n\
Std. af data fra alle tidsserier (samlet) = {np.sqrt(linreg.var_samlet):.2f} mm"

    plt.figtext(0.55, 0.18, t_tekst)
    if er_samlet:
        plt.figtext(0.55, 0.11, z_tekst)
    plt.figtext(0.55, 0.05, std_tekst)

    plt.show()

def plot_hts_analyse(
    label: str,
    tidsserie: HøjdeTidsserie,
    alpha: float = 0.05,
    er_samlet: bool = False,
):
    """
    Plot resultaterne af en GNSS-analyse.

    Hvis regressionen er en del af et TidsserieEnsemble kan "samlet" statistik
    plottes hvis flaget ``er_samlet`` sættes.

    ``alpha`` bestemmer signifkansniveauet for konfidensbånd til fittet samt for hypo-
    tesetests.

    Reference-hældningen vises som en linje der skærer regressionslinjen i punktet (mex,
    mey), som er punktet i midten af tidsserien (middelepoken).
    """
    linreg = tidsserie.linreg

    # Prædiktioner og intervaller
    x_præd = np.linspace(linreg.x[0], linreg.x[-1], 1000)
    y_præd = linreg.beregn_prædiktioner(x_præd)

    konfidensbånd = linreg.beregn_konfidensbånd(
        x_præd,
        y_præd,
        alpha=alpha,
        er_samlet=False,
    )

    # Hypotesetest
    H0 = 0 - linreg.beta[1]

    T_test = linreg.beregn_hypotesetest(H0=H0, alpha=alpha)
    Z_test = linreg.beregn_hypotesetest(H0=H0, alpha=alpha, er_samlet=True)

    # Plotting
    plt.rcParams["figure.autolayout"] = True
    plt.figure(figsize=(12, 9))
    ax = plt.subplot(111)
    ax.scatter(linreg.x, linreg.y, marker="*", color="black", label="GNSS Observation")

    ax.plot(
        x_præd,
        y_præd,
        "r",
        label=f"Hældning af fit: {linreg.beta[1]:.3f} [mm/år]",
    )

    # Konfidensbånd
    ax.plot(x_præd, konfidensbånd[0, :], color="green")
    ax.plot(x_præd, konfidensbånd[1, :], color="green", label="95% Konfidensbånd")

    ax.set_title(
        f"Tidsserie: {tidsserie.navn}    R$^2$ = {linreg.R2:.2f}   N = {len(tidsserie.decimalår)}"
    )
    ax.set_xlabel("Dato")
    ax.set_ylabel(label)

    ax.yaxis.set_major_formatter(FormatStrFormatter("%.3f"))

    ax.grid()
    ax.legend(
        loc="upper center",
        bbox_to_anchor=(0.2, -0.15),
        fancybox=True,
        shadow=True,
        ncol=1,
    )

    # T-test resultater til visning
    t_tekst = f"|t| = {T_test.score:.2f}\nt$\\mathregular{{_{{crit}}}}$ = {T_test.kritiskværdi:.2f}\n"

    if T_test.H0accepteret:
        t_tekst += f"H$_{{0}}$ accepteret ved {T_test.alpha*100}% signifikansniveau"
    else:
        t_tekst += f"H$_{{0}}$ forkastet ved {T_test.alpha*100}% signifikansniveau"

    # Standardafvigelse data til visning
    std_tekst = f"Std. af data = {np.sqrt(linreg.var0):.2f} mm"

    plt.figtext(0.55, 0.07, t_tekst)
    plt.figtext(0.55, 0.02, std_tekst)

    plt.show()



def plot_data(x: list, y: list, **kwargs):
    plt.plot(
        x,
        y,
        ".",
        markersize=4,
        color="black",
    )


def plot_fit(x: list, y: list, y_enhed: str = "mm"):
    """
    Plot x og y samt bedste rette linje.

    Enheden på x forventes at være decimalår.
    """

    lr = PolynomieRegression1D(x, y)
    lr.solve()

    x_præd = np.linspace(lr.x[0], lr.x[-1], 1000)
    y_præd = lr.beregn_prædiktioner(x_præd)

    plt.plot(
        x_præd,
        y_præd,
        "-",
        color="red",
        label=f"Hældning af fit: {lr.beta[1]:.3f} [{y_enhed}/år]",
    )
    plot_data(lr.x, lr.y)
    plt.ylim(lr.y.min(), lr.y.max())


def plot_konfidensbånd(x: list, y: list, y_enhed: str = "mm"):
    """
    Plot x og y samt bedste rette linje med konfidensbånd.

    Enheden på x forventes at være decimalår.
    """
    # Binning
    x_binned, y_binned = GNSSTidsserie.binning(x, y)

    # Foretag lineær regresion
    lr = PolynomieRegression1D(x_binned, y_binned)
    lr.solve()

    # Prædiktioner
    x_præd = np.linspace(lr.x[0], lr.x[-1], 1000)
    y_præd = lr.beregn_prædiktioner(x_præd)

    # Konfidensbånd
    konfidensbånd = lr.beregn_konfidensbånd(x_præd, y_præd)

    plt.plot(
        x_præd,
        y_præd,
        "-",
        color="red",
        label=f"Hældning af fit: {lr.beta[1]:.3f} [{y_enhed}/år]",
    )
    plt.plot(
        x_præd,
        konfidensbånd[0, :],
        "g-",
    )
    plt.plot(
        x_præd,
        konfidensbånd[1, :],
        "g-",
        label="95% konf. bånd",
    )
    plot_data(lr.x, lr.y)

"""This module contains functions for geodetic correction of height differences/levelling observations."""

from pathlib import Path

from dataclasses import dataclass
import pandas as pd

from fire.api.geodetic_levelling.tidal_transformation import (
    apply_tidal_corrections_to_height_diff,
)

from fire.api.geodetic_levelling.time_propagation import (
    propagate_height_diff_from_epoch_to_epoch,
)

from fire.api.geodetic_levelling.metric_to_gpu_transformation import (
    convert_metric_height_diff_to_geopotential_height_diff,
)
from fire.api.niv.datatyper import NivKote, NivObservation


@dataclass
class ObsCorrections:
    m2gpu_factor: float = 1
    tidal_corr: float = 0
    epoch_corr: float = 0

def apply_corrections_to_list_of_height_diffs(
    observationer: dict[str, NivObservation],
    koter: dict[str, NivKote],
    height_diff_unit: str = "metric",
    epoch_target: pd.Timestamp = None,
    tidal_system: str = None,
    grid_inputfolder: Path = None,
    deformationmodel: str = None,
    gravitymodel: str = None,
):
    fra_punkter = []
    til_punkter = []
    korrektioner: list[ObsCorrections] = []

    for idx, obs in observationer.items():
        deltah_corrected, korrektion = apply_geodetic_corrections_to_height_diffs(
            obs.deltaH,
            koter[obs.fra].øst,
            koter[obs.fra].nord,
            koter[obs.til].øst,
            koter[obs.til].nord,
            obs.dato,
            height_diff_unit,
            epoch_target,
            tidal_system,
            grid_inputfolder,
            deformationmodel,
            gravitymodel,
        )
        observationer[idx].deltaH = deltah_corrected

        # Gem værdier som skal gemmes i excel
        fra_punkter.append(obs.fra)
        til_punkter.append(obs.til)
        korrektioner.append([korrektion.tidal_corr, korrektion.epoch_corr, korrektion.m2gpu_factor])

    data = [
        fra_punkter,
        til_punkter,
        *[list(k) for k in zip(*korrektioner)]
    ]
    korrektioner_obs = pd.DataFrame(
        data=data,
        columns=[
            "From point",
            "To point",
            f"ΔH tidal correction (tidal system: {tidal_system}) [m]",
            f"ΔH epoch correction (target epoch: {epoch_target}) [m]",
            f"ΔH m2gpu multiplication factor (tidal system: {tidal_system}) [10 m/s^2]",
        ],
    )

    return observationer, korrektioner_obs

def apply_geodetic_corrections_to_height_diffs(
    height_diff: float,
    point_from_long: float,
    point_from_lat: float,
    point_to_long: float,
    point_to_lat: float,
    epoch_obs: pd.Timestamp,
    height_diff_unit: str = "metric",
    epoch_target: pd.Timestamp = None,
    tidal_system: str = None,
    grid_inputfolder: Path = None,
    deformationmodel: str = None,
    gravitymodel: str = None,
) -> tuple[float, ObsCorrections]:
    """Apply geodetic corrections to metric height differences.

    Applies various geodetic corrections to the metric height differences in a list of
    NivObservation objects.

    The metric height differences are tidally corrected if and only if the function is called
    with an argument for parameter tidal_system.

    The metric height differences are propagated to a target epoch if and only if
    the function is called with arguments for all three parameters epoch_target, deformationmodel
    and grid_inputfolder.

    The metric height differences are converted to geopotential units if and only
    if the function is called with argument "gpu" for parameter height_diff_unit and with arguments
    for both parameter gravitymodel and grid_inputfolder.

    Args:
    height_diff_objects: list[NivObservation], list of NivObservation objects with
    metric height differences to be corrected/converted
    height_objects: list[NivKote], list of NivKote objects with geographic coordinates of from/to points
    height_diff_unit: str = "metric", optional parameter, determines whether or not metric
    input height differences are converted to geopotential units, "metric" for no conversion,
    "gpu" for conversion to gpu, default value is "metric"
    epoch_target: pd.Timestamp = None, optional parameter, target epoch for the propagation
    of metric height differences (format: yyyy-mm-dd hh:mm:ss)
    tidal_system: str = None, optional parameter, system for tidal corrections of metric height
    differences, "non", "mean" or "zero" for non-tidal, mean tide or zero tide
    grid_inputfolder: Path = None, optional parameter, folder for input grid, i.e. deformation model
    and/or gravity model
    deformationmodel: str = None, optional parameter, deformation model used for the propagation
    of metric height differences, must be in GeoTIFF or GTX file format, e.g. "NKG2016_lev.tif"
    gravitymodel: str = None, optional parameter, gravity model used for the conversion of metric
    height differences to gpu, must be in GeoTIFF or GTX file format, e.g. "dk-g-direkte-fra-gri-thokn.tif"

    Returns:
    tuple[list[NivObservation], pd.DataFrame], a tuple containing a list of NivObservation
    objects with corrected/converted height differences (generated from deep copies of the
    inputted NivObservation objects) and a DataFrame with the corrections themselves.

    Raises:
    ? Hvis input mappe eller filer ikke findes, hvis der mangler punkter i points?
    """
    corrections = ObsCorrections()
    if tidal_system is not None:
        (height_diff, tidal_corr) = apply_tidal_corrections_to_height_diff(
            height_diff,
            point_from_lat,
            point_from_long,
            point_to_lat,
            point_to_long,
            epoch_obs,
            tidal_system,
            grid_inputfolder=grid_inputfolder,
            gravitymodel=gravitymodel,
        )

        corrections.tidal_corr = tidal_corr

    # The next steps use grid models of uplift and gravity, so we return if
    # no grid-folder is specified.
    if grid_inputfolder is None:
        return height_diff, corrections

    # Perform uplift-correction if both epoch_target and deformationmodel is specified
    if (epoch_target is not None) and (deformationmodel is not None):
        (height_diff, epoch_corr) = propagate_height_diff_from_epoch_to_epoch(
            height_diff,
            point_from_lat,
            point_from_long,
            point_to_lat,
            point_to_long,
            epoch_obs,
            epoch_target,
            grid_inputfolder,
            deformationmodel,
        )

        corrections.epoch_corr = epoch_corr

    # Perform metric-to-gpu conversion if output-unit is set to gpu and gravitymodel is
    # specified
    if height_diff_unit == "gpu" and gravitymodel is not None:
        height_diff, m2gpu_factor = (
            convert_metric_height_diff_to_geopotential_height_diff(
                height_diff,
                point_from_lat,
                point_from_long,
                point_to_lat,
                point_to_long,
                tidal_system,
                grid_inputfolder,
                gravitymodel,
            )
        )

        corrections.m2gpu_factor = m2gpu_factor

    return height_diff, corrections

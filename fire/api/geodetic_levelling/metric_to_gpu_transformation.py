"""This module contains functions for transformation of metric heights or height differences
to geopotential units or vice versa.
"""

from math import sin, pi
from pathlib import Path

import pandas as pd
import pyproj

from fire.api.geodetic_levelling.tidal_transformation import (
    transform_gravity_from_tidal_system_to_tidal_system,
)

import fire.api.geodetic_levelling.geophysical_parameters as geo_p


def interpolate_gravity(
    latitude: float,
    longitude: float,
    grid_inputfolder: Path,
    gravitymodel: str,
    gravitymodel2: str,
) -> float:
    """Interpolate in gravity model.

    Interpolates bilinearly in a grid-based gravity model and returns the result as a float.

    Args:
    latitude: float, latitude for which gravity is interpolated, in units of degrees
    longitude: float, longitude for which gravity is interpolated, in units of degrees
    grid_inputfolder: Path, folder for input grid, i.e. gravity model
    gravitymodel: str, grid-based model providing gravity in units of mGal (1 mGal = 10^-5 m/s^2),
    must be in GeoTIFF or GTX file format, e.g. "dk-g-direkte-fra-gri-thokn.tif"

    Returns:
    float, interpolated gravity in units of m/s^2

    Raises:
    ?
    """
    pyproj.datadir.append_data_dir(grid_inputfolder)

    # Transformer object for interpolation in gravity model
    transformer = pyproj.Transformer.from_pipeline(
        f"+proj=vgridshift +grids={gravitymodel}"
    )

    # Interpolated gravity in units of m/s^2
    gravity = transformer.transform(longitude, latitude, 0)[2] * 1e-5 * -1

    return gravity


def convert_metric_height_diff_to_geopotential_height_diff(
    height_diff: float,
    point_from_lat: float,
    point_from_long: float,
    point_to_lat: float,
    point_to_long: float,
    tidal_system: str | None,
    gravitymodel: str,
) -> tuple[float, float]:
    """Convert a metric height difference to a geopotential height difference.

    Converts a metric height difference to a geopotential height difference (in units of gpu)
    and returns the converted height difference and the m2gpu multiplication factor in a tuple.

    The gravity model used for the conversion is assumed to be in zero tide system as this is
    the conventional tide system for gravity.

    If the input height difference is in the zero tide system, the gravity interpolated from the
    gravity model is not tidally transformed.

    If the input height difference is in non-tidal or mean tide system, the gravity interpolated
    from the gravity model is transformed from the zero tide system to the tidal system of the
    input height difference.

    If the input height difference is not corrected for tidal effects, the gravity interpolated
    from the gravity model is transformed from the zero tide system to the mean tide system.

    Args:
    height_diff: float, metric height difference to be converted to gpu
    point_from_lat: float, latitude of from point in units of degrees
    point_from_long: float, longitude of from point in units of degrees
    point_to_lat: float, latitiude of to point in units of degrees
    point_to_long: float, longitude of to point in units of degrees
    tidal_system: str|None, tidal system of input height difference, i.e. "non", "mean" or "zero"
    for non-tidal, mean tide or zero tide or None if the input height difference is not corrected
    for tidal effects
    gravitymodel: str, gravity model used for the conversion of a height difference to gpu,
    must be in GeoTIFF or GTX file format, e.g. "dk-g-direkte-fra-gri-thokn.tif"

    Returns:
    tuple[float, float], a tuple containing the converted height difference
    in units of gpu (1 gpu = 10 m^2/s^2) and the m2gpu multiplication factor in units of m/s^2

    Raises:
    ? Hvis gravitymodel ikke er i et pyproj datadir

    TO DO: Bestem tyngde vha. funktionen interpolate_gravity
    """
    # Point_from and point_to gravity in units of m/s^2
    # Flyt til overfunktionen delta_h_corr?
    # KREBSLW: her bør interpolate_gravity vel bruges?
    transformer = pyproj.Transformer.from_pipeline(
        f"+proj=vgridshift +grids={gravitymodel}"
    )

    point_from_gravity = (
        transformer.transform(point_from_long, point_from_lat, 0)[2] * 1e-5 * -1
    )

    point_to_gravity = (
        transformer.transform(point_to_long, point_to_lat, 0)[2] * 1e-5 * -1
    )

    # Interpolated gravity is tidally transformed if tidal system of input height difference
    # is different than zero tide
    if tidal_system == "zero":
        pass

    elif tidal_system == "non":
        point_from_gravity = transform_gravity_from_tidal_system_to_tidal_system(
            point_from_gravity, point_from_lat, "zero_to_non"
        )

        point_to_gravity = transform_gravity_from_tidal_system_to_tidal_system(
            point_to_gravity, point_to_lat, "zero_to_non"
        )

    elif tidal_system == "mean" or tidal_system == None:
        point_from_gravity = transform_gravity_from_tidal_system_to_tidal_system(
            point_from_gravity, point_from_lat, "zero_to_mean"
        )

        point_to_gravity = transform_gravity_from_tidal_system_to_tidal_system(
            point_to_gravity, point_to_lat, "zero_to_mean"
        )

    # Mean gravity in units of m/s^2
    mean_gravity = (point_from_gravity + point_to_gravity) / 2

    # Conversion of height_diff to geopotential units (1 gpu = 10 m^2/s^2)
    m2gpu_factor = mean_gravity * 0.1
    height_diff = height_diff * m2gpu_factor

    return (height_diff, m2gpu_factor)


def convert_geopotential_heights_to_helmert_heights(
    fire_project: str,
    excel_inputfolder: Path,
    outputfolder: Path,
    grid_inputfolder: Path,
    gravitymodel: str,
    conversion: str,
    tidal_system: str = None,
) -> None:
    """Convert geopotential heights to metric Helmert heights or vice versa.

    Converts geopotential heights of a FIRE project to metric Helmert heights or vice versa.

    Reference:
    Klaus Schmidt, The Danish height system DVR90, pp. app 14-15.
    National Survey and Cadastre, 2000

    If geopotential heights are to be converted to metric Helmert heights
    (parameter conversion = "geopot_to_helmert") the input heights are taken from column "Ny kote"
    in the sheet "Kontrolberegning" in the input excel-file and the converted heights are
    written to column "Ny kote" in the sheet "Kontrolberegning" in the output excel-file.
    The conversion of geopotential heights to metric Helmert heights requires a priori
    metric Helmert heights, which are taken from column "Kote" in the input excel-file.
    Note that the accuracy of the converted heights depends on the accuracy
    of the a priori values.

    If metric Helmert heights are to be converted to geopotential heights
    (parameter conversion = "helmert_to_geopot") the input heights are taken from column "Kote" in the
    sheet "Kontrolberegning" in the input excel-file and the converted heights are wtitten
    to column "Ny kote" in the sheet "Kontrolberegning" in the output excel-file. TO DO: Change
    this to sheet "Punktoversigt"?

    The gravity model used for the conversion of geopotential heights to metric Helmert heights
    (or vice versa) is assumed to be in zero tide system as this is the conventional tide system
    for gravity.

    If the input heights are in the zero tide system, the gravity values interpolated from the
    gravity model are not tidally transformed.

    If the input heights are in non-tidal or mean tide system, the gravity values interpolated
    from the gravity model are transformed from the zero tide system to the tidal system of the
    input heights.

    If the input heights are not corrected for tidal effects, the gravity values interpolated
    from the gravity model are transformed from the zero tide system to the mean tide system.

    Args:
    fire_project: str, name of FIRE project with heights to be converted, must be in accordance
    with the name of the input excel-file, e.g. "asmei_temp"
    excel_inputfolder: Path, folder with input FIRE project/excel-file with heights to be converted
    outputfolder: Path, folder for output FIRE project/excel-file with converted heights
    grid_inputfolder: Path, folder for input grid, i.e. gravity model
    gravitymodel: str, gravity model used for the conversion of heights, must be in GeoTIFF
    or GTX file format, e.g. "dk-g-direkte-fra-gri-thokn.tif"
    conversion: str, direction of height conversion, "geopot_to_helmert" or "helmert_to_geopot"
    tidal_system: str = None, optional parameter, tidal system of input heights, i.e. "non", "mean"
    or "zero" for non-tidal, mean tide or zero tide. If no argument is passed it is assumed that
    the input heights are not corrected for tidal effects

    Returns:
    None

    Raises:
    ? Hvis grid_inputfolder ikke findes, hvis grid-fil ikke findes, hvis input excel-fil ikke findes

    Input file:
    FIRE project/excel-file with heights to be converted, e.g. "asmei_temp.xlsx"

    Output file:
    Excel-file with converted heights. This file contains the converted heights in column "Ny kote"
    as well as the conversion factor used for height conversion. Except for that the file is identical
    to the input excel-file.

    TO DO: Warning hvis a apriori Helmert højde mangler? print punktnr, hvad er betingelsen, = None?
    TO DO: Should it be called a transformation rather than a conversion?
    """
    # Make sure that the output folder exists
    outputfolder.mkdir(parents=True, exist_ok=True)

    pyproj.datadir.append_data_dir(grid_inputfolder)

    # Creation of a Transformer for interpolation in gravity model
    transformer = pyproj.Transformer.from_pipeline(
        f"+proj=vgridshift +grids={gravitymodel}"
    )

    excel_inputfile = excel_inputfolder / f"{fire_project}.xlsx"

    # DataFrame with heights etc. from input fire project
    points_df = pd.read_excel(excel_inputfile, sheet_name="Kontrolberegning")

    for index in points_df.index:
        h_adjusted = points_df.at[index, "Ny kote"]
        h_db = points_df.at[index, "Kote"]
        point_lat = points_df.at[index, "Nord"]
        point_long = points_df.at[index, "Øst"]

        # Gravity in units of m/s^2
        point_gravity = transformer.transform(point_long, point_lat, 0)[2] * 1e-5 * -1

        # Måske bedre at flytte de to if-konstruktioner op foran for-løkken?
        # Men så bliver koden væsentlig længere?
        # Interpolated gravity is tidally transformed if tidal system of input heights
        # is different than zero tide
        if tidal_system == "zero":
            pass

        elif tidal_system == "non":
            point_gravity = transform_gravity_from_tidal_system_to_tidal_system(
                point_gravity, point_lat, "zero_to_non"
            )

        elif tidal_system == "mean" or tidal_system == None:
            point_gravity = transform_gravity_from_tidal_system_to_tidal_system(
                point_gravity, point_lat, "zero_to_mean"
            )

        # Conversion factor (metric Helmert heights to geopotential heights) in units of 10 m/s^2
        conversion_factor = (point_gravity * 0.1) + (0.07045 * 1e-6 * h_db)

        # Conversion of heights and update of points_df
        if conversion == "geopot_to_helmert":
            h_converted = h_adjusted / conversion_factor
            points_df.at[index, "Ny kote"] = h_converted
            points_df.at[index, "Conversion factor [10 m/s^2]"] = conversion_factor

        elif conversion == "helmert_to_geopot":
            h_converted = h_db * conversion_factor
            points_df.at[index, "Ny kote"] = h_converted
            points_df.at[index, "Conversion factor [10 m/s^2]"] = conversion_factor

        else:
            exit(
                "Function convert_geopotential_heights_to_helmert_heights: Wrong argument for\n\
            parameter conversion. Only 'geopot_to_helmert' or 'helmert_to_geopot' is allowed."
            )

    # DataFrame with parameters of output fire project
    parameters_df = pd.read_excel(excel_inputfile, sheet_name="Parametre")

    parameters_new_df = pd.DataFrame(
        {
            "Navn": [
                "Conversion of heights",
                "Gravitymodel for conversion of heights",
            ],
            "Værdi": [conversion, gravitymodel],
        },
    )

    parameters_df = pd.concat([parameters_df, parameters_new_df], ignore_index=True)

    # Generation of output fire project/excel file with converted heights
    with pd.ExcelWriter(
        outputfolder / f"{fire_project}.xlsx"
    ) as writer:  # pylint: disable=abstract-class-instantiated
        pd.read_excel(excel_inputfile, sheet_name="Projektforside").to_excel(
            writer, "Projektforside", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Sagsgang").to_excel(
            writer, "Sagsgang", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Nyetablerede punkter").to_excel(
            writer, "Nyetablerede punkter", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Notater").to_excel(
            writer, "Notater", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Filoversigt").to_excel(
            writer, "Filoversigt", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Observationer").to_excel(
            writer, "Observationer", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Punktoversigt").to_excel(
            writer, "Punktoversigt", index=False
        )
        points_df.to_excel(writer, "Kontrolberegning", index=False)
        parameters_df.to_excel(writer, "Parametre", index=False)


def calculate_normal_gravity(
    latitude: float,
) -> float:
    """Calculate normal gravity at the GRS80 ellipsoid.

    Calculates normal gravity at the GRS80 ellipsoid.

    Reference:
    Johannes Ihde et al., Conventions for the Definition and Realization of a
    European Vertical Reference System (EVRS) - EVRS Conventions 2007, p. 10, eq. (A-1).
    EUREF, 2019

    H. Moritz, GEODETIC REFERENCE SYSTEM 1980

    TO DO: Tidal system of calculated normal gravity?

    Args:
    latitude: float, latitude for which normal gravity is calculated, in units of degrees

    Returns:
    float, calculated normal gravity in units of m/s^2

    Raises:
    ?
    """
    # Conversion of latitude to radians
    latitude = (latitude / 360) * 2 * pi

    # Coefficients of series expansion for calculation of normal gravity
    a = 0.0052790414
    b = 0.0000232718
    c = 0.0000001262
    d = 0.0000000007

    normal_gravity = geo_p.normal_gravity_equator_GRS80 * (
        1
        + a * sin(latitude) ** 2
        + b * sin(latitude) ** 4
        + c * sin(latitude) ** 6
        + d * sin(latitude) ** 8
    )

    return normal_gravity


def calculate_average_normal_gravity(
    latitude: float,
    normal_height: float,
) -> float:
    """Calculate average normal gravity.

    Calculates the average normal gravity along the normal plumb line between
    the GRS80 ellipsoid and the telluroid.

    Reference:
    Johannes Ihde et al., Conventions for the Definition and Realization of a
    European Vertical Reference System (EVRS) - EVRS Conventions 2007, p. 10, eq. (A-2).
    EUREF, 2019

    H. Moritz, GEODETIC REFERENCE SYSTEM 1980

    Args:
    latitude: float, latitude for which average normal gravity is calculated, in units of degrees
    normal_height: float, approximate normal height, in units of meters

    Returns:
    float, calculated average normal gravity in units of m/s^2

    Raises:
    ?

    TO DO: Handling of tidal system?, Tidal system of calculated average normal gravity?
    """
    # Calculation of normal gravity at the ellipsoid
    normal_gravity = calculate_normal_gravity(latitude)

    # Conversion of latitude to radians
    latitude = (latitude / 360) * 2 * pi

    # Calculation of average normal gravity
    r = 1 + geo_p.f_GRS80 + geo_p.m_GRS80 - 2 * geo_p.f_GRS80 * sin(latitude) ** 2
    s = normal_height / geo_p.a_GRS80

    average_normal_gravity = normal_gravity * (1 - r * s + s**2)

    return average_normal_gravity


def convert_geopotential_heights_to_normal_heights(
    fire_project: str,
    excel_inputfolder: Path,
    outputfolder: Path,
    conversion: str,
) -> None:
    """Convert geopotential heights to normal heights or vice versa.

    Converts geopotential heights of a FIRE project to GRS80 normal heights or vice versa.

    References:
    Johannes Ihde et al., Conventions for the Definition and Realization of a
    European Vertical Reference System (EVRS) - EVRS Conventions 2007. EUREF, 2019

    H. Moritz, GEODETIC REFERENCE SYSTEM 1980

    If geopotential heights are to be converted to normal heights
    (parameter conversion = "geopot_to_normal") the input heights are taken from column "Ny kote"
    in the sheet "Kontrolberegning" in the input excel-file and the converted heights are
    written to column "Ny kote" in the sheet "Kontrolberegning" in the output excel-file.

    The conversion of geopotential heights to normal heights requires a priori normal heights,
    which are taken from column "Kote" in the sheet "Kontrolberegning" in the input excel-file
    (it is assumed that the Helmert heights in column "Kote" are close to the normal heights).
    Note that the accuracy of the converted heights depends on the accuracy of the a priori values.

    If normal heights are to be converted to geopotential heights
    (parameter conversion = "normal_to_geopot") the input heights are taken from column "Kote" in
    the sheet "Kontrolberegning" in the input excel-file and the converted heights are written
    to column "Ny kote" in the sheet "Kontrolberegning" in the output excel-file. NB: usually the
    column "Kote" in the sheet "Kontrolberegning" contains Helmerts heights, not normal heights.
    TO DO: Change this to sheet "Punktoversigt"?

    TO DO: Handling of tidal corrections/systems?

    Args:
    fire_project: str, name of FIRE project with heights to be converted, must correspond
    to the name of the input excel-file, e.g. "asmei_temp"
    excel_inputfolder: Path, folder with input FIRE project/excel-file with heights to be converted
    outputfolder: Path, folder for output FIRE project/excel-file with converted heights
    conversion: str, direction of height conversion, "geopot_to_normal" or "normal_to_geopot"

    Returns:
    None

    Raises:
    ? hvis input excel-fil ikke findes

    Input file:
    FIRE project/excel-file with heights to be converted, e.g. "asmei_temp.xlsx"

    Output file:
    Excel-file with converted heights. This file contains the converted heights in column "Ny kote"
    as well as the average normal gravity used for height conversion. Except for that the file is
    identical to the input excel-file.

    TO DO: Warning hvis a apriori normal højde mangler? print punktnr, hvad er betingelsen, = None?
    TO DO: Should it be called a transformation rather than a conversion?
    """
    # Make sure that the output folder exists
    outputfolder.mkdir(parents=True, exist_ok=True)

    excel_inputfile = excel_inputfolder / f"{fire_project}.xlsx"

    # DataFrame with heights etc. from input fire project
    points_df = pd.read_excel(excel_inputfile, sheet_name="Kontrolberegning")

    for index in points_df.index:
        h_adjusted = points_df.at[index, "Ny kote"]
        h_db = points_df.at[index, "Kote"]
        point_lat = points_df.at[index, "Nord"]
        point_long = points_df.at[index, "Øst"]

        # # Måske bedre at flytte de to if-konstruktioner op foran for-løkken?
        # # Men så bliver koden væsentlig længere?

        # Calculation of average normal gravity in units of 10 m/s^2
        average_normal_gravity = calculate_average_normal_gravity(point_lat, h_db) * 0.1

        # Conversion of heights and update of points_df
        if conversion == "geopot_to_normal":
            h_converted = h_adjusted / average_normal_gravity
            points_df.at[index, "Ny kote"] = h_converted
            points_df.at[index, "Average normal gravity [10 m/s^2]"] = (
                average_normal_gravity
            )

        elif conversion == "normal_to_geopot":
            h_converted = h_db * average_normal_gravity
            points_df.at[index, "Ny kote"] = h_converted
            points_df.at[index, "Average normal gravity [10 m/s^2]"] = (
                average_normal_gravity
            )

        else:
            exit(
                "Function convert_geopotential_heights_to_normal_heights: "
                "Wrong argument for parameter conversion. Only 'geopot_to_normal' "
                "or 'normal_to_geopot' is allowed."
            )

    # DataFrame with parameters of output fire project
    parameters_df = pd.read_excel(excel_inputfile, sheet_name="Parametre")

    parameters_new_df = pd.DataFrame(
        {
            "Navn": [
                "Conversion of heights",
            ],
            "Værdi": [conversion],
        },
    )

    parameters_df = pd.concat([parameters_df, parameters_new_df], ignore_index=True)

    # Generation of output fire project/excel file with converted heights
    with pd.ExcelWriter(
        outputfolder / f"{fire_project}.xlsx"
    ) as writer:  # pylint: disable=abstract-class-instantiated
        pd.read_excel(excel_inputfile, sheet_name="Projektforside").to_excel(
            writer, "Projektforside", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Sagsgang").to_excel(
            writer, "Sagsgang", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Nyetablerede punkter").to_excel(
            writer, "Nyetablerede punkter", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Notater").to_excel(
            writer, "Notater", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Filoversigt").to_excel(
            writer, "Filoversigt", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Observationer").to_excel(
            writer, "Observationer", index=False
        )
        pd.read_excel(excel_inputfile, sheet_name="Punktoversigt").to_excel(
            writer, "Punktoversigt", index=False
        )
        points_df.to_excel(writer, "Kontrolberegning", index=False)
        parameters_df.to_excel(writer, "Parametre", index=False)

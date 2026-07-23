"""
Generates synthetic well log data that *looks* geologically plausible
(layered formations with characteristic curve responses) rather than
pure random noise, so the viewer has something meaningful to render
and so a later QC/anomaly-detection feature has real signal to find.

This stands in for what the real OSDU Wellbore DDMS / WellLog
work-product-component APIs would return. The shapes (Well,
Wellbore, WellLog, LogCurve) match models/osdu_models.py.
"""

import numpy as np
from models.osdu_models import Well, Wellbore, WellLog, LogCurve

RNG = np.random.default_rng(seed=42)


def _layered_curve(depth, layer_boundaries, layer_values, noise_std):
    """Build a curve that steps between layer_values at layer_boundaries,
    with smoothing + noise so it isn't a perfect staircase."""
    values = np.zeros_like(depth)
    for i in range(len(layer_boundaries) - 1):
        mask = (depth >= layer_boundaries[i]) & (depth < layer_boundaries[i + 1])
        values[mask] = layer_values[i]
    # smooth transitions
    kernel = np.ones(15) / 15
    values = np.convolve(values, kernel, mode="same")
    values += RNG.normal(0, noise_std, size=depth.shape)
    return values


def _generate_well_log(wellbore_id: str, top: float, bottom: float, step: float = 0.1525) -> WellLog:
    """0.1525 m (~0.5 ft) sample step is typical for wireline logs."""
    depth = np.arange(top, bottom, step)
    n_layers = RNG.integers(4, 8)
    boundaries = np.sort(RNG.uniform(top, bottom, size=n_layers - 1))
    boundaries = np.concatenate([[top], boundaries, [bottom]])

    # Rough facies-driven curve responses per layer (sand vs shale vs carbonate-ish)
    facies = RNG.choice(["sand", "shale", "carbonate"], size=n_layers)
    gr_vals, rhob_vals, nphi_vals, rt_vals = [], [], [], []
    for f in facies:
        if f == "sand":
            gr_vals.append(RNG.uniform(20, 50))
            rhob_vals.append(RNG.uniform(2.2, 2.35))
            nphi_vals.append(RNG.uniform(0.2, 0.3))
            rt_vals.append(RNG.uniform(20, 100))
        elif f == "shale":
            gr_vals.append(RNG.uniform(80, 140))
            rhob_vals.append(RNG.uniform(2.4, 2.55))
            nphi_vals.append(RNG.uniform(0.3, 0.4))
            rt_vals.append(RNG.uniform(2, 10))
        else:  # carbonate
            gr_vals.append(RNG.uniform(10, 30))
            rhob_vals.append(RNG.uniform(2.5, 2.7))
            nphi_vals.append(RNG.uniform(0.05, 0.15))
            rt_vals.append(RNG.uniform(50, 500))

    gr = np.clip(_layered_curve(depth, boundaries, gr_vals, 3), 0, 250)
    rhob = np.clip(_layered_curve(depth, boundaries, rhob_vals, 0.02), 1.8, 3.0)
    nphi = np.clip(_layered_curve(depth, boundaries, nphi_vals, 0.01), 0, 0.5)
    rt = np.clip(_layered_curve(depth, boundaries, rt_vals, 5), 0.2, 2000)

    curves = [
        LogCurve("GR", "GAPI", "Gamma Ray", depth.copy(), gr),
        LogCurve("RHOB", "G/C3", "Bulk Density", depth.copy(), rhob),
        LogCurve("NPHI", "V/V", "Neutron Porosity", depth.copy(), nphi),
        LogCurve("RT", "OHMM", "Deep Resistivity", depth.copy(), rt),
    ]

    return WellLog(
        id=f"osdu:work-product-component--WellLog:{wellbore_id}-log1",
        wellbore_id=wellbore_id,
        name=f"{wellbore_id} - Composite Log",
        top_depth=top,
        bottom_depth=bottom,
        curves=curves,
    )


def get_mock_wells():
    """Returns (wells, wellbores, well_logs_by_wellbore_id)."""
    well_defs = [
        ("Eldfisk Field", "Eldfisk A-1", "ConocoPhillips Skandinavia", "Norway", 56.40, 3.25, 1800, 3000),
        ("Eldfisk Field", "Eldfisk A-2", "ConocoPhillips Skandinavia", "Norway", 56.41, 3.26, 1750, 2950),
        ("Ekofisk Field", "Ekofisk 2/4-X", "ConocoPhillips Skandinavia", "Norway", 56.55, 3.21, 2000, 3200),
        ("Permian Basin", "Wolfcamp-14H", "Pioneer Natural Resources", "USA", 31.85, -102.35, 1500, 2600),
        ("Permian Basin", "Wolfcamp-22H", "Pioneer Natural Resources", "USA", 31.87, -102.37, 1550, 2650),
    ]

    wells, wellbores = [], []
    logs_by_wellbore = {}

    for i, (field, name, operator, country, lat, lon, top, bottom) in enumerate(well_defs, start=1):
        well_id = f"osdu:master-data--Well:{i:04d}"
        wellbore_id = f"osdu:master-data--Wellbore:{i:04d}"

        wells.append(Well(
            id=well_id, name=name, field_name=field, operator=operator,
            country=country, latitude=lat, longitude=lon,
        ))
        wellbores.append(Wellbore(
            id=wellbore_id, well_id=well_id, name=f"{name} Wellbore",
            wellbore_datum="KB", total_depth_md=bottom,
        ))
        logs_by_wellbore[wellbore_id] = _generate_well_log(wellbore_id, top, bottom)

    return wells, wellbores, logs_by_wellbore

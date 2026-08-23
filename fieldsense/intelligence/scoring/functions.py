"""Reusable deterministic scoring functions for FieldSense parameters."""

from .config import ParameterScoringBand


def optimum_range_score(val: float, band: ParameterScoringBand) -> float:
    """Calculate optimum-range score for parameters like pH or moisture.

    Returns 1.0 within [target_min, target_max].
    Decreases smoothly towards 0.0 at low_bound (below) and high_bound (above).
    """
    if band.target_min <= val <= band.target_max:
        return 1.0
    elif val < band.target_min:
        if val <= band.low_bound:
            return 0.0
        return (val - band.low_bound) / (band.target_min - band.low_bound)
    else:  # val > band.target_max
        if val >= band.high_bound:
            return 0.0
        return (band.high_bound - val) / (band.high_bound - band.target_max)


def upper_limit_penalty_score(val: float, ideal_max: float, severe_max: float) -> float:
    """Calculate upper-limit penalty score for parameters like EC (salinity).

    Returns 1.0 for val <= ideal_max.
    Decreases linearly to 0.0 at severe_max.
    """
    if val <= ideal_max:
        return 1.0
    elif val >= severe_max:
        return 0.0
    else:
        return (severe_max - val) / (severe_max - ideal_max)


def adequacy_band_score(val: float, band: ParameterScoringBand) -> float:
    """Calculate adequacy / reference-band score for nutrients (N/P/K).

    Returns 1.0 within adequate band [target_min, target_max].
    Scales from 0.0 at low_bound up to 1.0 at target_min.
    Above target_max, applies slight excessive nutrient penalty down to 0.5 at high_bound.
    """
    if band.target_min <= val <= band.target_max:
        return 1.0
    elif val < band.target_min:
        if val <= band.low_bound:
            return 0.0
        return (val - band.low_bound) / (band.target_min - band.low_bound)
    else:  # val > band.target_max
        if val >= band.high_bound:
            return 0.5
        # Soft penalty from 1.0 at target_max down to 0.5 at high_bound
        fraction = (val - band.target_max) / (band.high_bound - band.target_max)
        return 1.0 - 0.5 * fraction


def interpret_score(score: float) -> str:
    """Classify a score into prototype interpretation category."""
    if score >= 0.70:
        return "HEALTHY"
    elif score >= 0.40:
        return "MODERATE"
    else:
        return "POOR"

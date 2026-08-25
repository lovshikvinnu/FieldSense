"""Distance between two fixes, and whether that distance means anything.

A previous bench run recorded five samples whose coordinates were all
different, spread 8.0 m diagonally at HDOP 3.58, with points 3/4/5 differing in
the seventh decimal place — about a centimetre. Five distinct coordinates, one
physical location. The dashboard interpolated it anyway and produced a map.

That is the failure this module exists to prevent. Distinct numbers are not
distinct positions. The test is whether the separation clears the receiver's
own uncertainty, and a consumer GNSS fix does not know its position to the
centimetre no matter how many decimals it prints.
"""

import math
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

#: Mean Earth radius, metres. The spherical approximation is worth millimetres
#: of error over the tens of metres a soil-sampling grid spans; the GPS
#: uncertainty below is three orders of magnitude larger.
EARTH_RADIUS_M = 6_371_008.8

#: User-equivalent range error in metres, the per-satellite error budget that
#: HDOP multiplies. 3.0 m is a conventional working figure for an uncorrected
#: consumer L1 receiver; it is NOT measured on this NEO-M8N. It is exposed as a
#: parameter for exactly that reason — treat it as the stated assumption behind
#: every "did it actually move" answer, not as a property of the hardware.
DEFAULT_UERE_M = 3.0

#: Floor on estimated uncertainty. Even at HDOP 0.5 a bare receiver is not good
#: to 1.5 m, and without a floor an optimistic HDOP would let centimetre jitter
#: read as movement — the precise failure this module was written for.
MIN_UNCERTAINTY_M = 2.5

#: Separation must exceed this multiple of the combined uncertainty before two
#: fixes are called distinct locations. 2.0 is a deliberately conservative
#: choice: calling a real move "not distinct" costs an advisory line on the
#: panel, while the opposite mistake puts a fabricated gradient on a map.
DISTINCT_SIGMA = 2.0

#: Stand-in uncertainty for a fix that reports no HDOP at all. Large enough
#: that no realistic sampling walk clears it, which is the point: a fix with no
#: precision figure cannot support a claim about movement, and treating it as
#: merely "poor" would let a big enough number pass as evidence anyway. The
#: verdict text says "cannot be established" rather than quoting this, so it is
#: never mistaken for a measured error bar.
UNKNOWN_UNCERTAINTY_M = 1000.0


def haversine_meters(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Great-circle distance between two WGS84 points, in metres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = phi2 - phi1
    d_lambda = math.radians(lon2 - lon1)
    a = (math.sin(d_phi / 2.0) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2.0) ** 2)
    return 2.0 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def position_uncertainty_m(hdop: Optional[float], uere_m: float = DEFAULT_UERE_M) -> float:
    """Estimate horizontal uncertainty in metres from HDOP.

    Args:
        hdop: Horizontal dilution of precision from the GGA sentence. None or a
            non-positive value is treated as "unknown", which is not the same as
            "good": an unknown HDOP yields the widest uncertainty this function
            will report, so an unlabelled fix can never be used to claim
            movement.
        uere_m: Per-satellite range error budget. See DEFAULT_UERE_M.

    Returns:
        Estimated horizontal error in metres, never below MIN_UNCERTAINTY_M.
    """
    try:
        value = float(hdop)
    except (TypeError, ValueError):
        value = 0.0
    # 99.9 is the sketch's cold-start sentinel for "no fix"; anything at or
    # above it carries no information about precision, and neither does a
    # missing or non-positive value.
    if value <= 0.0 or value >= 99.9 or math.isnan(value) or math.isinf(value):
        return UNKNOWN_UNCERTAINTY_M
    return max(MIN_UNCERTAINTY_M, value * uere_m)


def hdop_is_usable(hdop: Optional[float]) -> bool:
    """True when this HDOP carries real precision information."""
    return position_uncertainty_m(hdop) < UNKNOWN_UNCERTAINTY_M


@dataclass(frozen=True)
class MovementVerdict:
    """Whether two fixes describe two places, and the numbers behind the answer."""

    distance_m: float
    uncertainty_m: float
    threshold_m: float
    distinct: bool
    detail: str

    def to_dict(self) -> dict:
        """Serialize for the durable sample record."""
        return {
            "distance_m": round(self.distance_m, 3),
            "uncertainty_m": round(self.uncertainty_m, 2),
            "threshold_m": round(self.threshold_m, 2),
            "distinct": self.distinct,
            "detail": self.detail,
        }


def assess_movement(
    previous: Tuple[float, float],
    previous_hdop: Optional[float],
    current: Tuple[float, float],
    current_hdop: Optional[float],
    uere_m: float = DEFAULT_UERE_M,
    sigma: float = DISTINCT_SIGMA,
) -> MovementVerdict:
    """Decide whether the operator actually moved between two samples.

    Uncertainties are combined in quadrature because the two fixes are
    independent measurements; the separation has to clear the error of both
    ends, not just the worse one.

    Returns:
        A MovementVerdict carrying the distance, the uncertainty it was judged
        against, and the verdict. Never raises on odd input — an unusable fix
        produces `distinct=False`, which is the safe answer.
    """
    distance = haversine_meters(previous[0], previous[1], current[0], current[1])
    prev_sigma = position_uncertainty_m(previous_hdop, uere_m)
    curr_sigma = position_uncertainty_m(current_hdop, uere_m)
    combined = math.sqrt(prev_sigma ** 2 + curr_sigma ** 2)
    threshold = sigma * combined
    distinct = distance > threshold

    if not (hdop_is_usable(previous_hdop) and hdop_is_usable(current_hdop)):
        # Do not quote a threshold that was never measured. Saying "16.3 m
        # apart, inside the 847.7 m threshold" invites the reader to argue with
        # a number that came from a placeholder, when the real answer is that
        # this pair of fixes cannot settle the question either way.
        detail = (
            "{:.1f} m apart, but at least one fix reports no usable HDOP, so "
            "movement cannot be established from it".format(distance)
        )
        return MovementVerdict(distance, combined, threshold, False, detail)

    if distinct:
        detail = "moved {:.1f} m, clear of the {:.1f} m jitter threshold".format(
            distance, threshold)
    else:
        detail = (
            "{:.1f} m apart, inside the {:.1f} m GPS jitter threshold "
            "(HDOP {:.2f} -> +/-{:.1f} m); not treated as a new location".format(
                distance, threshold, float(current_hdop), curr_sigma)
        )
    return MovementVerdict(distance, combined, threshold, distinct, detail)


def spatial_spread_m(points: Sequence[Tuple[float, float]]) -> float:
    """Return the greatest separation between any two points, in metres.

    The honest one-number answer to "how big is this field session". Zero for
    fewer than two points rather than an error, because a session in progress
    legitimately has one.
    """
    greatest = 0.0
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            distance = haversine_meters(
                points[i][0], points[i][1], points[j][0], points[j][1])
            if distance > greatest:
                greatest = distance
    return greatest

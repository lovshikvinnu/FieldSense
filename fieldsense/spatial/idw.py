"""Deterministic Inverse Distance Weighting (IDW) interpolator."""

import math
from typing import List, Tuple, Optional
from .grid import GridValue


class IDWInterpolator:
    """Deterministic Inverse Distance Weighting (IDW) interpolator.

    Calculates weighted average of sample values based on inverse distance:
    w_i = 1 / distance^power
    interpolated_value = sum(w_i * v_i) / sum(w_i)
    """

    def __init__(self, power: float = 2.0, max_support_distance: float = 100.0) -> None:
        """Initialize IDW interpolator.

        Args:
            power: Distance exponent power (default 2.0).
            max_support_distance: Maximum radius in meters for sample support.
        """
        self.power = power
        self.max_support_distance = max_support_distance

    def interpolate_point(
        self,
        target_x: float,
        target_y: float,
        sample_points: List[Tuple[float, float, float]],
    ) -> GridValue:
        """Interpolate value at target (x, y) given sample points (x, y, value).

        Args:
            target_x: Target point local x coordinate.
            target_y: Target point local y coordinate.
            sample_points: List of tuples (x, y, value).

        Returns:
            GridValue containing interpolated value and support metadata.
        """
        if not sample_points:
            return GridValue(value=None, nearest_sample_distance=0.0, supporting_sample_count=0)

        weights_and_values: List[Tuple[float, float]] = []
        min_dist = float("inf")
        supporting_count = 0

        for x, y, val in sample_points:
            dist = math.hypot(target_x - x, target_y - y)
            if dist < min_dist:
                min_dist = dist

            # Exact sample location coincidence check (distance ~ 0)
            if dist < 1e-6:
                return GridValue(
                    value=round(val, 4),
                    nearest_sample_distance=0.0,
                    supporting_sample_count=1,
                )

            if dist <= self.max_support_distance:
                supporting_count += 1
                weight = 1.0 / (dist ** self.power)
                weights_and_values.append((weight, val))

        # Check if nearest sample is beyond maximum support distance (avoid uncontrolled extrapolation)
        if min_dist > self.max_support_distance or not weights_and_values:
            return GridValue(
                value=None,
                nearest_sample_distance=round(min_dist, 2),
                supporting_sample_count=0,
            )

        sum_weights = sum(w for w, _ in weights_and_values)
        if sum_weights == 0.0:
            return GridValue(
                value=None,
                nearest_sample_distance=round(min_dist, 2),
                supporting_sample_count=0,
            )

        interpolated_val = sum(w * v for w, v in weights_and_values) / sum_weights
        return GridValue(
            value=round(interpolated_val, 4),
            nearest_sample_distance=round(min_dist, 2),
            supporting_sample_count=supporting_count,
        )

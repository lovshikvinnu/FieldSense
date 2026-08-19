"""Validation reason enum for FieldSense validation engine."""

from enum import Enum


class ValidationReason(str, Enum):
    """Structured reason codes explaining sample validation warnings or rejections."""
    MISSING_VALUE = "MISSING_VALUE"
    INVALID_NUMERIC_VALUE = "INVALID_NUMERIC_VALUE"
    GPS_OUT_OF_RANGE = "GPS_OUT_OF_RANGE"
    MEASUREMENT_OUT_OF_RANGE = "MEASUREMENT_OUT_OF_RANGE"
    LOW_MEASUREMENT_QUALITY = "LOW_MEASUREMENT_QUALITY"
    UNSTABLE_MEASUREMENT = "UNSTABLE_MEASUREMENT"

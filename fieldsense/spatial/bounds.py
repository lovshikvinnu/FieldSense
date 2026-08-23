"""Spatial field boundaries and local Cartesian coordinate converter."""

import math
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple


@dataclass(frozen=True)
class FieldBounds:
    """Bounding box for a spatial field in geographical coordinates."""
    min_latitude: float
    max_latitude: float
    min_longitude: float
    max_longitude: float

    @property
    def center_latitude(self) -> float:
        """Centroid latitude of field bounds."""
        return (self.min_latitude + self.max_latitude) / 2.0

    @property
    def center_longitude(self) -> float:
        """Centroid longitude of field bounds."""
        return (self.min_longitude + self.max_longitude) / 2.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize FieldBounds to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FieldBounds":
        """Deserialize dictionary to FieldBounds."""
        return cls(**data)


class LocalCoordinateConverter:
    """Converts GPS coordinates (lat, lon) to local Cartesian (x, y) in meters.

    Uses a local equirectangular projection centered at reference centroid.
    Suitable for small agricultural field scales:
    - x: East (+m) / West (-m)
    - y: North (+m) / South (-m)
    """

    METERS_PER_LATITUDE_DEGREE = 111000.0

    def __init__(self, ref_latitude: float, ref_longitude: float) -> None:
        self.ref_latitude = ref_latitude
        self.ref_longitude = ref_longitude
        rad_lat = math.radians(ref_latitude)
        self.meters_per_longitude_degree = self.METERS_PER_LATITUDE_DEGREE * math.cos(rad_lat)

    def to_local(self, latitude: float, longitude: float) -> Tuple[float, float]:
        """Convert GPS coordinates to local meters (x, y)."""
        x = (longitude - self.ref_longitude) * self.meters_per_longitude_degree
        y = (latitude - self.ref_latitude) * self.METERS_PER_LATITUDE_DEGREE
        return round(x, 4), round(y, 4)

    def to_gps(self, x: float, y: float) -> Tuple[float, float]:
        """Convert local meters (x, y) back to GPS coordinates (latitude, longitude)."""
        latitude = self.ref_latitude + (y / self.METERS_PER_LATITUDE_DEGREE)
        longitude = self.ref_longitude + (x / self.meters_per_longitude_degree)
        return round(latitude, 6), round(longitude, 6)

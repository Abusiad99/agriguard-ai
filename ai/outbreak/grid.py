"""Regular latitude/longitude grid used to aggregate observations into areas.

Individual scan locations are never shown; observations are counted per cell, and the
public map only shows cells (see the privacy rules in docs/features/outbreak-prediction.md).
At the default 0.25 deg a cell is roughly 28 x 28 km at the equator (narrower toward the poles).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List

DEFAULT_RESOLUTION_DEG = 0.25
MIN_RESOLUTION_DEG = 0.1  # finer cells would make individual farms identifiable


@dataclass(frozen=True)
class GridCell:
    resolution: float
    lat_index: int
    lon_index: int

    @property
    def key(self) -> str:
        return f"{self.resolution:g}:{self.lat_index}:{self.lon_index}"

    @property
    def south(self) -> float:
        return round(self.lat_index * self.resolution, 6)

    @property
    def west(self) -> float:
        return round(self.lon_index * self.resolution, 6)

    @property
    def north(self) -> float:
        return round(self.south + self.resolution, 6)

    @property
    def east(self) -> float:
        return round(self.west + self.resolution, 6)

    @property
    def center(self) -> tuple:
        return (round(self.south + self.resolution / 2, 6), round(self.west + self.resolution / 2, 6))


def validate_coordinates(lat: float, lon: float) -> None:
    if lat is None or lon is None or math.isnan(lat) or math.isnan(lon):
        raise ValueError("latitude and longitude are required")
    if not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
        raise ValueError("latitude must be within -90..90 and longitude within -180..180")


def cell_for(lat: float, lon: float, resolution: float = DEFAULT_RESOLUTION_DEG) -> GridCell:
    validate_coordinates(lat, lon)
    if resolution < MIN_RESOLUTION_DEG:
        raise ValueError(f"grid resolution must be at least {MIN_RESOLUTION_DEG} degrees")
    lat_index = min(math.floor(lat / resolution), math.floor(90 / resolution) - 1)
    lon_index = min(math.floor(lon / resolution), math.floor(180 / resolution) - 1)
    return GridCell(resolution, lat_index, lon_index)


def cell_from_key(key: str) -> GridCell:
    res, lat_index, lon_index = key.split(":")
    return GridCell(float(res), int(lat_index), int(lon_index))


def neighbors(cell: GridCell) -> List[GridCell]:
    return [GridCell(cell.resolution, cell.lat_index + dy, cell.lon_index + dx)
            for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]

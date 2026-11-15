"""Convert latitude/longitude to the map projection used by the Cropland Data Layer.

The CDL is stored in "NAD83 / Conus Albers" (EPSG:5070), so CropScape wants x/y in metres
in that system. This is the standard Albers equal-area conic formula for an ellipsoid
(Snyder, "Map Projections: A Working Manual", 1987, eqs. 14-3 to 14-15) with the
EPSG:5070 constants. Written out here so we do not need the pyproj package.
"""
import math

# GRS80 ellipsoid (what NAD83 uses)
GRS80_A = 6378137.0
GRS80_E2 = (1 / 298.257222101) * (2 - 1 / 298.257222101)

# EPSG:5070 parameters, in degrees
LAT_1, LAT_2 = 29.5, 45.5   # standard parallels
LAT_0, LON_0 = 23.0, -96.0  # projection origin


def make_albers(a: float, e2: float, lat_1=LAT_1, lat_2=LAT_2, lat_0=LAT_0, lon_0=LON_0):
    """Build an Albers projection function for the given ellipsoid and parameters."""
    e = math.sqrt(e2)

    def m(phi):
        s = math.sin(phi)
        return math.cos(phi) / math.sqrt(1 - e2 * s * s)

    def q(phi):
        s = math.sin(phi)
        return (1 - e2) * (s / (1 - e2 * s * s) - (1 / (2 * e)) * math.log((1 - e * s) / (1 + e * s)))

    p1, p2, p0 = (math.radians(v) for v in (lat_1, lat_2, lat_0))
    n = (m(p1) ** 2 - m(p2) ** 2) / (q(p2) - q(p1))
    c = m(p1) ** 2 + n * q(p1)
    rho0 = a * math.sqrt(c - n * q(p0)) / n

    def project(lat: float, lon: float) -> tuple[float, float]:
        rho = a * math.sqrt(c - n * q(math.radians(lat))) / n
        theta = n * math.radians(lon - lon_0)
        return rho * math.sin(theta), rho0 - rho * math.cos(theta)

    return project


# lat/lon -> EPSG:5070 (x, y) in metres
to_albers = make_albers(GRS80_A, GRS80_E2)

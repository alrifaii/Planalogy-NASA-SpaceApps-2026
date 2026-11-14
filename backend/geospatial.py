
"""
Planalogy - NASA Space Apps Challenge 2026

Module: Geospatial Engine
Purpose: Geographical calculations and spatial queries.
"""
import math

from backend.data_interface import (
    load_dataset,
    filter_by_planet,
    PROJECT_ROOT
)


# Mean planetary radii in kilometres
PLANETARY_RADII = {
    "Earth": 6371.0,
    "Moon": 1737.4,
    "Mars": 3389.5
}


def calculate_distance(lat1, lon1, lat2, lon2,
                       planet="Earth"):
    """
    Calculate great-circle distance in kilometres
    using the Haversine formula.
    """

    if planet not in PLANETARY_RADII:
        raise ValueError("Unsupported planetary body.")

    radius = PLANETARY_RADII[planet]

    lat1 = math.radians(lat1)
    lon1 = math.radians(lon1)
    lat2 = math.radians(lat2)
    lon2 = math.radians(lon2)

    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1)
        * math.cos(lat2)
        * math.sin(delta_lon / 2) ** 2
    )

    a = max(0.0, min(1.0, a))

    c = 2 * math.atan2(
        math.sqrt(a),
        math.sqrt(1 - a)
    )

    return radius * c


def find_nearby_locations(
    data, latitude, longitude,
    radius_km, planet="Earth"
):
    """Find locations within a geographical radius."""

    locations = filter_by_planet(data, planet)

    locations["distance_km"] = locations.apply(
        lambda row: calculate_distance(
            latitude,
            longitude,
            row["latitude"],
            row["longitude"],
            planet
        ),
        axis=1
    )

    nearby = locations[
        locations["distance_km"] <= radius_km
    ]

    return nearby.sort_values("distance_km")


def generate_geojson(data, planet="Earth"):
    """Convert locations into GeoJSON map features."""

    locations = filter_by_planet(data, planet)

    features = []

    for _, row in locations.iterrows():

        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [
                    float(row["longitude"]),
                    float(row["latitude"])
                ]
            },
            "properties": {
                "location_id": row["location_id"],
                "location_name": row["location_name"],
                "planetary_body": row["planetary_body"],
                "data_source": row["data_source"]
            }
        }

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


if __name__ == "__main__":

    dataset = load_dataset(
        PROJECT_ROOT / "data" / "sample_locations.csv"
    )

    print("Geospatial engine started!")

    distance = calculate_distance(
        51.5074, -0.1278,
        64.8, -18.0
    )

    print(
        f"London to Iceland: {distance:.2f} km"
    )

    nearby = find_nearby_locations(
        dataset,
        latitude=51.5074,
        longitude=-0.1278,
        radius_km=3000,
        planet="Earth"
    )

    print("\nLocations within 3000 km of London:")

    print(
        nearby[
            ["location_name", "distance_km"]
        ].to_string(index=False)
    )

    geojson = generate_geojson(dataset)

    print(
        f"\nMap features generated: "
        f"{len(geojson['features'])}"
    )

    print("\nGeospatial engine test completed!")

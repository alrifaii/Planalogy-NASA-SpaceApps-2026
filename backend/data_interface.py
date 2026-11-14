
"""
Planeology - NASA Space Apps Challenge 2026

Module: Data Interface
Purpose: Load and validate planetary analogue datasets.
"""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_COLUMNS = [
    "location_id",
    "location_name",
    "planetary_body",
    "latitude",
    "longitude",
    "data_source"
]


def load_dataset(file_path):
    """Load a CSV dataset and validate its structure."""

    data = pd.read_csv(file_path)

    missing = [
        column for column in REQUIRED_COLUMNS
        if column not in data.columns
    ]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    if data["location_id"].duplicated().any():
        raise ValueError("Duplicate location IDs detected.")

    if not data["latitude"].between(-90, 90).all():
        raise ValueError("Invalid latitude detected.")

    if not data["longitude"].between(-180, 180).all():
        raise ValueError("Invalid longitude detected.")

    if not data["planetary_body"].isin(
        ["Earth", "Moon", "Mars"]
    ).all():
        raise ValueError("Unsupported planetary body.")

    return data


def filter_by_planet(data, planet):
    """Return locations belonging to a selected planet."""

    return data[
        data["planetary_body"].str.lower() == planet.lower()
    ].copy()


def get_location(data, location_id):
    """Retrieve a specific location using its ID."""

    result = data[data["location_id"] == location_id]

    if result.empty:
        raise ValueError(f"Location {location_id} not found.")

    return result.iloc[0].to_dict()


if __name__ == "__main__":

    file_path = PROJECT_ROOT / "data" / "sample_locations.csv"

    dataset = load_dataset(file_path)

    print("Dataset loaded successfully!")
    print(f"Total locations: {len(dataset)}")

    earth = filter_by_planet(dataset, "Earth")
    moon = filter_by_planet(dataset, "Moon")
    mars = filter_by_planet(dataset, "Mars")

    print(f"Earth locations: {len(earth)}")
    print(f"Moon locations: {len(moon)}")
    print(f"Mars locations: {len(mars)}")

    print("\nEarth analogue candidates:")
    print(earth[["location_id", "location_name"]])

    print("\nData interface test completed!")

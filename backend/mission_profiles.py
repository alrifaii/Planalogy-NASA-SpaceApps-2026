
"""
Planalogy - NASA Space Apps Challenge 2026

Module: Mission Profiles
Purpose: Define environmental priorities for lunar
and Martian mission testing on Earth.
"""

MISSION_PROFILES = {

    "rover_testing": {
        "name": "Autonomous Rover Testing",
        "description": "Evaluate rover mobility and navigation.",
        "parameters": [
            "terrain_slope",
            "surface_roughness",
            "geology"
        ]
    },

    "habitat_construction": {
        "name": "Habitat Construction",
        "description": "Investigate habitat construction environments.",
        "parameters": [
            "terrain_slope",
            "geology",
            "temperature"
        ]
    },

    "isru": {
        "name": "In-Situ Resource Utilisation",
        "description": "Investigate local resource extraction.",
        "parameters": [
            "mineralogy",
            "water_ice_indicators",
            "geology"
        ]
    },

    "thermal_testing": {
        "name": "Thermal Systems Testing",
        "description": "Evaluate thermal management technologies.",
        "parameters": [
            "temperature",
            "temperature_variability"
        ]
    },

    "astronaut_training": {
        "name": "Astronaut Training",
        "description": "Evaluate operational procedures.",
        "parameters": [
            "terrain_slope",
            "isolation",
            "accessibility"
        ]
    }
}


def get_mission_profile(mission_type):
    """Return the selected mission profile."""
    return MISSION_PROFILES.get(mission_type)


if __name__ == "__main__":
    for profile in MISSION_PROFILES.values():
        print(profile["name"])

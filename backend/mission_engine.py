
"""
Planeology - NASA Space Apps Challenge 2026

Module: Mission Intelligence Engine
Purpose: Interpret environmental similarity scores
and generate mission-specific recommendations.
"""
import pandas as pd
import math

from backend.mission_profiles import get_mission_profile


MISSION_APPLICATIONS = {

    "rover_testing":
        "Mobility, navigation and obstacle avoidance testing.",

    "habitat_construction":
        "Excavation, foundation and construction experiments.",

    "isru":
        "Resource extraction and material processing experiments.",

    "thermal_testing":
        "Thermal management and environmental exposure testing.",

    "astronaut_training":
        "Exploration procedures and operational training."
}


def classify_similarity(score):
    """Classify a similarity score between 0 and 100."""

    if not math.isfinite(score) or not 0 <= score <= 100:
        raise ValueError("Score must be between 0 and 100.")

    if score >= 80:
        return "High similarity"

    elif score >= 60:
        return "Moderate similarity"

    elif score >= 40:
        return "Low similarity"

    else:
        return "Very low similarity"


def assess_data_coverage(location, mission_type):
    """Check which mission parameters are available."""

    profile = get_mission_profile(mission_type)

    if profile is None:
        raise ValueError("Unknown mission type.")

    required = profile["parameters"]

    available = [
        parameter for parameter in required
        if parameter in location
        and pd.notna(location[parameter])
    ]

    missing = [
        parameter for parameter in required
        if parameter not in available
    ]

    coverage = len(available) / len(required) * 100

    return {
        "available_parameters": available,
        "missing_parameters": missing,
        "coverage_percent": round(coverage, 2)
    }


def generate_recommendation(
    location,
    mission_type,
    similarity_score
):
    """Generate a preliminary mission recommendation."""

    profile = get_mission_profile(mission_type)

    if profile is None:
        raise ValueError("Unknown mission type.")

    classification = classify_similarity(
        similarity_score
    )

    coverage = assess_data_coverage(
        location,
        mission_type
    )

    return {
        "location": location["location_name"],
        "mission": profile["name"],
        "similarity_score": similarity_score,
        "classification": classification,
        "potential_application":
            MISSION_APPLICATIONS[mission_type],
        "data_coverage": coverage,
        "data_source": location.get(
            "data_source", "Unknown"
        ),
        "status": "Preliminary - requires validation"
    }


if __name__ == "__main__":

    sample_location = {
        "location_name": "Atacama Desert",
        "terrain_slope": 8,
        "surface_roughness": 0.35,
        "temperature": 290,
        "data_source": "SYNTHETIC"
    }

    result = generate_recommendation(
        location=sample_location,
        mission_type="rover_testing",
        similarity_score=85
    )

    print("Mission Intelligence Engine started!")

    for key, value in result.items():
        print(f"{key}: {value}")

    print("\nMission engine test completed!")

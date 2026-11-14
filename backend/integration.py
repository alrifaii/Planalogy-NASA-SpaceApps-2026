
"""
Planeology - NASA Space Apps Challenge 2026

Module: Integration
Purpose: Connect scientific datasets, geospatial
functions and mission intelligence into one interface.
"""

import json

from backend.data_interface import (
    load_dataset,
    filter_by_planet,
    get_location,
    PROJECT_ROOT
)

from backend.geospatial import generate_geojson

from backend.mission_engine import (
    generate_recommendation
)


def run_assessment(
    target_id,
    mission_type,
    similarity_scores,
    dataset_path=None,
    score_source="SYNTHETIC"
):
    """Generate assessments for Earth analogue candidates."""

    if dataset_path is None:
        dataset_path = (
            PROJECT_ROOT / "data" / "sample_locations.csv"
        )

    dataset = load_dataset(dataset_path)

    target = get_location(dataset, target_id)

    if target["planetary_body"] not in ["Moon", "Mars"]:
        raise ValueError("Target must be on the Moon or Mars.")

    earth_locations = filter_by_planet(dataset, "Earth")

    recommendations = []

    for _, row in earth_locations.iterrows():

        location = row.to_dict()

        location_id = location["location_id"]

        if location_id not in similarity_scores:
            continue

        score = float(similarity_scores[location_id])

        assessment = generate_recommendation(
            location=location,
            mission_type=mission_type,
            similarity_score=score
        )

        assessment["location_id"] = location_id
        assessment["latitude"] = float(location["latitude"])
        assessment["longitude"] = float(location["longitude"])

        recommendations.append(assessment)

    recommendations.sort(
        key=lambda item: item["similarity_score"],
        reverse=True
    )

    return {
        "project": "Planeology",
        "target_location": target["location_name"],
        "target_body": target["planetary_body"],
        "target_data_source": target["data_source"],
        "mission_type": mission_type,
        "score_source": score_source,
        "candidate_count": len(earth_locations),
        "assessed_count": len(recommendations),
        "recommendations": recommendations,
        "map_data": generate_geojson(dataset, "Earth"),
        "validation_status": "Preliminary"
    }


def export_results(results, output_path):
    """Export assessment results for frontend integration."""

    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(
            results,
            file,
            indent=4,
            allow_nan=False
        )


if __name__ == "__main__":

    # Temporary scores for software testing only.
    # Daniel's mathematical model will replace these.

    demo_scores = {
        "E001": 85,
        "E002": 78,
        "E003": 92
    }

    results = run_assessment(
        target_id="L001",
        mission_type="rover_testing",
        similarity_scores=demo_scores
    )

    print("Planeology Integration Engine started!")

    print(f"\nTarget: {results['target_location']}")
    print(f"Planetary body: {results['target_body']}")
    print(f"Mission: {results['mission_type']}")
    print(f"Score source: {results['score_source']}")

    print("\nRanked Earth analogue candidates:")

    for rank, item in enumerate(
        results["recommendations"], start=1
    ):

        print(
            f"{rank}. {item['location']} - "
            f"{item['similarity_score']}%"
        )

    output_path = (
        PROJECT_ROOT / "data" / "assessment_results.json"
    )

    export_results(results, output_path)

    print(f"\nResults exported to: {output_path}")
    print("\nIntegration test completed!")

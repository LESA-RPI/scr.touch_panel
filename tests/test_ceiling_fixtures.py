"""The quiet fixture layer retains the source's tile-level annotations."""

import json
from pathlib import Path


def test_fixture_positions_and_provenance_match_verified_annotations():
    data = json.loads(
        (Path(__file__).resolve().parents[1] / "app" / "ceiling_map.json").read_text(
            encoding="utf-8"
        )
    )
    expected = {
        "troffer": ("Light troffers", [
            (7, 2, 4), (8, 2, 2), (9, 6, 4), (10, 6, 2),
            (11, 9, 4), (12, 9, 2), (13, 13, 4), (14, 13, 2),
            (15, 4, 3), (16, 11, 3),
        ]),
        "hvac": ("HVAC vents", [
            (1, 4, 4), (2, 4, 2), (3, 8, 4),
            (4, 8, 2), (5, 11, 4), (6, 11, 2),
        ]),
        "sprinkler": ("Sprinklers", [
            (17, 1, 1), (18, 14, 1), (19, 1, 5),
            (20, 14, 5), (21, 8, 1), (22, 8, 5),
        ]),
    }
    assert [group["kind"] for group in data["fixtures"]] == list(expected)
    for group in data["fixtures"]:
        label, points = expected[group["kind"]]
        assert group["label"] == label
        assert group["positions"] == [
            {"cell": [column, row], "u": 0.5, "v": 0.5,
             "reference_id": "FIXTURE-%03d" % reference}
            for reference, column, row in points
        ]
    assert data["fixtures_source"] == {
        "repository": "Project-X-Ceiling",
        "path": "data/field-map/ceiling_field_map.yaml",
        "sha256": "89dd5512aed1bd3127926e067d4762875cec1397265db6e0936c1a73b733790c",
        "updated": "2026-10-24T22:29:06Z",
        "note": "Tile-level annotations; symbols do not represent measured footprints or live status.",
    }
    assert [(family["id"], len(family["positions"])) for family in data["families"]] == [
        ("color", 53), ("combo", 40), ("irma", 18)
    ]
    sensor_ids = [point["reference_id"]
                  for family in data["families"] for point in family["positions"]]
    assert len(set(sensor_ids)) == 111
    assert data["source"]["sha256"] == "3043c19b74a23d817c5b0c11221879815ca9dbdb324855017ea837b681e16f77"

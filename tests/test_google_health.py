from datetime import date

import pytest

from google_health_training_mcp.google_health import (
    civil_filter,
    daily_filter,
    date_range,
    downsample_evenly,
    heart_rate_statistics,
    physical_sample_filter,
    sleep_filter,
    summarize_workout,
)
from google_health_training_mcp.normalization import duration_seconds, normalize_workout


def test_date_range_is_inclusive() -> None:
    start, end = date_range("2026-08-01", "2026-08-31", default_days=30)
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 31)


def test_invalid_date_range() -> None:
    with pytest.raises(ValueError, match="start_date"):
        date_range("2026-09-02", "2026-09-01", default_days=30)


def test_filters_use_correct_google_fields() -> None:
    target = date(2026, 9, 2)
    assert civil_filter("exercise", target, target) == (
        'exercise.interval.civil_start_time >= "2026-09-02" AND '
        'exercise.interval.civil_start_time < "2026-09-03"'
    )
    assert daily_filter("daily-heart-rate-variability", target).startswith(
        'daily_heart_rate_variability.date >= "2026-09-02"'
    )
    assert sleep_filter(target).startswith('sleep.interval.civil_end_time >= "2026-09-02"')
    assert physical_sample_filter("heart-rate", "a", "b") == (
        'heart_rate.sample_time.physical_time >= "a" AND '
        'heart_rate.sample_time.physical_time < "b"'
    )


def test_workout_summary() -> None:
    point = {
        "name": "users/u/dataTypes/exercise/dataPoints/run-1",
        "exercise": {
            "exerciseType": "RUNNING",
            "displayName": "Morning run",
            "interval": {"startTime": "2026-09-01T06:00:00Z", "endTime": "2026-09-01T06:30:00Z"},
            "activeDuration": "1800s",
            "metricsSummary": {
                "distanceMillimeters": 5000000,
                "steps": "6200",
                "averagePaceSecondsPerMeter": 0.36,
                "activeZoneMinutes": "45",
                "mobilityMetrics": {"avgCadenceStepsPerMinute": 164.5},
            },
            "splits": [{}, {}],
            "exerciseMetadata": {"hasGps": True},
        },
    }
    summary = summarize_workout(point)
    assert summary["id"] == "run-1"
    assert summary["workoutId"] == "run-1"
    assert summary["exerciseType"] == "RUNNING"
    assert summary["splitCount"] == 2
    assert summary["runningContinuityStatus"] == "unknown"
    assert summary["duration"] == {"elapsedSeconds": 1800, "activeSeconds": 1800}
    assert summary["distanceMeters"] == 5000
    assert summary["steps"] == 6200
    assert summary["averagePaceSecondsPerKm"] == 360
    assert summary["activeZoneMinutesAreIntensityWeighted"] is True
    assert summary["mobility"]["averageCadenceStepsPerMinute"] == 164.5
    assert summary["hasGps"] is True


def test_normalize_workout_supports_documented_splits_and_deduplicates_exact_events() -> None:
    point = {
        "name": "users/u/dataTypes/exercise/dataPoints/run-2",
        "exercise": {
            "interval": {
                "startTime": "2026-09-01T06:00:00Z",
                "endTime": "2026-09-01T06:30:00Z",
            },
            "splitSummaries": [
                {
                    "startTime": "2026-09-01T06:00:00Z",
                    "endTime": "2026-09-01T06:10:00Z",
                    "activeDuration": "590.5s",
                    "metricsSummary": {"distanceMillimeters": 1000000},
                }
            ],
            "exerciseEvents": [
                {"eventTime": "2026-09-01T06:30:00Z", "exerciseEventType": "STOP"},
                {"eventTime": "2026-09-01T06:30:00Z", "exerciseEventType": "STOP"},
                {"eventTime": "2026-09-01T06:30:00Z", "exerciseEventType": "PAUSE"},
            ],
        },
    }

    normalized = normalize_workout(point)

    assert normalized["workoutId"] == "run-2"
    assert normalized["splitCount"] == 1
    assert normalized["splits"][0]["duration"]["activeSeconds"] == 590.5
    assert normalized["splits"][0]["metrics"]["distanceMeters"] == 1000
    assert normalized["sourceEventCount"] == 3
    assert normalized["eventCount"] == 2
    assert normalized["duplicateEventCount"] == 1
    assert [event["eventType"] for event in normalized["events"]] == ["STOP", "PAUSE"]
    assert normalized["runningContinuity"] == {
        "status": "not_applicable",
        "longestContinuousRunSeconds": None,
        "longestContinuousRunMeters": None,
    }


def test_duration_seconds_accepts_protobuf_and_numeric_values() -> None:
    assert duration_seconds("1804s") == 1804
    assert duration_seconds("3.5s") == 3.5
    assert duration_seconds(12) == 12
    assert duration_seconds("invalid") is None


def test_downsample_preserves_ends() -> None:
    values = [{"n": n} for n in range(100)]
    result = downsample_evenly(values, 10)
    assert len(result) == 10
    assert result[0] == {"n": 0}
    assert result[-1] == {"n": 99}


def test_heart_rate_statistics() -> None:
    points = [
        {"heartRate": {"beatsPerMinute": "100"}},
        {"heartRate": {"beatsPerMinute": "140"}},
        {"heartRate": {"beatsPerMinute": "120"}},
    ]
    assert heart_rate_statistics(points) == {
        "sampleCount": 3,
        "minimumBpm": 100.0,
        "maximumBpm": 140.0,
        "averageBpm": 120.0,
    }

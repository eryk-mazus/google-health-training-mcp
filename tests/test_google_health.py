from datetime import date

import pytest

from pixel_health_mcp.google_health import (
    civil_filter,
    daily_filter,
    date_range,
    downsample_evenly,
    heart_rate_statistics,
    physical_sample_filter,
    sleep_filter,
    summarize_workout,
)


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
        'dailyHeartRateVariability.date >= "2026-09-02"'
    )
    assert sleep_filter(target).startswith('sleep.interval.civil_end_time >= "2026-09-02"')
    assert physical_sample_filter("heart-rate", "a", "b") == (
        'heartRate.sample_time.physical_time >= "a" AND '
        'heartRate.sample_time.physical_time < "b"'
    )


def test_workout_summary() -> None:
    point = {
        "name": "users/u/dataTypes/exercise/dataPoints/run-1",
        "exercise": {
            "exerciseType": "RUNNING",
            "displayName": "Morning run",
            "interval": {"startTime": "2026-09-01T06:00:00Z", "endTime": "2026-09-01T06:30:00Z"},
            "activeDuration": "1800s",
            "metricsSummary": {"distanceMillimeters": 5000000},
            "splitSummaries": [{}, {}],
            "exerciseMetadata": {"hasGps": True},
        },
    }
    summary = summarize_workout(point)
    assert summary["id"] == "run-1"
    assert summary["exerciseType"] == "RUNNING"
    assert summary["splitCount"] == 2
    assert summary["hasGps"] is True


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

from __future__ import annotations

from datetime import datetime
from typing import Any


def _number(value: object) -> int | float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def duration_seconds(value: object) -> int | float | None:
    if not isinstance(value, str) or not value.endswith("s"):
        return _number(value)
    return _number(value[:-1])


def elapsed_seconds(interval: dict[str, Any]) -> int | float | None:
    start_time = interval.get("startTime")
    end_time = interval.get("endTime")
    if not isinstance(start_time, str) or not isinstance(end_time, str):
        return None
    try:
        start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _number((end - start).total_seconds())


def normalize_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    distance_mm = _number(metrics.get("distanceMillimeters"))
    pace_seconds_per_meter = _number(metrics.get("averagePaceSecondsPerMeter"))
    speed_mm_per_second = _number(metrics.get("averageSpeedMillimetersPerSecond"))
    elevation_mm = _number(metrics.get("elevationGainMillimeters"))
    active_zone_minutes = _number(metrics.get("activeZoneMinutes"))
    mobility = metrics.get("mobilityMetrics", {})
    if not isinstance(mobility, dict):
        mobility = {}
    zones = metrics.get("heartRateZoneDurations", {})
    if not isinstance(zones, dict):
        zones = {}
    return {
        "caloriesKcal": _number(metrics.get("caloriesKcal")),
        "distanceMeters": distance_mm / 1000 if distance_mm is not None else None,
        "steps": _number(metrics.get("steps")),
        "averageHeartRateBeatsPerMinute": _number(
            metrics.get("averageHeartRateBeatsPerMinute")
        ),
        "activeZoneMinutes": active_zone_minutes,
        "activeZoneMinutesAreIntensityWeighted": (
            True if active_zone_minutes is not None else None
        ),
        "averageSpeedMetersPerSecond": (
            speed_mm_per_second / 1000 if speed_mm_per_second is not None else None
        ),
        "averagePaceSecondsPerKm": (
            pace_seconds_per_meter * 1000 if pace_seconds_per_meter is not None else None
        ),
        "elevationGainMeters": elevation_mm / 1000 if elevation_mm is not None else None,
        "runVo2Max": _number(metrics.get("runVo2Max")),
        "totalSwimLengths": _number(metrics.get("totalSwimLengths")),
        "heartRateZoneSeconds": {
            "light": duration_seconds(zones.get("lightTime")),
            "moderate": duration_seconds(zones.get("moderateTime")),
            "vigorous": duration_seconds(zones.get("vigorousTime")),
            "peak": duration_seconds(zones.get("peakTime")),
        },
        "mobility": {
            "averageGroundContactTimeSeconds": duration_seconds(
                mobility.get("avgGroundContactTimeDuration")
            ),
            "averageCadenceStepsPerMinute": _number(
                mobility.get("avgCadenceStepsPerMinute")
            ),
            "averageStrideLengthMeters": (
                value / 1000
                if (value := _number(mobility.get("avgStrideLengthMillimeters"))) is not None
                else None
            ),
            "averageVerticalOscillationMeters": (
                value / 1000
                if (value := _number(mobility.get("avgVerticalOscillationMillimeters")))
                is not None
                else None
            ),
            "averageVerticalRatio": _number(mobility.get("avgVerticalRatio")),
        },
    }


def _source_splits(exercise: dict[str, Any]) -> list[dict[str, Any]]:
    # Current Fitbit-backed responses use `splits`, while Google's documented
    # REST representation uses `splitSummaries`. Accept both without double-counting.
    empty: list[dict[str, Any]] = []
    for field in ("splits", "splitSummaries"):
        value = exercise.get(field)
        if isinstance(value, list):
            parsed = [item for item in value if isinstance(item, dict)]
            if parsed:
                return parsed
            empty = parsed
    return empty


def normalize_split(split: dict[str, Any], index: int) -> dict[str, Any]:
    interval = {
        "startTime": split.get("startTime"),
        "endTime": split.get("endTime"),
    }
    return {
        "index": index,
        "splitType": split.get("splitType"),
        "startTime": split.get("startTime"),
        "endTime": split.get("endTime"),
        "duration": {
            "elapsedSeconds": elapsed_seconds(interval),
            "activeSeconds": duration_seconds(split.get("activeDuration")),
        },
        "metrics": normalize_metrics(
            split.get("metricsSummary") or split.get("metrics") or {}
        ),
    }


def normalize_events(events: object) -> tuple[list[dict[str, Any]], int]:
    if not isinstance(events, list):
        return [], 0
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[object, object, object]] = set()
    source_count = 0
    for event in events:
        if not isinstance(event, dict):
            continue
        source_count += 1
        key = (
            event.get("eventTime"),
            event.get("eventUtcOffset"),
            event.get("exerciseEventType"),
        )
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "eventTime": event.get("eventTime"),
                "eventUtcOffset": event.get("eventUtcOffset"),
                "eventType": event.get("exerciseEventType"),
            }
        )
    return normalized, source_count


def normalize_workout(point: dict[str, Any]) -> dict[str, Any]:
    exercise = point.get("exercise", {})
    interval = exercise.get("interval", {})
    splits = _source_splits(exercise)
    events, source_event_count = normalize_events(exercise.get("exerciseEvents"))
    name = point.get("name", "")
    exercise_type = exercise.get("exerciseType")
    return {
        "workoutId": name.rsplit("/", 1)[-1] if name else None,
        "exerciseType": exercise_type,
        "displayName": exercise.get("displayName"),
        "startTime": interval.get("startTime"),
        "endTime": interval.get("endTime"),
        "duration": {
            "elapsedSeconds": elapsed_seconds(interval),
            "activeSeconds": duration_seconds(exercise.get("activeDuration")),
        },
        "metrics": normalize_metrics(exercise.get("metricsSummary", {})),
        "splitCount": len(splits),
        "splits": [
            normalize_split(split, index) for index, split in enumerate(splits, start=1)
        ],
        "eventCount": len(events),
        "sourceEventCount": source_event_count,
        "duplicateEventCount": source_event_count - len(events),
        "events": events,
        "runningContinuity": {
            "status": "unknown" if exercise_type == "RUNNING" else "not_applicable",
            "longestContinuousRunSeconds": None,
            "longestContinuousRunMeters": None,
        },
    }

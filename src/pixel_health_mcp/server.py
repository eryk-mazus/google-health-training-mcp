from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from pixel_health_mcp.auth import authentication_status
from pixel_health_mcp.config import Settings
from pixel_health_mcp.google_health import (
    GoogleHealthClient,
    civil_filter,
    daily_filter,
    date_range,
    downsample_evenly,
    heart_rate_statistics,
    parse_date,
    physical_sample_filter,
    sleep_filter,
    summarize_workout,
)


mcp = MCPServer(
    "Pixel Health",
    instructions=(
        "Read-only access to the user's personal Google Health training and recovery data. "
        "Never interpret these measurements as a medical diagnosis. Prefer summaries before "
        "requesting high-volume telemetry. GPS routes are intentionally not exposed."
    ),
)

READ_ONLY_TOOL = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=True,
)


def _client() -> GoogleHealthClient:
    return GoogleHealthClient(Settings.load())


@mcp.tool(annotations=READ_ONLY_TOOL)
def health_auth_status(verify_online: bool = False) -> dict[str, object]:
    """Check Google Health authentication without revealing credentials.

    Set verify_online=true to refresh an expired access token and prove that the stored
    refresh token still works.
    """
    return authentication_status(Settings.load(), verify_online=verify_online)


@mcp.tool(annotations=READ_ONLY_TOOL)
def list_workouts(
    start_date: str | None = None,
    end_date: str | None = None,
    exercise_type: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """List workout summaries in an inclusive date range.

    Dates use YYYY-MM-DD. The default is the most recent 30 days. exercise_type is an
    optional exact match such as RUNNING, WALKING, or BIKING.
    """
    if limit < 1 or limit > 500:
        raise ValueError("limit must be between 1 and 500")
    start, end = date_range(start_date, end_date, default_days=30)
    points = _client().list_data_points(
        "exercise",
        filter_expression=civil_filter("exercise", start, end),
        max_results=limit,
    )
    workouts = [summarize_workout(point) for point in points]
    if exercise_type:
        wanted = exercise_type.upper()
        workouts = [item for item in workouts if item.get("exerciseType") == wanted]
    return {
        "startDate": start.isoformat(),
        "endDate": end.isoformat(),
        "count": len(workouts),
        "workouts": workouts,
    }


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_workout(workout_id: str) -> dict[str, Any]:
    """Get one complete workout session, including summary metrics, events, laps, and splits."""
    return _client().get_data_point("exercise", workout_id)


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_workout_heart_rate(workout_id: str, max_samples: int = 300) -> dict[str, Any]:
    """Get heart-rate telemetry for a workout, evenly reduced to a safe response size.

    Returns statistics calculated from all fetched samples plus at most max_samples points.
    GPS coordinates are never returned.
    """
    if max_samples < 2 or max_samples > 1000:
        raise ValueError("max_samples must be between 2 and 1000")
    client = _client()
    workout = client.get_data_point("exercise", workout_id)
    interval = workout.get("exercise", {}).get("interval", {})
    start_time, end_time = interval.get("startTime"), interval.get("endTime")
    if not start_time or not end_time:
        raise ValueError("Workout has no physical start/end interval")
    points = client.list_data_points(
        "heart-rate",
        filter_expression=physical_sample_filter("heart-rate", start_time, end_time),
        max_results=10000,
    )
    return {
        "workoutId": workout_id.rsplit("/", 1)[-1],
        "startTime": start_time,
        "endTime": end_time,
        "statistics": heart_rate_statistics(points),
        "returnedSampleCount": min(len(points), max_samples),
        "samples": downsample_evenly(points, max_samples),
    }


@mcp.tool(annotations=READ_ONLY_TOOL)
def get_recovery_snapshot(target_date: str | None = None) -> dict[str, Any]:
    """Return sleep and daily recovery-related measurements for one calendar date.

    target_date uses YYYY-MM-DD and defaults to today. The result contains source data;
    it is not a medical assessment or a proprietary readiness score.
    """
    target = parse_date(target_date, name="target_date") if target_date else date.today()
    client = _client()
    data: dict[str, object] = {}
    errors: dict[str, str] = {}
    data_types = (
        "daily-heart-rate-variability",
        "daily-resting-heart-rate",
        "daily-respiratory-rate",
        "daily-oxygen-saturation",
        "daily-vo2-max",
    )
    for data_type in data_types:
        try:
            data[data_type] = client.list_data_points(
                data_type,
                filter_expression=daily_filter(data_type, target),
                max_results=25,
            )
        except Exception as exc:
            errors[data_type] = str(exc)
    try:
        data["sleep"] = client.list_data_points(
            "sleep", filter_expression=sleep_filter(target), max_results=25
        )
    except Exception as exc:
        errors["sleep"] = str(exc)
    return {"date": target.isoformat(), "data": data, "unavailable": errors}


def run() -> None:
    mcp.run()

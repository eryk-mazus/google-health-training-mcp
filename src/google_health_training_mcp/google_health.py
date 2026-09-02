from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession

from google_health_training_mcp.auth import load_credentials
from google_health_training_mcp.config import Settings
from google_health_training_mcp.normalization import normalize_workout


BASE_URL = "https://health.googleapis.com/v4"


class GoogleHealthError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int,
        provider_status: str | None = None,
        reason: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_status = provider_status
        self.reason = reason


def parse_date(value: str, *, name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} must use YYYY-MM-DD format") from exc


def date_range(start_date: str | None, end_date: str | None, *, default_days: int) -> tuple[date, date]:
    end = parse_date(end_date, name="end_date") if end_date else date.today()
    start = parse_date(start_date, name="start_date") if start_date else end - timedelta(days=default_days - 1)
    if start > end:
        raise ValueError("start_date must be on or before end_date")
    if (end - start).days > 3660:
        raise ValueError("date range may not exceed 10 years")
    return start, end


def _filter_data_type(data_type: str) -> str:
    """Return the identifier used in Google Health filter expressions."""
    return data_type.replace("-", "_")


class GoogleHealthClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _session(self) -> AuthorizedSession:
        return AuthorizedSession(load_credentials(self.settings))

    def _request_json(self, method: str, path: str, *, params: dict[str, object] | None = None) -> dict[str, Any]:
        response = self._session().request(method, f"{BASE_URL}{path}", params=params, timeout=30)
        if not response.ok:
            provider_status: str | None = None
            reason: str | None = None
            try:
                payload = response.json()
                error = payload.get("error", {}) if isinstance(payload, dict) else {}
                if not isinstance(error, dict):
                    error = {}
                message = error.get("message") or response.reason
                status = error.get("status")
                provider_status = str(status) if status else None
                for detail in error.get("details") or []:
                    if isinstance(detail, dict) and detail.get("reason"):
                        reason = str(detail["reason"])
                        break
            except ValueError:
                message = response.reason
            raise GoogleHealthError(
                f"Google Health API returned HTTP {response.status_code}: {message}",
                status_code=response.status_code,
                provider_status=provider_status,
                reason=reason,
            )
        return response.json()

    def list_data_points(
        self,
        data_type: str,
        *,
        filter_expression: str,
        max_results: int = 1000,
    ) -> list[dict[str, Any]]:
        if max_results < 1 or max_results > 10000:
            raise ValueError("max_results must be between 1 and 10000")
        page_limit = 25 if data_type in {"exercise", "sleep"} else min(max_results, 10000)
        result: list[dict[str, Any]] = []
        page_token: str | None = None
        while len(result) < max_results:
            params: dict[str, object] = {
                "filter": filter_expression,
                "pageSize": min(page_limit, max_results - len(result)),
            }
            if page_token:
                params["pageToken"] = page_token
            payload = self._request_json(
                "GET", f"/users/me/dataTypes/{quote(data_type, safe='')}/dataPoints", params=params
            )
            result.extend(payload.get("dataPoints", []))
            page_token = payload.get("nextPageToken")
            if not page_token:
                break
        return result[:max_results]

    def get_data_point(self, data_type: str, data_point_id: str) -> dict[str, Any]:
        clean_id = data_point_id.rsplit("/", 1)[-1]
        return self._request_json(
            "GET",
            f"/users/me/dataTypes/{quote(data_type, safe='')}/dataPoints/{quote(clean_id, safe='')}",
        )


def civil_filter(data_type: str, start: date, end_inclusive: date) -> str:
    field = f"{_filter_data_type(data_type)}.interval.civil_start_time"
    end_exclusive = end_inclusive + timedelta(days=1)
    return f'{field} >= "{start.isoformat()}" AND {field} < "{end_exclusive.isoformat()}"'


def daily_filter(data_type: str, target: date) -> str:
    field = f"{_filter_data_type(data_type)}.date"
    return f'{field} >= "{target.isoformat()}" AND {field} < "{(target + timedelta(days=1)).isoformat()}"'


def sleep_filter(target: date) -> str:
    field = "sleep.interval.civil_end_time"
    return f'{field} >= "{target.isoformat()}" AND {field} < "{(target + timedelta(days=1)).isoformat()}"'


def physical_sample_filter(data_type: str, start_time: str, end_time: str) -> str:
    field = f"{_filter_data_type(data_type)}.sample_time.physical_time"
    return f'{field} >= "{start_time}" AND {field} < "{end_time}"'


def summarize_workout(point: dict[str, Any]) -> dict[str, Any]:
    exercise = point.get("exercise", {})
    interval = exercise.get("interval", {})
    metrics = exercise.get("metricsSummary", {})
    name = point.get("name", "")
    normalized = normalize_workout(point)
    return {
        "id": normalized["workoutId"],
        "workoutId": normalized["workoutId"],
        "name": name or None,
        "exerciseType": exercise.get("exerciseType"),
        "displayName": exercise.get("displayName"),
        "startTime": interval.get("startTime"),
        "endTime": interval.get("endTime"),
        "activeDuration": exercise.get("activeDuration"),
        "metrics": metrics,
        "splitCount": normalized["splitCount"],
        "runningContinuityStatus": normalized["runningContinuity"]["status"],
        "hasGps": exercise.get("exerciseMetadata", {}).get("hasGps", False),
        "dataSource": point.get("dataSource"),
        "duration": normalized["duration"],
        **normalized["metrics"],
    }


def downsample_evenly(values: list[dict[str, Any]], maximum: int) -> list[dict[str, Any]]:
    if maximum < 1:
        raise ValueError("maximum must be positive")
    if len(values) <= maximum:
        return values
    if maximum == 1:
        return [values[0]]
    indices = [round(i * (len(values) - 1) / (maximum - 1)) for i in range(maximum)]
    return [values[index] for index in indices]


def heart_rate_statistics(points: list[dict[str, Any]]) -> dict[str, float | int | None]:
    samples: list[float] = []
    for point in points:
        value = point.get("heartRate", {}).get("beatsPerMinute")
        if value is not None:
            try:
                samples.append(float(value))
            except (TypeError, ValueError):
                continue
    if not samples:
        return {"sampleCount": 0, "minimumBpm": None, "maximumBpm": None, "averageBpm": None}
    return {
        "sampleCount": len(samples),
        "minimumBpm": min(samples),
        "maximumBpm": max(samples),
        "averageBpm": round(math.fsum(samples) / len(samples), 1),
    }

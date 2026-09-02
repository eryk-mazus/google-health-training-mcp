import anyio
from mcp import Client
import pytest

import google_health_training_mcp.server as server_module
from google_health_training_mcp.google_health import GoogleHealthError
from google_health_training_mcp.server import mcp


EXPECTED_TOOLS = {
    "health_auth_status",
    "list_workouts",
    "get_workout",
    "get_workout_heart_rate",
    "get_recovery_snapshot",
}


async def _discover_tools():
    async with Client(mcp) as client:
        return await client.list_tools()


def test_mcp_tool_discovery_and_safety_annotations() -> None:
    result = anyio.run(_discover_tools)
    tools = {tool.name: tool for tool in result.tools}

    assert set(tools) == EXPECTED_TOOLS
    for tool in tools.values():
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is True


class FakeRecoveryClient:
    def list_data_points(self, data_type, *, filter_expression, max_results):
        assert max_results == 25
        if data_type == "daily-heart-rate-variability":
            raise GoogleHealthError(
                "sensitive provider message containing /local/private/path",
                status_code=400,
                provider_status="INVALID_ARGUMENT",
                reason="INVALID_DATA_POINT_FILTER",
            )
        if data_type == "sleep":
            return [{"sleep": {"marker": "recorded"}}]
        return []


def test_recovery_snapshot_reports_partial_results_without_raw_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server_module, "_client", FakeRecoveryClient)

    result = server_module.get_recovery_snapshot("2026-09-02")

    assert result["status"] == "partial"
    assert result["metrics"]["daily-heart-rate-variability"] == {
        "status": "provider_error",
        "records": [],
        "errorCode": "UNSUPPORTED_FILTER",
    }
    assert result["metrics"]["daily-resting-heart-rate"]["status"] == "no_data"
    assert result["metrics"]["sleep"]["status"] == "available"
    assert result["unavailable"] == {
        "daily-heart-rate-variability": "UNSUPPORTED_FILTER"
    }
    assert "/local/private/path" not in str(result)


def test_get_workout_adds_normalized_view_without_removing_source_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = {
        "name": "users/me/dataTypes/exercise/dataPoints/run-1",
        "exercise": {
            "exerciseType": "RUNNING",
            "activeDuration": "60s",
            "metricsSummary": {"distanceMillimeters": 250000},
            "splits": [],
        },
    }

    class FakeWorkoutClient:
        def get_data_point(self, data_type, workout_id):
            assert data_type == "exercise"
            assert workout_id == "run-1"
            return source

    monkeypatch.setattr(server_module, "_client", FakeWorkoutClient)

    result = server_module.get_workout("run-1")

    assert result["exercise"] is source["exercise"]
    assert result["workoutId"] == "run-1"
    assert result["normalized"]["workoutId"] == "run-1"
    assert result["normalized"]["metrics"]["distanceMeters"] == 250

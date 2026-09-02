import anyio
from mcp import Client

from pixel_health_mcp.server import mcp


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

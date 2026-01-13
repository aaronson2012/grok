import pytest
from src.services.tools import ToolRegistry

@pytest.fixture
def registry():
    return ToolRegistry()

@pytest.mark.asyncio
async def test_register_and_get_definitions(registry):
    async def sample_tool(arg1: str):
        return f"echo {arg1}"

    registry.register(
        name="sample_tool",
        description="A sample tool",
        parameters={"type": "object", "properties": {"arg1": {"type": "string"}}},
        func=sample_tool
    )

    definitions = registry.get_definitions()
    assert len(definitions) == 1
    assert definitions[0]["function"]["name"] == "sample_tool"
    assert definitions[0]["function"]["description"] == "A sample tool"

@pytest.mark.asyncio
async def test_execute_tool(registry):
    async def add_numbers(a: int, b: int):
        return a + b

    registry.register(
        name="add",
        description="Add two numbers",
        parameters={},
        func=add_numbers
    )

    result = await registry.execute("add", {"a": 5, "b": 3})
    assert result == "8"

@pytest.mark.asyncio
async def test_execute_unknown_tool(registry):
    with pytest.raises(ValueError, match="Tool 'unknown' not found"):
        await registry.execute("unknown", {})

@pytest.mark.asyncio
async def test_execute_tool_exception(registry):
    async def failing_tool():
        raise ValueError("Something went wrong")

    registry.register(
        name="fail",
        description="Fails",
        parameters={},
        func=failing_tool
    )

    result = await registry.execute("fail", {})
    assert "Tool execution failed" in result

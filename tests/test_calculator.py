import pytest
from src.utils.calculator import calculate
from src.services.tools import tool_registry

@pytest.mark.asyncio
async def test_calculator_tool_registration():
    tools = tool_registry.get_definitions()
    tool_names = [t["function"]["name"] for t in tools]
    assert "calculator" in tool_names

@pytest.mark.asyncio
async def test_calculator_execution():
    result = await tool_registry.execute("calculator", {"expression": "2 + 2"})
    assert result == "4"

def test_calculate_basic():
    assert calculate("2 + 2") == "4"
    assert calculate("10 - 5") == "5"
    assert calculate("3 * 4") == "12"
    assert calculate("10 / 2") == "5"

def test_calculate_advanced():
    assert calculate("2 ** 3") == "8"
    assert calculate("sqrt(16)") == "4"
    assert calculate("abs(-5)") == "5"
    assert calculate("pi") != "Error: Unknown variable or constant: pi"

def test_calculate_safety():
    assert "Error" in calculate("import os")
    assert "Error" in calculate("__import__('os')")
    assert "Error" in calculate("2 + 'a'")
    assert "Error" in calculate("2; 3") # Multiple statements not allowed

def test_calculate_float_formatting():
    assert calculate("1/3").startswith("0.333333")
    assert calculate("5.0") == "5"

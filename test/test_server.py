import pytest
from fastmcp import FastMCP

from tools import (
    register_be_tools,
    register_ch_tools,
    register_no_tools,
    register_pt_tools,
    register_uk_tools,
    register_vbb_tools,
)

ALL_PROVIDERS = [
    register_be_tools,
    register_ch_tools,
    register_no_tools,
    register_pt_tools,
    register_uk_tools,
    register_vbb_tools,
]


@pytest.mark.unit
async def test_all_tools_are_read_only():
    server = FastMCP("test-all")
    for register in ALL_PROVIDERS:
        register(server)

    tools = await server._list_tools()
    assert tools
    for tool in tools:
        assert tool.annotations is not None, tool.name
        assert tool.annotations.readOnlyHint is True, tool.name
        assert tool.annotations.openWorldHint is True, tool.name

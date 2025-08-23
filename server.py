"""
MCP Server for Public Transport Data (Multiple Countries)
Supports both STDIO (default) and HTTP-based transport (SSE or Streamable HTTP).
"""
import os
import argparse
import logging
from fastmcp import FastMCP
from tools.ch import register_ch_tools
from tools.uk import register_uk_tools
from tools.be import register_be_tools
from tools.no import register_no_tools
from config import SERVER_NAME

logger = logging.getLogger(__name__)

mcp = FastMCP(SERVER_NAME)

def main():
    parser = argparse.ArgumentParser(description="Run the Public Transport MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport method: stdio (default), sse, or http"
    )
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host to bind for HTTP/SSE transports")
    parser.add_argument("--port", type=int, default=8080, help="Port for HTTP/SSE transport")
    # Optional: default to '/mcp/' to avoid 307 redirects
    parser.add_argument("--path", type=str, default="/mcp/", help="Path for HTTP/SSE transport")
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level"
    )
    # Optional switch to force-disable UK tools
    parser.add_argument("--disable-uk", action="store_true", help="Disable UK tools even if keys are present")

    args = parser.parse_args()

    level_name = (args.log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Register tools (UK only if keys exist and not disabled)
    ch_tools = register_ch_tools(mcp)
    be_tools = register_be_tools(mcp)
    no_tools = register_no_tools(mcp)

    uk_app_id = os.getenv("UK_TRANSPORT_APP_ID")
    uk_api_key = os.getenv("UK_TRANSPORT_API_KEY")
    if not args.disable_uk and uk_app_id and uk_api_key:
        uk_tools = register_uk_tools(mcp)
    else:
        uk_tools = []
        if not args.disable_uk:
            logger.info("UK tools disabled: missing UK_TRANSPORT_APP_ID or UK_TRANSPORT_API_KEY")
        else:
            logger.info("UK tools disabled via --disable-uk")

    total = len(ch_tools) + len(uk_tools) + len(be_tools)
    logger.info(f"{SERVER_NAME} initialized with {total} tools "
                f"(CH: {len(ch_tools)}, NO: {len(no_tools)}, UK: {len(uk_tools)}, BE: {len(be_tools)})")

    # Start transport
    if args.transport == "stdio":
        logger.info("Starting MCP server on STDIO transport")
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        logger.info(f"Starting MCP server on SSE at http://{args.host}:{args.port}{args.path}")
        mcp.run(transport="sse", host=args.host, port=args.port, path=args.path)
    else:  # http (Streamable HTTP)
        logger.info(f"Starting MCP server on HTTP-Stream at http://{args.host}:{args.port}{args.path}")
        mcp.run(transport="http", host=args.host, port=args.port, path=args.path)

if __name__ == "__main__":
    main()

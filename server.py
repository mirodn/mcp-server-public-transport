"""
MCP Server for Public Transport Data (Multiple Countries)
Supports both STDIO (default) and HTTP-based transports (SSE or Streamable HTTP).
"""
import os
import argparse
import logging
from fastmcp import FastMCP
from tools.ch import register_ch_tools
from tools.uk import register_uk_tools
from tools.be import register_be_tools
from config import SERVER_NAME, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def main():
    # ——— CLI args —————————————————————————————————————————————
    parser = argparse.ArgumentParser(description="Run the Public Transport MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport method: stdio (default), sse, or http (Streamable HTTP)"
    )
    parser.add_argument("--host",     type=str, default="0.0.0.0", help="Host to bind for HTTP/SSE transports")
    parser.add_argument("--port",     type=int, default=8080,       help="Port for HTTP/SSE transport")
    parser.add_argument(
        "--path",
        type=str,
        default="/mcp",
        help="Path for HTTP/SSE transport (e.g. /mcp or /sse)"
    )
    args = parser.parse_args()

    # ——— Initialize MCP and register tools ——————————————————————
    mcp = FastMCP(SERVER_NAME)
    ch_tools = register_ch_tools(mcp)
    uk_tools = register_uk_tools(mcp)
    be_tools = register_be_tools(mcp)
    total = len(ch_tools) + len(uk_tools) + len(be_tools)
    logger.info(f"{SERVER_NAME} initialized with {total} tools "
                f"(CH: {len(ch_tools)}, UK: {len(uk_tools)}, BE: {len(be_tools)})")

    # ——— Choose and start transport —————————————————————————
    if args.transport == "stdio":
        logger.info("Starting MCP server on STDIO transport")
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        logger.info(f"Starting MCP server on SSE at http://{args.host}:{args.port}{args.path}")
        mcp.run(
            transport="sse",      # SSE transport (deprecated but supported) 
            host=args.host,
            port=args.port,
            path=args.path
        )
    else:  # args.transport == "http"
        logger.info(f"Starting MCP server on Streamable HTTP at http://{args.host}:{args.port}{args.path}")
        mcp.run(
            transport="http",     # Streamable HTTP transport (recommended) :contentReference[oaicite:0]{index=0}
            host=args.host,
            port=args.port,
            path=args.path
        )

if __name__ == "__main__":
    main()

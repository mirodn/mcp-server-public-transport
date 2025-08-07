"""
MCP Server for Public Transport Data (Multiple Countries)
"""
import logging
from fastmcp import FastMCP
from tools.ch import register_ch_tools
from tools.uk import register_uk_tools
from tools.be import register_be_tools
from config import SERVER_NAME, LOG_LEVEL

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP(SERVER_NAME)

def main():
    """Initialize and run the MCP server"""
    try:
        # Register country-specific transport tools
        ch_tools = register_ch_tools(mcp)
        uk_tools = register_uk_tools(mcp)
        be_tools = register_be_tools(mcp)
        
        total_tools = len(ch_tools) + len(uk_tools) + len(be_tools)
        logger.info(f" {SERVER_NAME} initialized with {total_tools} tools")
        logger.info(f"Swiss tools: {len(ch_tools)}")
        logger.info(f"UK tools: {len(uk_tools)}")
        logger.info(f"Belgium tools: {len(be_tools)}")
        
        # Start the server
        mcp.run()
        
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise

    if __name__ == "__main__":
        main()
"""
Configuration for MCP Public Transport Server
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Swiss Transport API (transport.opendata.ch)
CH_BASE_URL = "https://transport.opendata.ch/v1"

# UK Transport API (transportapi.com)
UK_BASE_URL = "https://transportapi.com/v3/uk"
# Note: UK_TRANSPORT_API_KEY and UK_TRANSPORT_APP_ID are read directly via os.getenv()
# in server.py and tools/uk.py to avoid duplicating environment variable lookups

# Belgium iRail API (docs.irail.be)
BE_BASE_URL = "https://api.irail.be"

# Server settings
SERVER_NAME = "MCP Public Transport Server"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

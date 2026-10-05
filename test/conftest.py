import sys
from pathlib import Path

# Make the repo root (server.py, config.py, core/, tools/) importable
root_path = Path(__file__).parent.parent
if str(root_path) not in sys.path:
    sys.path.insert(0, str(root_path))

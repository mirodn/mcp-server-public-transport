# test/conftest.py
import sys
from pathlib import Path

# Add src or tools to PYTHONPATH
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

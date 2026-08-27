import os
import sys
import tempfile

# Make the `src` package importable from the repository root
# so legacy tests (`from fusion import FusionEngine`) keep working.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

# Fast simulator ticks for API tests
os.environ.setdefault("SIM_INTERVAL", "0.1")

# No throttle on persistence during tests
os.environ.setdefault("DATA_THROTTLE", "0")

# Use a fresh, isolated data store per test session (do not touch data/)
_test_data_dir = tempfile.mkdtemp(prefix="arq_test_data_")
os.environ.setdefault("DATA_DB_PATH", os.path.join(_test_data_dir, "test.db"))
os.environ.setdefault("DATA_JSONL_PATH", os.path.join(_test_data_dir, "events.jsonl"))
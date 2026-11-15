"""Run backend tests from anywhere: python backend/run_tests.py"""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.exit(pytest.main(["-q", "-p", "no:cacheprovider", str(HERE / "tests")]))

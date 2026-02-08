"""Pytest configuration for Haven CLI tests.

This module handles mocking of optional dependencies that may not be available
in the test environment (e.g., libtorrent).
"""

import sys
from unittest.mock import MagicMock

# Mock libtorrent before any imports try to use it
sys.modules['libtorrent'] = MagicMock()

# Mock any other problematic imports
sys.modules['sklearn'] = MagicMock()
sys.modules['sklearn.metrics'] = MagicMock()

#!/bin/bash
# Setup script to add bundled libraries to LD_LIBRARY_PATH
# Run this before starting the backend if not using patchelf

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export LD_LIBRARY_PATH="${SCRIPT_DIR}/libs/usr/lib:${LD_LIBRARY_PATH}"
echo "LD_LIBRARY_PATH set to: $LD_LIBRARY_PATH"

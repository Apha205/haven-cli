# Task 7.3: Packaging

**Priority:** High
**Estimated Effort:** 1 day

**Description:**
Prepare distribution packages for release.

## PyPI Package

**Setup Configuration:**
```python
# pyproject.toml
[project]
name = "haven-tui"
version = "0.1.0"
description = "Terminal User Interface for Haven video archival pipeline"
readme = "README.md"
license = {text = "MIT"}
authors = [
    {name = "Haven Team", email = "team@haven.io"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Environment :: Console :: Curses",
    "Intended Audience :: End Users/Desktop",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.9",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Topic :: System :: Archiving",
]

[project.optional-dependencies]
tui = [
    "listpick >= 1.0.0",
    "plotille >= 4.0.0",
    "textual >= 0.40.0",
]
dev = [
    "pytest >= 7.0.0",
    "pytest-asyncio >= 0.21.0",
    "black >= 23.0.0",
    "mypy >= 1.0.0",
]

[project.scripts]
haven-tui = "haven_tui.app:main"

[project.entry-points."haven.plugins"]
tui = "haven_tui.app:TUIModule"
```

**Package Structure:**
```
src/
└── haven_tui/
    ├── __init__.py
    ├── __main__.py
    ├── app.py
    ├── config.py
    ├── data/
    │   ├── __init__.py
    │   ├── repositories.py
    │   ├── event_consumer.py
    │   └── state_manager.py
    ├── models/
    │   ├── __init__.py
    │   └── video_view.py
    ├── ui/
    │   ├── __init__.py
    │   ├── layout.py
    │   ├── components/
    │   └── views/
    └── utils/
        └── __init__.py
```

## Build & Publish

```bash
# Build package
python -m build

# Test upload to TestPyPI
python -m twine upload --repository testpypi dist/*

# Install from TestPyPI
pip install --index-url https://test.pypi.org/simple/ haven-tui

# Publish to PyPI
python -m twine upload dist/*
```

## Docker Image (Optional)

```dockerfile
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    libtorrent-rasterbar2.0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
RUN pip install ./src

ENTRYPOINT ["haven-tui"]
```

## Installation Scripts

**install.sh:**
```bash
#!/bin/bash
# Quick install script

set -e

echo "Installing Haven TUI..."

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python version: $python_version"

# Install via pip
pip3 install haven-tui

echo "Installation complete!"
echo "Run 'haven-tui' to start the application"
```

## Acceptance Criteria:
- [ ] PyPI package builds successfully
- [ ] Package installs cleanly
- [ ] All entry points work
- [ ] Docker image builds (optional)
- [ ] Installation script tested
- [ ] Package uploaded to PyPI

# libtorrent Installation Complete

The libtorrent package has been successfully installed and configured for Python 3.14.

## What Was Done

1. **Extracted System Libraries**: Extracted the libtorrent-rasterbar system package to `wheels/libs/usr/lib/` to provide the required shared libraries.

2. **Installed Python Wheel**: Installed the libtorrent Python wheel using `uv pip install`.

3. **Configured Library Path**: Modified `.venv/bin/activate` to automatically set `LD_LIBRARY_PATH` when the virtual environment is activated.

## Verification

The installation has been verified with the following tests:
- ✅ Import libtorrent module successfully
- ✅ Check libtorrent version (2.0.11.0)
- ✅ Create a libtorrent session successfully

## Usage

To use libtorrent in your Python code, simply activate the virtual environment:

```bash
source .venv/bin/activate
```

Then you can import and use libtorrent:

```python
import libtorrent

# Create a session
ses = libtorrent.session()

# Check version
print(f"libtorrent version: {libtorrent.version}")
```

## Library Path Configuration

The `LD_LIBRARY_PATH` is automatically set when you activate the virtual environment. It points to:
- `/home/tower/Documents/workspace/haven-cli/wheels/libs/usr/lib`
- `/home/tower/Documents/workspace/haven-cli/wheels/libs/usr/lib/x86_64-linux-gnu`

This ensures that the libtorrent shared libraries are found at runtime.

## Shared Libraries Available

The following shared libraries are now available:
- `libboost_python314.so.1.83.0`
- `libtorrent-rasterbar.so.2.0`
- `libtorrent-rasterbar.so.2.0.10`
- `libtorrent-rasterbar.so.2.0.11`

## Notes

- The system packages (`.deb` files) were not installed system-wide due to sudo requirements, but the libraries are available locally.
- The virtual environment activation script handles the library path automatically.
- This setup works for the current user and virtual environment without requiring system-wide installation.

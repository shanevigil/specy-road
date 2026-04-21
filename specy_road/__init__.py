"""specy-road package (CLI and shared helpers)."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("specy-road")
except PackageNotFoundError:
    # Editable/dev without metadata (e.g. partial PYTHONPATH)
    __version__ = "0.1.0rc4"

"""GENCON-style laytime, demurrage and despatch calculator.

The public surface is one pure function, ``compute_laytime``. It takes a
``basis`` mapping (charter-party terms plus one entry per port) and returns a
``result`` mapping. Nothing is read from or written to any external system, so
the same basis produces the same result whenever it is replayed.
"""

from .engine import compute_laytime

__all__ = ["compute_laytime", "__version__"]
__version__ = "0.1.0"

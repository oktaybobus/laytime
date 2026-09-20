"""GENCON-style laytime, demurrage and despatch calculator.

The public surface is one pure function, ``compute_laytime``. It takes a
``basis`` mapping (charter-party terms plus one entry per port) and returns a
``result`` mapping. Nothing is read from or written to any external system, so
the same basis produces the same result whenever it is replayed.
``excepted_intervals`` exposes the calendar the engine applies, for statements
that list the excepted periods.
"""

from .engine import compute_laytime, excepted_intervals

__all__ = ["compute_laytime", "excepted_intervals", "__version__"]
__version__ = "0.2.0"

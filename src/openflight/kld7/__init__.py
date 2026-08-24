"""K-LD7 angle radar integration module.

.. deprecated::
    The K-LD7 angle radars are deprecated — OpenFlight has moved to a more
    capable radar chip for angle measurement. This module is kept for
    existing builds but will not receive further development.
"""

from .tracker import KLD7Tracker
from .types import KLD7Angle, KLD7Frame

__all__ = ["KLD7Angle", "KLD7Frame", "KLD7Tracker"]

"""
Events of the current Fuji session that must be documented in the report.

No wx imports here, so it can be used from the acquisition code.
"""

from datetime import datetime
from typing import List

# Times at which a terminal was opened from Fuji (recovery only)
TERMINAL_OPENED: List[datetime] = []


def record_terminal_opened() -> datetime:
    now = datetime.now()
    TERMINAL_OPENED.append(now)
    return now

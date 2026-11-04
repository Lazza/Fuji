"""
Open a Terminal window from Fuji (meant for the recovery environment).
"""

import os
import subprocess
from typing import Tuple

TERMINAL_APP_PATHS = [
    "/System/Applications/Utilities/Terminal.app",
    "/Applications/Utilities/Terminal.app",
]


def open_terminal() -> Tuple[bool, str]:
    """Returns (success, error message)."""
    # Preferred: "open" brings up a new Terminal window
    try:
        p = subprocess.run(
            ["open", "-n", "-a", "Terminal"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if p.returncode == 0:
            return True, ""
        error = (p.stdout + p.stderr).strip()
    except Exception as e:
        error = str(e)

    # Fallback: start the Terminal binary directly (detached)
    for app in TERMINAL_APP_PATHS:
        binary = os.path.join(app, "Contents", "MacOS", "Terminal")
        if os.path.exists(binary):
            try:
                subprocess.Popen(
                    [binary],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return True, ""
            except Exception as e:
                error = str(e)

    return False, error or "Terminal not found"

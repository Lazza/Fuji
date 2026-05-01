"""
Check that the configured source is mounted read-only.

This is belt-and-braces verification: after the examiner has (hopefully)
unlocked the FileVault volume via the read-only path in shared.filevault,
this check confirms that the kernel-level mount flags on PARAMS.source
actually reflect a read-only mount before acquisition begins.

The check is intentionally strict: any uncertainty is treated as a failure,
on the principle that a false negative (wrongly flagging a read-only mount
as writable) is harmless, whereas a false positive would defeat the point
of the check.
"""

import os
import subprocess

from acquisition.abstract import Parameters
from checks.abstract import Check, CheckResult


class ReadOnlySourceCheck(Check):
    name = "Source read-only check"

    def _find_mount_line(self, mount_point: str) -> str:
        """Return the mount(8) line whose mount point matches, or ''."""
        try:
            out = subprocess.run(
                ["mount"], capture_output=True, check=True, text=True
            ).stdout
        except (subprocess.CalledProcessError, FileNotFoundError):
            return ""

        for line in out.splitlines():
            if f" on {mount_point} (" in line:
                return line
        return ""

    def _walk_to_mount(self, path: str) -> str:
        """Walk up from a path to the nearest mount point."""
        path = os.path.realpath(path)
        while path and not os.path.ismount(path):
            parent = os.path.dirname(path)
            if parent == path:
                break
            path = parent
        return path

    def execute(self, params: Parameters) -> CheckResult:
        result = CheckResult()

        source = f"{params.source}"
        if not source or source == "/":
            # The root filesystem case: in the live OS this is the running
            # system and this check is not meaningful. In Recovery, SOURCE_PATH
            # defaults to "/" only when auto-discovery failed and the user
            # hasn't yet selected anything.
            result.passed = True
            result.write("Source is the root filesystem; read-only check skipped.")
            return result

        mount_point = self._walk_to_mount(source)
        line = self._find_mount_line(mount_point)

        if not line:
            result.passed = False
            result.write(
                f"Could not determine mount flags for {mount_point}. "
                "Refusing to assume read-only."
            )
            return result

        flags = line.split("(", 1)[1].rstrip(") ").lower()
        tokens = [t.strip() for t in flags.split(",")]

        if "read-only" in tokens:
            result.passed = True
            result.write(f"Source mount {mount_point} is read-only.")
        else:
            result.passed = False
            result.write(
                f"Source mount {mount_point} is NOT read-only. "
                "Acquisition from a writable source risks altering evidence."
            )

        return result

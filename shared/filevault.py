"""
FileVault (APFS) discovery and read-only unlock helpers for Fuji.

This module is deliberately GUI-free so it can be unit tested and reasoned
about independently of wxPython.

Forensic design notes
---------------------
* The unlock is performed in two steps:
    1. ``diskutil apfs unlockVolume <id> -nomount -stdinpassphrase``
    2. ``diskutil mount readOnly <id>``
  The ``-nomount`` flag on step 1 is essential: without it, ``diskutil``
  auto-mounts the unlocked volume **read-write**, which would violate the
  forensic requirement that no writes reach the source disk.
* ``-stdinpassphrase`` is used so the password never appears in argv
  (argv is visible to any other process on the system via ``ps``).
* The password is passed to ``subprocess.run`` via ``input=`` and is never
  written to a temp file, logged, or printed to stdout/stderr.
* Python strings are immutable, so true zeroisation of the password in
  memory is not possible at the language level. Callers should drop their
  reference promptly; this module does the same.
* Nothing in this module invokes ``diskutil repairVolume``, ``fsck_apfs``,
  or any other command that could modify the source disk.
"""

import plistlib
import subprocess
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class EncryptedVolume:
    """A single APFS volume that is encrypted (possibly FileVault-protected)."""

    identifier: str          # e.g. "disk3s1" (no /dev/ prefix)
    name: str                # APFS volume name as reported by diskutil
    container: str           # e.g. "disk3"
    roles: List[str]         # e.g. ["Data"], ["System"], ["Preboot"], []
    filevault: bool          # True if FileVault is enabled on the volume
    locked: bool             # True if currently locked (needs unlock)
    mount_point: str = ""    # Current mount point, if any

    @property
    def is_user_data(self) -> bool:
        """Heuristic: this is the volume an examiner usually wants."""
        return "Data" in self.roles

    @property
    def display_status(self) -> str:
        """Short human-readable label for the device list UI."""
        if not self.filevault and not self.locked:
            return ""
        if self.locked:
            return "FileVault: Locked"
        return "FileVault: Unlocked"


def _diskutil_apfs_list() -> dict:
    """Run ``diskutil apfs list -plist`` and return the parsed plist."""
    result = subprocess.run(
        ["diskutil", "apfs", "list", "-plist"],
        capture_output=True,
        check=True,
    )
    return plistlib.loads(result.stdout)


def _diskutil_info(identifier: str) -> dict:
    """Run ``diskutil info -plist <identifier>`` and return the parsed plist."""
    result = subprocess.run(
        ["diskutil", "info", "-plist", identifier],
        capture_output=True,
        check=True,
    )
    return plistlib.loads(result.stdout)


def list_encrypted_volumes() -> List[EncryptedVolume]:
    """Return every APFS volume that is encrypted, whether locked or not.

    This is discovery only. It does not unlock anything, does not prompt for
    anything, and does not write to any disk.
    """
    volumes: List[EncryptedVolume] = []
    try:
        data = _diskutil_apfs_list()
    except (subprocess.CalledProcessError, FileNotFoundError, plistlib.InvalidFileException):
        return volumes

    for container in data.get("Containers", []):
        container_ref = container.get("ContainerReference", "")
        for vol in container.get("Volumes", []):
            # Only surface encrypted volumes. Unencrypted volumes are of no
            # interest to this module and are handled by the existing
            # DevicesWindow enumeration.
            encryption = bool(vol.get("Encryption", False))
            filevault = bool(vol.get("FileVault", False))
            if not (encryption or filevault):
                continue

            identifier = vol.get("DeviceIdentifier", "")
            if not identifier:
                continue

            locked = bool(vol.get("Locked", False))
            volumes.append(
                EncryptedVolume(
                    identifier=identifier,
                    name=vol.get("Name", "") or "",
                    container=container_ref,
                    roles=list(vol.get("Roles", []) or []),
                    filevault=filevault,
                    locked=locked,
                    mount_point=_current_mount_point(identifier),
                )
            )

    return volumes


def _current_mount_point(identifier: str) -> str:
    """Return the current mount point for a volume, or '' if not mounted."""
    try:
        info = _diskutil_info(identifier)
    except (subprocess.CalledProcessError, FileNotFoundError, plistlib.InvalidFileException):
        return ""
    return info.get("MountPoint", "") or ""


class UnlockError(Exception):
    """Raised when a FileVault unlock or read-only mount fails."""


def unlock_volume_readonly(identifier: str, password: str) -> str:
    """Unlock an APFS volume with FileVault and mount it read-only.

    Returns the mount point on success. Raises :class:`UnlockError` on failure.

    The password is sent to ``diskutil`` via stdin (``-stdinpassphrase``) so
    that it never appears in the process argument list. It is not written to
    any file, not logged, and not returned to the caller.
    """
    if not identifier:
        raise UnlockError("No volume identifier supplied.")
    if password is None:
        raise UnlockError("No password supplied.")

    # Step 1: unlock WITHOUT mounting. This prevents the default auto-mount,
    # which would otherwise be read-write.
    try:
        unlock = subprocess.run(
            [
                "diskutil",
                "apfs",
                "unlockVolume",
                identifier,
                "-nomount",
                "-stdinpassphrase",
            ],
            input=password.encode("utf-8"),
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UnlockError("diskutil is not available on this system.") from exc

    if unlock.returncode != 0:
        # Never surface raw stderr to the UI in case it contains the passphrase
        # echoed back in some edge case. Map return codes to a safe message.
        raise UnlockError(_classify_unlock_error(unlock.stderr, unlock.stdout))

    # Step 2: mount read-only. This is the only mount step; the source disk
    # is never mounted read-write by this code path.
    try:
        mount = subprocess.run(
            ["diskutil", "mount", "readOnly", identifier],
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise UnlockError("diskutil is not available on this system.") from exc

    if mount.returncode != 0:
        raise UnlockError(
            "Volume was unlocked but read-only mount failed. "
            "Refusing to fall back to a writable mount."
        )

    mount_point = _current_mount_point(identifier)
    if not mount_point:
        raise UnlockError(
            "Volume was unlocked and mount reported success, but no mount "
            "point could be determined."
        )

    if not verify_readonly(mount_point):
        # Defence in depth: if somehow the mount came up writable, refuse
        # silently succeeding. We leave the volume mounted so the examiner
        # can decide what to do, but we flag it as an error.
        raise UnlockError(
            f"Volume mounted at {mount_point} but is NOT read-only. "
            "Do not proceed with acquisition from this mount."
        )

    return mount_point


def _classify_unlock_error(stderr: bytes, stdout: bytes) -> str:
    """Return a safe, human-readable error message.

    We intentionally do not surface raw ``diskutil`` output to avoid any
    chance of leaking the passphrase in corner cases.
    """
    blob = (stderr + stdout).lower()
    if b"passphrase" in blob and (b"incorrect" in blob or b"wrong" in blob):
        return "Incorrect FileVault password."
    if b"not locked" in blob:
        return "Volume is not locked."
    if b"not encrypted" in blob or b"no crypto" in blob:
        return "Volume is not encrypted."
    if b"could not find" in blob or b"no such" in blob:
        return "Volume identifier not found."
    return "Unlock failed. Check the volume identifier and try again."


def verify_readonly(mount_point: str) -> bool:
    """Return True if the given mount point is mounted read-only.

    Parses the output of ``mount`` rather than relying on diskutil, because
    the kernel-level mount flags are what actually determine whether writes
    can happen.
    """
    if not mount_point:
        return False
    try:
        out = subprocess.run(
            ["mount"], capture_output=True, check=True, text=True
        ).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

    for line in out.splitlines():
        # Format: "/dev/diskXsY on /mount/point (apfs, local, read-only, ...)"
        if f" on {mount_point} (" not in line:
            continue
        flags = line.split("(", 1)[1].rstrip(") ").lower()
        tokens = [t.strip() for t in flags.split(",")]
        if "read-only" in tokens:
            return True
        return False

    return False

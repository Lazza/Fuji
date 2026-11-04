"""
Detection, unlocking and mounting of macOS data volumes.

Used in the recovery environment, where the data volume is often not mounted
yet, or still locked by FileVault. Without it, Fuji falls back to "/" (the
recovery system) as source.

No wx imports here, so it can be used from checks and from the UI.
"""

import plistlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

USER_TYPES = {
    "LocalOpenDirectory": "Local user",
    "PersonalRecovery": "Personal recovery key",
    "InstitutionalRecovery": "Institutional recovery key",
}


@dataclass
class DataVolume:
    identifier: str  # e.g. disk6s5
    name: str
    container: str
    filevault: bool
    locked: bool
    mount_point: str = ""

    @property
    def mounted(self) -> bool:
        return bool(self.mount_point)

    def state(self) -> str:
        if self.mounted:
            return f"mounted at {self.mount_point}"
        if self.locked:
            return "locked (FileVault)"
        return "not mounted"

    def label(self) -> str:
        return f"{self.name} ({self.identifier}) - {self.state()}"


@dataclass
class CryptoUser:
    uuid: str
    type: str

    def label(self) -> str:
        kind = USER_TYPES.get(self.type, self.type or "Unknown")
        return f"{kind} ({self.uuid[:8]}...)"


def _plist(arguments: List[str]) -> dict:
    try:
        p = subprocess.run(arguments, capture_output=True, timeout=60)
        if p.returncode != 0:
            return {}
        return plistlib.loads(p.stdout)
    except Exception:
        return {}


def _run(arguments: List[str], stdin: Optional[str] = None) -> Tuple[int, str]:
    try:
        p = subprocess.run(
            arguments,
            input=stdin,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return p.returncode, (p.stdout + p.stderr).strip()
    except Exception as e:
        return -1, str(e)


def mount_point(identifier: str) -> str:
    info = _plist(["diskutil", "info", "-plist", identifier])
    return info.get("MountPoint", "") or ""


def data_volumes() -> List[DataVolume]:
    """All APFS volumes with the "Data" role, mounted or not."""
    listing = _plist(["diskutil", "apfs", "list", "-plist"])
    result: List[DataVolume] = []

    for container in listing.get("Containers", []):
        for volume in container.get("Volumes", []):
            if "Data" not in volume.get("Roles", []):
                continue
            identifier = volume.get("DeviceIdentifier", "")
            if not identifier:
                continue

            filevault = bool(volume.get("FileVault", False))
            point = mount_point(identifier)
            # "Locked" is reported by diskutil; if missing, assume an unmounted
            # FileVault volume is locked (unlock handles "already unlocked").
            locked = bool(volume.get("Locked", filevault and not point))

            result.append(
                DataVolume(
                    identifier=identifier,
                    name=volume.get("Name", identifier),
                    container=container.get("ContainerReference", ""),
                    filevault=filevault,
                    locked=locked,
                    mount_point=point,
                )
            )

    return result


def crypto_users(identifier: str) -> List[CryptoUser]:
    """Users and keys that can unlock the volume (local users, recovery key)."""
    listing = _plist(["diskutil", "apfs", "listUsers", identifier, "-plist"])
    users: List[CryptoUser] = []
    for user in listing.get("Users", []):
        uuid = user.get("APFSCryptoUserUUID", "")
        kind = user.get("APFSCryptoUserType", "")
        # iCloud keys cannot be used with a passphrase here
        if uuid and not kind.startswith("iCloud"):
            users.append(CryptoUser(uuid=uuid, type=kind))
    return users


def mount(volume: DataVolume, read_only: bool = True) -> Tuple[bool, str, str]:
    """Mount an (unlocked) volume. Returns (success, message, mount point)."""
    command = ["diskutil", "mount"]
    if read_only:
        command.append("readOnly")
    command.append(volume.identifier)

    status, output = _run(command)
    point = mount_point(volume.identifier)
    if status == 0 and point:
        return True, output, point
    return False, output or "Mount failed", ""


def unlock(
    volume: DataVolume,
    passphrase: str,
    user_uuid: Optional[str] = None,
    read_only: bool = True,
) -> Tuple[bool, str, str]:
    """
    Unlock a FileVault volume and mount it.

    The passphrase is passed via stdin, so it never appears in the process
    list. Unlocking happens with -nomount, then the volume is mounted
    separately, read-only by default (recommended for forensic acquisition).

    Returns (success, message, mount point).
    """
    command = ["diskutil", "apfs", "unlockVolume", volume.identifier]
    if user_uuid:
        command.extend(["-user", user_uuid])
    command.extend(["-stdinpassphrase", "-nomount"])

    status, output = _run(command, stdin=passphrase)
    already_unlocked = "already unlocked" in output.lower()

    if status != 0 and not already_unlocked:
        return False, output or "Unlock failed", ""

    return mount(volume, read_only=read_only)


def contains(mount_path: str, path: Path) -> bool:
    base = Path(mount_path)
    return path == base or base in path.parents

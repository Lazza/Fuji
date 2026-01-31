import os

from .utils import command_to_properties


RECOVERY: bool = bool(os.getenv("__OSINSTALL_ENVIRONMENT", ""))
OS_ROOT: str = "/"
SOURCE_PATH: str = "/"

if RECOVERY:
    mount_lines = command_to_properties(["mount"], separator=" on ")
    sealed = [v.split("(")[0].strip() for v in mount_lines.values() if "sealed" in v]
    for path in sealed:
        canary_path = os.path.join(path, "usr/bin/rsync")
        if os.path.exists(canary_path):
            OS_ROOT = path
            OS_DATA = f"{path} - Data"
            if os.path.exists(OS_DATA):
                SOURCE_PATH = OS_DATA
            break

RSYNC_PATH: str = os.path.join(OS_ROOT, "usr/bin/rsync")
SLURP_PATH: str = os.path.join(
    OS_ROOT, "System/Library/Filesystems/apfs.fs/Contents/Resources/slurpAPFSMeta"
)

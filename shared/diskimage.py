"""
Abstraction over disk image tooling.

macOS 27 deprecates `hdiutil` in favour of `diskutil image`. This module picks
the right tool at runtime and builds the matching command lines, so the rest
of Fuji does not need to know which one is in use.

Strategy:
  - macOS < 27: keep the proven `hdiutil` path (no warnings there).
  - macOS >= 27 AND `diskutil image` is available: use `diskutil image`.
  - Override with FUJI_DISKIMAGE=hdiutil|diskutil for testing.

All `diskutil image` flags used here (create blank, create from, attach) are
verified against the macOS 27 help output.
"""

import functools
import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Tuple


@functools.lru_cache(maxsize=None)
def macos_version() -> Tuple[int, ...]:
    # sw_vers reads the real system version. platform.mac_ver() may report a
    # compatibility version (e.g. 16.0) for binaries linked against old SDKs.
    try:
        out = subprocess.check_output(
            ["sw_vers", "-productVersion"], universal_newlines=True
        ).strip()
        return tuple(int(p) for p in out.split(".") if p.isdigit())
    except Exception:
        return (0,)


def macos_version_string() -> str:
    return ".".join(str(p) for p in macos_version())


@functools.lru_cache(maxsize=None)
def _diskutil_image_available() -> bool:
    try:
        p = subprocess.run(
            ["diskutil", "image", "--help"], capture_output=True, timeout=10
        )
        return p.returncode == 0
    except Exception:
        return False


@functools.lru_cache(maxsize=None)
def use_diskutil_image() -> bool:
    override = os.getenv("FUJI_DISKIMAGE", "").lower()
    if override == "hdiutil":
        return False
    if override == "diskutil":
        return _diskutil_image_available()
    return macos_version() >= (27,) and _diskutil_image_available()


def tool_name() -> str:
    return "diskutil image" if use_diskutil_image() else "hdiutil"


# --- Temporary (writable, sparse) image ---------------------------------------


def sparse_extension() -> str:
    # `diskutil image create blank` supports RAW, ASIF and UDSB, but not the old
    # single-file UDSP ".sparseimage". UDSB (sparsebundle) works on any
    # destination filesystem (exFAT, HFS+, APFS), unlike ASIF.
    return ".sparsebundle" if use_diskutil_image() else ".sparseimage"


def create_sparse_command(
    path: Path, size_bytes: int, filesystem: str, volume_name: str
) -> List[str]:
    if use_diskutil_image():
        # --size is in bytes by default (rounded to the sector size).
        # --fs only supports APFS / ExFAT / MS-DOS / None, so HFS+ is mapped
        # to APFS. That is fine for Rsync, Ditto and ASR (ASR erases the
        # target anyway). APFS keeps xattrs, ACLs and nanosecond timestamps.
        return [
            "diskutil",
            "image",
            "create",
            "blank",
            "--format",
            "UDSB",
            "--fs",
            "APFS",
            "--size",
            f"{size_bytes}",
            "--volumeName",
            volume_name,
            f"{path}",
        ]
    sectors = -(-size_bytes // 512)
    return [
        "hdiutil",
        "create",
        "-sectors",
        f"{sectors}",
        "-fs",
        filesystem,
        "-volname",
        volume_name,
        f"{path}",
    ]


def attach_command(path: Path) -> List[str]:
    # Output format (one "/dev/diskN ... [mount point]" line per device) is the
    # same for both tools, so the existing parser keeps working.
    if use_diskutil_image():
        return ["diskutil", "image", "attach", f"{path}"]
    return ["hdiutil", "attach", f"{path}"]


def ramdisk_attach_command(sectors: int) -> List[str]:
    # Both tools accept ram://<sector count> (512-byte sectors). With
    # diskutil image, RAM disks default to mountPolicy=noMount, which matches
    # hdiutil's -nomount; --noMount is passed explicitly anyway.
    if use_diskutil_image():
        return ["diskutil", "image", "attach", "--noMount", f"ram://{sectors}"]
    return ["hdiutil", "attach", "-nomount", f"ram://{sectors}"]


def detach_volume_command(volume_device: str) -> List[str]:
    # First, gentle step (retried by the caller while the volume is busy).
    if use_diskutil_image():
        return ["diskutil", "unmount", volume_device]
    return ["hdiutil", "detach", volume_device]


def detach_container_command(container_device: str) -> List[str]:
    # Second step: release the whole image. `diskutil image` has no detach,
    # the replacement is the top-level `diskutil eject`.
    if use_diskutil_image():
        return ["diskutil", "eject", container_device]
    return ["hdiutil", "detach", "-force", container_device]


def convert_command(source: Path, destination: Path, fmt: str = "UDZO") -> List[str]:
    if use_diskutil_image():
        # Format is passed explicitly: the default would be ULFO (LZFSE),
        # which many non-Apple forensic tools cannot read. UDZO (zlib) keeps
        # the output identical in format to the hdiutil path.
        return [
            "diskutil",
            "image",
            "create",
            "from",
            "--format",
            fmt,
            f"{source}",
            f"{destination}",
        ]
    return ["hdiutil", "convert", f"{source}", "-format", fmt, "-o", f"{destination}"]


def remove_image(path: Path) -> None:
    # A .sparsebundle is a directory, Path.unlink() would fail on it.
    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except Exception as e:
        print(f"Could not remove {path}: {e}")


def first_device(output: str) -> str:
    # Robustly pick the device node from attach output, ignoring any
    # deprecation warning lines printed by the tool.
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("/dev/disk"):
            return line.split()[0]
    return ""

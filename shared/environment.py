import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List
import wx.lib.agw.hyperlink as hl

from meta import RAMDISK_NAME, VOLUME_NAME

from .utils import command_to_properties

RECOVERY: bool = bool(os.getenv("__OSINSTALL_ENVIRONMENT", ""))
OS_ROOT: str = "/"
SOURCE_PATH: str = "/"

if RECOVERY:
    mount_lines = command_to_properties(["mount"], separator=" on ")
    candidates: List[str] = [
        v.split("(")[0].strip()
        for v in mount_lines.values()
        if "apfs" in v.split("(")[1]
    ]
    # Find the OS_ROOT first
    for path in candidates:
        canary_path = os.path.join(path, "usr/bin/rsync")
        data_canary_path = os.path.join(path, ".fseventsd")
        if os.path.exists(canary_path) and not os.path.exists(data_canary_path):
            OS_ROOT = path
            break
    # Then find the data volume
    for path in candidates:
        data_canary_path = os.path.join(path, ".fseventsd")
        if path.startswith(OS_ROOT) and os.path.exists(data_canary_path):
            SOURCE_PATH = path
            break
else:
    data_path = "/System/Volumes/Data"
    data_canary_path = os.path.join(data_path, ".fseventsd")
    if os.path.exists(data_canary_path):
        SOURCE_PATH = data_path

RSYNC_PATH: str = os.path.join(OS_ROOT, "usr/bin/rsync")
SLURP_PATH: str = os.path.join(
    OS_ROOT, "System/Library/Filesystems/apfs.fs/Contents/Resources/slurpAPFSMeta"
)


def current_volume() -> str:
    if getattr(sys, "frozen", False):
        # If the application is run as a bundle, the PyInstaller bootloader
        # extends the sys module by a flag frozen=True and sets the app
        # path into variable _MEIPASS'.
        application_path = Path(sys._MEIPASS)  # type: ignore
    else:
        application_path = Path(__file__).absolute().parent

    print(application_path)
    components = application_path.parts
    if components[1] != "Volumes":
        return ""
    return components[2]


def attempt_ramdisk() -> None:
    volume = current_volume()
    if volume.startswith(RAMDISK_NAME):
        return

    # Exit if the volume is not recognized
    if not volume.startswith(VOLUME_NAME):
        return

    print("Attempting to create and switch to RAM disk...")
    # Clone the contents of the volume to a RAM disk (256 MB)
    sectors = 256 * 1024 * 1024 // 512
    try:
        attach_result = subprocess.run(
            ["hdiutil", "attach", "-nomount", f"ram://{sectors}"],
            capture_output=True,
            text=True,
            check=True,
        )
        ramdisk_device = attach_result.stdout.strip()

        # Format the RAM disk
        subprocess.run(
            ["diskutil", "erasevolume", "HFS+", RAMDISK_NAME, ramdisk_device],
            check=True,
        )

        # Find the mount point of the RAM disk
        mount_lines = command_to_properties(["mount"], separator=" on ")
        ramdisk = None
        for mount_path, description in mount_lines.items():
            if RAMDISK_NAME in description and ramdisk_device in mount_path:
                ramdisk = Path(description.split("(")[0].strip())
                break

        if not ramdisk:
            print("Error: RAM disk mount point not found.")
            return  # Abort the RAM disk attempt

        source_fujiapp = Path("/Volumes") / volume

        # Copy contents
        print(f"Copying from {source_fujiapp} to {ramdisk}...")
        subprocess.run(["ditto", source_fujiapp, ramdisk], check=True)

        # Determine the new executable path
        ramdisk_executable = ramdisk / "Fuji.app" / "Contents" / "MacOS" / "Fuji"

        # Detach the original volume and create symlink in a detached shell process after a delay
        quoted_source_fujiapp = shlex.quote(source_fujiapp.as_posix())
        quoted_ramdisk = shlex.quote(ramdisk.as_posix())

        shell_command = (
            f"sleep 2 && "  # Delay for 2 seconds
            f"hdiutil detach -force {quoted_source_fujiapp} && "  # Detach
            f"ln -s {quoted_ramdisk} {quoted_source_fujiapp}"  # Create symlink
        )

        subprocess.Popen(
            shell_command,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        # Start the new process from the RAM disk in a new session
        subprocess.Popen(
            ramdisk_executable,
            start_new_session=True,
        )

        # Exit the current process cleanly
        print("Switch to RAM disk successful. Exiting old process.")
        sys.exit(0)

    except (subprocess.CalledProcessError, FileNotFoundError):
        print("Aborting RAM disk attempt. Running from original location.")


class AdaptiveHyperLinkCtrl(hl.HyperLinkCtrl):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Apple Silicon macOS recovery
        safari_app = Path("/System/Cryptexes/App/System/Applications/Safari.app")
        containers = Path("/System/Volumes/Data/private/var/root/Library/Containers")

        # Intel-based macOS recovery
        if not safari_app.exists():
            safari_app = Path("/Applications/Safari.app")
            containers = Path("/private/var/root/Library/Containers")

        self.data_path = containers / "com.apple.Safari" / "Data"
        self.safari = safari_app / "Contents" / "MacOS" / "Safari"

        self.caches_path = self.data_path / "Library" / "Caches"
        self.html_name = "redirect.html"
        self.html_path = self.data_path / self.html_name
        self.override = RECOVERY and self.safari.exists()

    def GotoURL(self, URL, ReportErrors=True, NotSameWinIfPossible=False):
        if not self.override:
            return super().GotoURL(URL, ReportErrors, NotSameWinIfPossible)

        # Space can be very limited, clean temporary cache to be safe
        shutil.rmtree(self.caches_path, ignore_errors=True)

        # Leverage Safari's ability to open local HTML files to perform the
        # redirection, since we cannot pass a custom URL directly to it.
        html_content = f"""<!DOCTYPE html>
        <html>
        <head>
            <script>location.href = "{URL}";</script>
            <title>Redirect...</title>
        </head>
        <body>
        </body>
        </html>"""
        self.data_path.mkdir(parents=True, exist_ok=True)
        self.html_path.write_text(html_content)

        subprocess.Popen([self.safari, self.html_name])
        return True

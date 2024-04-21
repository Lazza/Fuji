import os
from pathlib import Path

# This will be called from the parent directory
project_directory = Path(os.getcwd())
dist_directory = project_directory / "dist"
pack_directory = project_directory / "packaging"

files = [
    str(pack_directory / "Full Disk Access Settings.url"),
    str(dist_directory / "Fuji.app"),
]
badge_icon = str(pack_directory / "Fuji.icns")

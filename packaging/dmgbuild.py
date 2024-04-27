import os
from pathlib import Path

# This will be called from the parent directory
project_directory = Path(os.getcwd())
dist_directory = project_directory / "dist"
pack_directory = project_directory / "packaging"

# File names
settings_file = "Full Disk Access Settings.url"
fuji_app_file = "Fuji.app"
license_file = "LICENSE.rtf"

files = [
    str(pack_directory / settings_file),
    str(dist_directory / fuji_app_file),
    str(pack_directory / license_file),
]
icon_locations = {
    settings_file: (128, 128),
    fuji_app_file: (320, 128),
    license_file: (512, 128),
}
badge_icon = str(pack_directory / "Fuji.icns")
left_bottom_coordinates = (200, 300)
width_height = (640, 480)
window_rect = (left_bottom_coordinates, width_height)

import os
from pathlib import Path

# This will be called from the parent directory
project_directory = Path(os.getcwd())
dist_directory = project_directory / "dist"
pack_directory = project_directory / "packaging"
recovery_directory = project_directory / "recovery"

# File names
settings_file = "Full Disk Access Settings.url"
fuji_app_file = "Fuji.app"
license_file = "LICENSE.rtf"
physical_media_file = ".IAPhysicalMedia"
start_file = "start.sh"

files = [
    str(pack_directory / settings_file),
    str(dist_directory / fuji_app_file),
    str(pack_directory / license_file),
    str(recovery_directory / physical_media_file),
    str(recovery_directory / start_file),
]
hide = [start_file]
icon_locations = {
    settings_file: (128, 128),
    fuji_app_file: (320, 128),
    license_file: (512, 128),
}
icon = str(pack_directory / "FujiApp.icns")
left_bottom_coordinates = (200, 300)
width_height = (640, 480)
window_rect = (left_bottom_coordinates, width_height)

# RW format for temporary DMG
format = "UDRW"
size = "200m"
shrink = False

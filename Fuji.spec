# -*- mode: python ; coding: utf-8 -*-

import importlib
import subprocess
import sys
from os import remove
from pathlib import Path
from shutil import copy, copytree, move

import dmgbuild

sys.path.insert(0, ".")
meta = importlib.import_module("meta")


a = Analysis( # type: ignore
    ["fuji.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure) # type: ignore

exe = EXE( # type: ignore
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Fuji",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch="universal2",
    codesign_identity=None,
    entitlements_file=None,
    icon=["packaging/Fuji.icns"],
)
coll = COLLECT( # type: ignore
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Fuji",
)
app = BUNDLE( # type: ignore
    coll,
    name="Fuji.app",
    icon="./packaging/Fuji.icns",
    bundle_identifier="com.andrealazzarotto.fuji",
    version=meta.VERSION,
)

# Add language file for recovery environment
app_bundle_path = Path("./dist/Fuji.app")
copytree("./recovery/en.lproj", app_bundle_path / "Contents" / "Resources" / "en.lproj")

executable_path = app_bundle_path / "Contents" / "MacOS"
move(executable_path / "Fuji", executable_path / "Fuji.bin")
copy("./packaging/Fuji.sh", executable_path / "Fuji")

dmg_path = f"./dist/FujiApp-{meta.VERSION}.dmg"
temp_dmg_path = f"./dist/FujiApp-{meta.VERSION}-temp.dmg"
volume_name = "FujiApp"

print("Building temporary DMG", temp_dmg_path)
try:
    dmgbuild.build_dmg(
        temp_dmg_path,
        volume_name,
        settings_file="packaging/dmgbuild.py",
    )
except Exception as e:
    print(e)
    print("DMG build failed")
    sys.exit(1)

print("Exporting final DMG", dmg_path)

# Attach temporary image and get mount point
attach_process = subprocess.Popen(
    [
        "hdiutil",
        "attach",
        "-nobrowse",
        "-noverify",
        "-noautoopen",
        "-owners",
        "off",
        temp_dmg_path,
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
stdout, stderr = attach_process.communicate()
if attach_process.returncode != 0:
    print("Failed to attach DMG:", stderr.decode().strip())
    sys.exit(1)

mount_point = None
for line in stdout.decode().splitlines():
    if f"/Volumes/{volume_name}" in line:
        mount_point = line.split("\t")[-1]
        break

# Make the mounted file system "read-only"
if mount_point:
    print("Making mounted image read-only")
    subprocess.call(["chmod", "-R", "a-w", mount_point])

    # Detach the mounted image
    subprocess.call(["hdiutil", "detach", mount_point])
else:
    print("Mount point not found.")
    sys.exit(1)

# Convert to zlib-compressed image
subprocess.call(
    [
        "hdiutil",
        "convert",
        temp_dmg_path,
        "-format",
        "UDZO",
        "-ov",
        "-o",
        dmg_path,
    ]
)
remove(temp_dmg_path)

print("Done!")

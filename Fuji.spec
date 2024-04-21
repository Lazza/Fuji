# -*- mode: python ; coding: utf-8 -*-

import subprocess
from pathlib import Path
from shutil import copy, move

a = Analysis(
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
pyz = PYZ(a.pure)

exe = EXE(
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
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Fuji",
)
app = BUNDLE(
    coll,
    name="Fuji.app",
    icon="./packaging/Fuji.icns",
    bundle_identifier="com.andrealazzarotto.fuji",
)

executable_path = Path("./dist/Fuji.app/Contents/MacOS")
move(executable_path / "Fuji", executable_path / "Fuji.bin")
copy("./packaging/Fuji.sh", executable_path / "Fuji")

dmg_path = "./dist/FujiApp.dmg"
print("Building", dmg_path)
result = subprocess.call(
    ["dmgbuild", "-s", "./packaging/dmgbuild.py", "FujiApp", dmg_path]
)
if result == 0:
    print("Done")
else:
    print("Failed!!!")

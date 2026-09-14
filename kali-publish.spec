from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPECPATH)
datas = [(str(project_root / "utils" / "stealth.min.js"), "utils")]
binaries = []
hiddenimports = []

for package in ("playwright", "patchright"):
    package_datas, package_binaries, package_hiddenimports = collect_all(package)
    datas.extend(item for item in package_datas if ".local-browsers" not in str(item[0]))
    binaries.extend(item for item in package_binaries if ".local-browsers" not in str(item[0]))
    hiddenimports.extend(package_hiddenimports)

analysis = Analysis(
    [str(project_root / "app.py")],
    pathex=[str(project_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="kali-publish",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="kali-publish",
)

import os

a = Analysis(
    ['../../../core/pipe_client.py'],
    # SPECPATH = desktop/installer/Package/specs  →  ../../ = desktop/
    # Needed so PyInstaller can find the `native`, `views`, etc. packages
    # whose root is desktop/, not desktop/core/ (the entry-script dir).
    pathex=[os.path.normpath(os.path.join(SPECPATH, '..', '..'))],
    binaries=[("../../../native/windows/pipe/*.pyd", "native/windows/pipe")],

    datas=[("../../../resources/", "resources/")],
    hiddenimports=["native", "native.windows", "native.windows.pipe", "native.windows.pipe.pipe_module"],
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
    exclude_binaries=True,
    name='file',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon='../../../resources/icons/logo.ico',
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='FileHandler',
)
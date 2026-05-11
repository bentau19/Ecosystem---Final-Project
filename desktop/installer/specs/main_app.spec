a = Analysis(
    ['../../main.py'],
    pathex=[],
    binaries=[("../../native/windows/pipe/*.pyd", "native/windows/pipe")],
    datas=[("../../data/", "data/"),
           ("../../resources/", "resources/"),
           ("../../serializers/schemas/", "serializers/schemas/"),
           ("../../../TauSync/windows/tausync_py/dll/", "tausync_py/dll/")],
    hiddenimports=["tausync_py", "native", "native.windows", "native.windows.pipe", "native.windows.pipe.pipe_module"],
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
    name='SyncDose',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    icon='../../resources/icons/logo.ico',
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
    name='SyncDose',
)
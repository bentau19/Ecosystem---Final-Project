import os

a = Analysis(
    ['../../../main.py'],
    # FileDetection/ lives at the project root (one level above desktop/).
    # Adding it to pathex lets PyInstaller trace imports from classifer,
    # image_classifer, detector, file_duplicates, etc. at analysis time.
    pathex=[os.path.normpath(os.path.join(SPECPATH, '..', '..', '..', '..', 'FileDetection'))],
    binaries=[
        ("../../../native/windows/pipe/*.pyd", "native/windows/pipe"),
        ("../../../native/windows/virtual_drive/build/Release/VirtualDrive.exe",
         "native/windows/virtual_drive"),
    ],
    datas=[("../../../data/", "data/"),
           ("../../../resources/", "resources/"),
           ("../../../serializers/schemas/", "serializers/schemas/"),
           ("../../../../TauSync/windows/tausync_py/dll/", "tausync_py/dll/"),
           # FileDetection — bundled so the frozen exe can find classifer,
           # image_classifer, detector, file_duplicates, etc. at runtime.
           # main.py switches its sys.path injection to sys._MEIPASS when frozen.
           ("../../../../FileDetection/*.py", "FileDetection/"),
           ("../../../../FileDetection/checkers", "FileDetection/checkers"),
           ("../../../../FileDetection/model.pth", "FileDetection/")],
    hiddenimports=[
        "tausync_py",
        "native", "native.windows", "native.windows.pipe", "native.windows.pipe.pipe_module",
        # FileDetection runtime dependencies (C extensions PyInstaller may miss)
        "xxhash",
    ],
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
    console=False,
    disable_windowed_traceback=False,
    icon='../../../resources/icons/logo.ico',
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
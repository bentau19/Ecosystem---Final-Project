import os

a = Analysis(
    ['../../../core/file_handler.py'],
    # SPECPATH = desktop/installer/Package/specs  →  ../../../ = desktop/
    # Needed so PyInstaller can find the `native`, `views`, etc. packages
    # whose root is desktop/, not desktop/core/ (the entry-script dir).
    pathex=[os.path.normpath(os.path.join(SPECPATH, '..', '..', '..'))],
    binaries=[("../../../native/windows/pipe/*.pyd", "native/windows/pipe")],

    datas=[("../../../resources/", "resources/"),
           # Ship the native package __init__.py files ON DISK next to the
           # pipe_module.pyd. PyInstaller would otherwise keep them only in the
           # PYZ archive, leaving the on-disk native/windows/pipe/ folder (which
           # holds just the .pyd) to be picked up as a *namespace package*. That
           # shadows the real package, so __init__.py never runs and you get:
           #   ImportError: cannot import name 'Client' ... (unknown location)
           ("../../../native/__init__.py", "native"),
           ("../../../native/windows/__init__.py", "native/windows"),
           ("../../../native/windows/pipe/__init__.py", "native/windows/pipe")],
    hiddenimports=["native", "native.windows", "native.windows.pipe", "native.windows.pipe.pipe_module", "views", "views.widgets", "views.widgets.dialogs"],
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
    name='FileHandler',
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
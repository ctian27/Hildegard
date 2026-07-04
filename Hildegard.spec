# PyInstaller spec for the Hildegard standalone app.
# Build:  pyinstaller --noconfirm Hildegard.spec
# Output: dist/Hildegard.app (macOS)  |  dist/Hildegard/Hildegard.exe (Windows)
#
# One entry point (app.py) serves both the GUI and, via `--pipeline`, a cycle.

import sys
from PyInstaller.utils.hooks import collect_submodules

datas = [
    ("assets/hildegard_icon.png", "assets"),
]

# xhtml2pdf/reportlab pull in modules PyInstaller doesn't always trace.
hiddenimports = (
    collect_submodules("xhtml2pdf")
    + collect_submodules("reportlab")
    + ["markdown"]
)

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Hildegard",
    debug=False,
    strip=False,
    upx=False,
    console=False,               # windowed GUI app
    icon="assets/hildegard.ico" if sys.platform.startswith("win") else "assets/hildegard.icns",
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False, name="Hildegard",
)

# macOS: wrap COLLECT output in a proper .app bundle.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="Hildegard.app",
        icon="assets/hildegard.icns",
        bundle_identifier="local.hildegard.app",
        info_plist={
            "CFBundleName": "Hildegard",
            "CFBundleDisplayName": "Hildegard",
            "CFBundleShortVersionString": "1.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.13",
        },
    )

# PyInstaller runtime hook — ensure frozen bundle root is importable.
import os
import sys

if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    root = sys._MEIPASS
    if root not in sys.path:
        sys.path.insert(0, root)
    os.environ.setdefault("CM_DESKTOP", "1")

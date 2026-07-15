"""Tests for the desktop installer infrastructure (NSIS, VERSION, build script).

These are static-analysis and dry-run checks. No actual NSIS or PyInstaller.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DESKTOP = ROOT / "desktop"
SCRIPTS = ROOT / "scripts"


class TestVersionFile:

    def test_version_file_exists(self):
        assert DESKTOP.joinpath("VERSION").is_file()

    def test_version_file_readable(self):
        raw = DESKTOP.joinpath("VERSION").read_text(encoding="utf-8").strip()
        assert raw, "VERSION file is empty"

    def test_version_is_semver(self):
        raw = DESKTOP.joinpath("VERSION").read_text(encoding="utf-8").strip()
        assert re.match(r"^\d+\.\d+\.\d+$", raw), f"VERSION '{raw}' not semver"

    def test_version_matches_init(self):
        v = DESKTOP.joinpath("VERSION").read_text(encoding="utf-8").strip()
        init = DESKTOP.joinpath("__init__.py").read_text(encoding="utf-8")
        m = re.search(r'__version__\s*=\s*"([^"]+)"', init)
        assert m, "No __version__ in __init__.py"
        assert m.group(1) == v, f"__init__.py {m.group(1)} != VERSION {v}"

    def test_version_matches_nsis(self):
        v = DESKTOP.joinpath("VERSION").read_text(encoding="utf-8").strip()
        nsis = DESKTOP.joinpath("installer.nsi").read_text(encoding="utf-8")
        assert f'PRODUCT_VERSION       "{v}"' in nsis


class TestNSISInstaller:

    NSIS_PATH = DESKTOP / "installer.nsi"

    def test_nsis_file_exists(self):
        assert self.NSIS_PATH.is_file()

    def _text(self):
        return self.NSIS_PATH.read_text(encoding="utf-8")

    def test_has_install_section(self):
        assert 'Section "MainApplication"' in self._text()

    def test_has_uninstall_section(self):
        assert 'Section "Uninstall"' in self._text()

    def test_has_start_menu_shortcut(self):
        t = self._text()
        assert "SMPROGRAMS" in t and "CreateShortCut" in t

    def test_has_desktop_shortcut(self):
        assert "$DESKTOP" in self._text()

    def test_has_uninstaller_registration(self):
        t = self._text()
        assert "UninstallString" in t and "DisplayName" in t

    def test_has_uninstaller_writer(self):
        assert "WriteUninstaller" in self._text()

    def test_has_version_info_block(self):
        t = self._text()
        assert "VIProductVersion" in t and "VIAddVersionKey" in t

    def test_requires_admin(self):
        assert "RequestExecutionLevel admin" in self._text()

    def test_section_names_unique(self):
        t = self._text()
        s = re.findall(r'^Section\s+"([^"]*)"', t, re.MULTILINE)
        assert len(s) == len(set(s)), f"Duplicate sections: {s}"


class TestBuildInstallerScript:

    SCRIPT_PATH = SCRIPTS / "build-installer.ps1"

    def test_script_exists(self):
        assert self.SCRIPT_PATH.is_file()

    def _text(self):
        return self.SCRIPT_PATH.read_text(encoding="utf-8")

    def test_has_pyinstaller_step(self):
        t = self._text()
        assert "build-windows.ps1" in t and "SkipPyInstaller" in t

    def test_has_makensis_detection(self):
        assert "makensis" in self._text()

    def test_has_nsis_invocation(self):
        t = self._text()
        assert "installer.nsi" in t and "$InstallersDir" in t

    def test_handles_skip_flag(self):
        assert "-SkipPyInstaller" in self._text()

    def test_creates_installers_directory(self):
        t = self._text()
        assert "dist/installers" in t or "dist\\installers" in t

    def test_script_is_syntactically_valid(self):
        t = self._text()
        assert t.count("{") == t.count("}")
        assert t.count("(") == t.count(")")
        assert t.count("[") == t.count("]")

    def test_calls_build_windows(self):
        assert "build-windows.ps1" in self._text()


class TestIconFile:

    def test_icon_svg_exists(self):
        assert DESKTOP.joinpath("icon.svg").is_file()

    def test_icon_svg_has_monkey_features(self):
        svg = DESKTOP.joinpath("icon.svg").read_text(encoding="utf-8")
        keywords = ("monkey", "face", "ears", "snout", "nostrils")
        assert any(k in svg for k in keywords)

    def test_icon_svg_has_conversion_note(self):
        svg = DESKTOP.joinpath("icon.svg").read_text(encoding="utf-8")
        keywords = ("codemonkeys.ico", "ImageMagick", "icoconverter", "convert")
        assert any(k in svg for k in keywords)

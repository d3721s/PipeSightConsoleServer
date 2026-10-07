"""Validate packaging boundaries and reject incompatible offline dependencies."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

DEPLOY = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("bundle", DEPLOY / "lib/bundle.py")
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project = self.root / "source"
        self.cache = self.root / "offline"
        self.cache.mkdir()
        self.write("front_end/package-lock.json", '{"lockfileVersion":3}\n')
        self.write("server/pyproject.toml", '[project]\ndependencies = ["httpx"]\n')
        self.write("deploy/config/system-packages.txt", "python3\n")
        bundle.manifest(self.project, self.cache, "amd64", "22.23.0", "v1.15.2")

    def write(self, name, value="test\n"):
        path = self.project / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value.encode("utf-8"))
        return path

    def test_current_source_is_compatible(self):
        bundle.validate(self.project, self.cache)

    def test_changed_frontend_lock_is_rejected(self):
        self.write("front_end/package-lock.json", "changed")
        with self.assertRaisesRegex(ValueError, "FRONT_LOCK_SHA256"):
            bundle.validate(self.project, self.cache)

    def test_changed_python_dependencies_are_rejected(self):
        self.write("server/pyproject.toml", "changed")
        with self.assertRaisesRegex(ValueError, "PYPROJECT_SHA256"):
            bundle.validate(self.project, self.cache)

    def test_different_python_minor_is_rejected(self):
        path = self.cache / "manifest.env"
        value = path.read_text().replace(
            f"PYTHON_MINOR={sys.version_info.major}.{sys.version_info.minor}", "PYTHON_MINOR=0.0"
        )
        path.write_text(value)
        with self.assertRaisesRegex(ValueError, "PYTHON_MINOR"):
            bundle.validate(self.project, self.cache)

    def test_changed_system_dependencies_are_rejected(self):
        self.write("deploy/config/system-packages.txt", "python3\nffmpeg\n")
        with self.assertRaisesRegex(ValueError, "SYSTEM_PACKAGES_SHA256"):
            bundle.validate(self.project, self.cache)

    def test_manifest_is_data_not_executable_code(self):
        (self.cache / "manifest.env").write_text("FORMAT=$(touch dangerous)\n")
        with self.assertRaises(ValueError):
            bundle.validate(self.project, self.cache)
        self.assertFalse((self.root / "dangerous").exists())

    @unittest.skipUnless(sys.platform == "linux", "requires sha256sum")
    def test_checksums_detect_corruption(self):
        path = self.cache / "python/wheels/package.whl"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"original")
        bundle.checksums(self.cache)
        command = ["sha256sum", "--check", "--strict", "--quiet", "SHA256SUMS"]
        self.assertEqual(subprocess.run(command, cwd=self.cache, capture_output=True).returncode, 0)
        path.write_bytes(b"corrupt")
        self.assertNotEqual(subprocess.run(command, cwd=self.cache, capture_output=True).returncode, 0)

    def test_snapshot_omits_machine_state_and_keeps_selected_sdk(self):
        for name in (
            "deploy/install-online.sh", "deploy/config/versions.env", "front_end/src/main.ts",
            "pointcloud_bridge/main.cpp", "server/app/main.py", "server/.env.example",
            "3d_camera/linux/include/camera.h", "3d_camera/linux/src/CameraSrv.cpp",
            "3d_camera/linux/configurationfiles/config.json", "3d_camera/linux/scripts/setup.sh",
            "3d_camera/linux/libs/include/sdk.h",
            "3d_camera/linux/libs/lib/x86_64-linux-gnu/libCamera.so",
            "3d_camera/linux/libs/lib/aarch64-linux-gnu/libCamera.so",
            "README.md", ".gitignore", ".gitattributes",
        ):
            self.write(name)
        for name in (
            "server/.env", "server/data/app.db", "server/storage/recording.mp4",
            "server/.venv/bin/python", "front_end/node_modules/pkg/index.js",
            "front_end/dist/index.html", "front_end/.env", "deploy/offline/private.deb",
            "pointcloud_bridge/pointcloud_bridge", "server/app/__pycache__/main.pyc",
        ):
            self.write(name)
        self.write("deploy/install-online.sh", "#!/bin/bash\r\necho test\r\n")
        output = self.root / "snapshot"
        bundle.snapshot(self.project, output, "x86_64-linux-gnu")
        self.assertTrue((output / "3d_camera/linux/libs/lib/x86_64-linux-gnu/libCamera.so").is_file())
        self.assertFalse((output / "3d_camera/linux/libs/lib/aarch64-linux-gnu").exists())
        self.assertTrue((output / "server/.env.example").is_file())
        self.assertTrue((output / "server/app/main.py").is_file())
        for relative in (
            "server/.env", "server/data", "server/storage", "server/.venv", "front_end/node_modules",
            "front_end/dist", "front_end/.env", "deploy/offline", "pointcloud_bridge/pointcloud_bridge",
            "server/app/__pycache__",
        ):
            self.assertFalse((output / relative).exists(), relative)
        self.assertNotIn(b"\r", (output / "deploy/install-online.sh").read_bytes())

    def test_unit_render_escapes_paths_and_allows_double_underscores(self):
        template = self.root / "example.service"
        template.write_text('ExecStart="__EXEC__"\n')
        output = self.root / "rendered.service"
        bundle.render(template, output, ['EXEC=/opt/a space/100%/with__name/python'])
        self.assertEqual(output.read_text(), 'ExecStart="/opt/a space/100%%/with__name/python"\n')

    def test_unit_render_rejects_missing_placeholders(self):
        template = self.root / "example.service"
        template.write_text('ExecStart="__EXEC__"\n')
        with self.assertRaisesRegex(ValueError, "EXEC"):
            bundle.render(template, self.root / "rendered.service", ["OTHER=/bin/true"])

    @unittest.skipUnless(sys.platform == "linux" and shutil.which("systemd-analyze"), "requires systemd-analyze")
    def test_systemd_accepts_rendered_units_with_spaces_and_percent(self):
        directory = self.root / "project space 100%"
        directory.mkdir()
        arguments = [
            "USER=root", "GROUP=root", f"SERVER_DIR={directory}",
            f"BRIDGE_DIR={directory}", f"SDK_LIB_DIR={directory}",
            "VENV_PY=/usr/bin/true", "BRIDGE_EXE=/usr/bin/true",
        ]
        units = []
        for template in (DEPLOY / "templates/systemd").glob("*.service"):
            output = self.root / template.name
            bundle.render(template, output, arguments)
            units.append(str(output))
        result = subprocess.run(["systemd-analyze", "verify", *units], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        # systemd may return success while ignoring invalid individual directives.
        for unit in units:
            self.assertNotIn(f"{unit}:", result.stderr, result.stderr)


if __name__ == "__main__":
    unittest.main()

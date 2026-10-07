#!/usr/bin/env python3
"""Small deployment helpers; no application imports or hardware side effects."""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def requirements(project: Path, output: Path) -> None:
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    with (project / "server/pyproject.toml").open("rb") as stream:
        dependencies = tomllib.load(stream)["project"]["dependencies"]
    output.write_text("\n".join(dependencies) + "\n", encoding="utf-8")


def snapshot(project: Path, output: Path, sdk_arch: str) -> None:
    output.mkdir(parents=True, exist_ok=True)
    excluded = (
        ".git", ".env", ".venv", "node_modules", "dist", "__pycache__",
        "*.pyc", "*.log", ".deploy", "offline", "data", "storage",
    )
    ignored = shutil.ignore_patterns(*excluded)
    for name in ("deploy", "front_end", "pointcloud_bridge"):
        # Service files describe the preparation host. Generate actual target units at install time.
        exclusions = shutil.ignore_patterns(*excluded, "systemd") if name == "deploy" else ignored
        shutil.copytree(project / name, output / name, ignore=exclusions)
    # The compiled bridge is never transferred between systems.
    binary = output / "pointcloud_bridge/pointcloud_bridge"
    if binary.exists() or binary.is_symlink():
        binary.unlink()
    shutil.copytree(project / "server/app", output / "server/app", ignore=ignored)
    for name in ("pyproject.toml",):
        shutil.copy2(project / "server" / name, output / "server" / name)
    sdk_source = project / "3d_camera/linux"
    sdk_output = output / "3d_camera/linux"
    for name in ("include", "src", "configurationfiles", "scripts"):
        shutil.copytree(sdk_source / name, sdk_output / name, ignore=ignored)
    shutil.copytree(sdk_source / "libs/include", sdk_output / "libs/include")
    shutil.copytree(sdk_source / "libs/lib" / sdk_arch, sdk_output / "libs/lib" / sdk_arch)
    for name in ("README.md", ".gitignore", ".gitattributes"):
        shutil.copy2(project / name, output / name)
    for path in output.rglob("*"):
        if path.is_file() and path.suffix in (".sh", ".service", ".rules"):
            path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


def manifest(project: Path, bundle: Path, arch: str, node: str, mediamtx: str) -> None:
    fields = {
        "FORMAT": "1",
        "OS_ID": "ubuntu",
        "OS_VERSION": "22.04",
        "ARCH": arch,
        "PYTHON_MINOR": f"{sys.version_info.major}.{sys.version_info.minor}",
        "NODE_VERSION": node,
        "MEDIAMTX_VERSION": mediamtx,
        "FRONT_LOCK_SHA256": digest(project / "front_end/package-lock.json"),
        "PYPROJECT_SHA256": digest(project / "server/pyproject.toml"),
        "SYSTEM_PACKAGES_SHA256": digest(project / "deploy/config/system-packages.txt"),
        "OFFLINE_BASE_PACKAGES_SHA256": digest(project / "deploy/config/offline-base-packages.txt"),
    }
    (bundle / "manifest.env").write_text(
        "".join(f"{key}={value}\n" for key, value in fields.items()), encoding="utf-8"
    )


def read_manifest(bundle: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in (bundle / "manifest.env").read_text(encoding="utf-8").splitlines())


def validate(project: Path, bundle: Path) -> None:
    fields = read_manifest(bundle)
    expected = {
        "FORMAT": "1",
        "PYTHON_MINOR": f"{sys.version_info.major}.{sys.version_info.minor}",
        "FRONT_LOCK_SHA256": digest(project / "front_end/package-lock.json"),
        "PYPROJECT_SHA256": digest(project / "server/pyproject.toml"),
        "SYSTEM_PACKAGES_SHA256": digest(project / "deploy/config/system-packages.txt"),
        "OFFLINE_BASE_PACKAGES_SHA256": digest(project / "deploy/config/offline-base-packages.txt"),
    }
    for key, value in expected.items():
        if fields.get(key) != value:
            raise ValueError(f"Offline bundle does not match {key}; prepare a new bundle for this project/platform")


def checksums(bundle: Path) -> None:
    entries = []
    for path in sorted(bundle.rglob("*")):
        if path.name == "SHA256SUMS" or not path.is_file():
            continue
        relative = path.relative_to(bundle).as_posix()
        if "\n" in relative or "\\" in relative:
            raise ValueError("Bundle filenames must not contain newlines or backslashes")
        entries.append(f"{digest(path)}  {relative}\n")
    (bundle / "SHA256SUMS").write_text("".join(entries), encoding="utf-8")


def unit_value(value: str | Path) -> str:
    value = str(value)
    if "\n" in value or "\r" in value:
        raise ValueError("systemd values must not contain newlines")
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%")


def units(project: Path, release: Path, user: str, group: str, sdk_arch: str, output: Path) -> None:
    """Write complete service files with the actual installation paths and account."""
    server = unit_value(project / "server")
    bridge = unit_value(project / "pointcloud_bridge")
    python = unit_value(release / "venv/bin/python")
    executable = unit_value(release / "pointcloud_bridge")
    libraries = unit_value(project / "3d_camera/linux/libs/lib" / sdk_arch)
    user, group = unit_value(user), unit_value(group)
    output.mkdir(parents=True, exist_ok=True)
    backend = f"""[Unit]
Description=PipeSight API, frontend and camera services
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={server}
Environment=PYTHONUNBUFFERED=1
Environment=PIPESIGHT_HOST=0.0.0.0
Environment=PIPESIGHT_PORT=8000
EnvironmentFile={server}/.env
ExecStart="{python}" -m uvicorn app.main:app --host ${{PIPESIGHT_HOST}} --port ${{PIPESIGHT_PORT}} --workers 1
Restart=on-failure
RestartSec=3
TimeoutStopSec=20
SupplementaryGroups=dialout
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    camera = f"""[Unit]
Description=PipeSight depth camera streams (9090-9093)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
Group={group}
WorkingDirectory={bridge}
Environment="LD_LIBRARY_PATH={libraries}"
ExecStart="{executable}"
Restart=on-failure
RestartSec=3
TimeoutStopSec=15
SupplementaryGroups=video
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
"""
    for name, content in (("pipesight-backend", backend), ("pipesight-pcl-bridge", camera)):
        (output / f"{name}.service").write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for name in ("requirements", "validate"):
        action = actions.add_parser(name)
        action.add_argument("project", type=Path)
        action.add_argument("output", type=Path)
    action = actions.add_parser("snapshot")
    action.add_argument("project", type=Path)
    action.add_argument("output", type=Path)
    action.add_argument("sdk_arch")
    action = actions.add_parser("manifest")
    action.add_argument("project", type=Path)
    action.add_argument("bundle", type=Path)
    action.add_argument("arch")
    action.add_argument("node")
    action.add_argument("mediamtx")
    action = actions.add_parser("checksums")
    action.add_argument("bundle", type=Path)
    action = actions.add_parser("units")
    action.add_argument("project", type=Path)
    action.add_argument("release", type=Path)
    action.add_argument("user")
    action.add_argument("group")
    action.add_argument("sdk_arch")
    action.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.action == "requirements":
        requirements(args.project, args.output)
    elif args.action == "snapshot":
        snapshot(args.project, args.output, args.sdk_arch)
    elif args.action == "manifest":
        manifest(args.project, args.bundle, args.arch, args.node, args.mediamtx)
    elif args.action == "validate":
        validate(args.project, args.output)
    elif args.action == "checksums":
        checksums(args.bundle)
    elif args.action == "units":
        units(args.project, args.release, args.user, args.group, args.sdk_arch, args.output)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)

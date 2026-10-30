#!/usr/bin/env python3
"""Plan and verify the prebuilt Home Assistant App images published to GHCR."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "ghcr.io/tlamoureux24"
RUNNERS = {
    "amd64": "ubuntu-24.04",
    "aarch64": "ubuntu-24.04-arm",
}
PLATFORMS = {
    "amd64": "linux/amd64",
    "aarch64": "linux/arm64",
}
SCALAR = re.compile(r'^(?P<key>[a-z_]+):\s*"(?P<value>[^"]*)"\s*$')


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=True, text=True, capture_output=True,
    ).stdout


def read_config(text: str) -> dict[str, object]:
    """Read the top-level keys this workflow needs without a YAML dependency."""
    config: dict[str, object] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = SCALAR.match(line)
        if match:
            config[match["key"]] = match["value"]
        elif line == "arch:":
            arches = []
            for item in lines[index + 1:]:
                if not item.startswith("  - "):
                    break
                arches.append(item[4:].strip())
            config["arch"] = arches
    return config


def config_at(ref: str | None, app: str) -> dict[str, object]:
    if ref is None:
        return read_config((ROOT / app / "config.yaml").read_text(encoding="utf-8"))
    try:
        return read_config(git("show", f"{ref}:{app}/config.yaml"))
    except subprocess.CalledProcessError:
        return {}


def apps() -> list[str]:
    return sorted(path.parent.name for path in ROOT.glob("*/config.yaml"))


def expected_image(app: str) -> str:
    return f"{REGISTRY}/{{arch}}-{app}"


def check() -> list[str]:
    errors: list[str] = []
    for app in apps():
        config = config_at(None, app)
        if config.get("slug") != app:
            errors.append(f"{app}: slug must match the App directory")
        if config.get("image") != expected_image(app):
            errors.append(f'{app}: config.yaml must declare image: "{expected_image(app)}"')
        unsupported = set(config.get("arch", [])) - set(RUNNERS)
        if not config.get("arch") or unsupported:
            errors.append(f"{app}: unsupported or missing arch list {sorted(unsupported)}")
        if not config.get("version"):
            errors.append(f"{app}: version is missing")
    return errors


def selected(requested: str) -> list[str]:
    known = apps()
    if requested.strip() in ("", "all"):
        return known
    names = [name for name in re.split(r"[\s,]+", requested.strip()) if name]
    unknown = sorted(set(names) - set(known))
    if unknown:
        raise SystemExit(f"Unknown Apps: {', '.join(unknown)}")
    return sorted(set(names))


def changed(before: str, after: str) -> list[str]:
    """Apps whose config.yaml changed in a push; all Apps when this tooling changed."""
    if not before or set(before) == {"0"}:
        return apps()
    try:
        paths = git("diff", "--name-only", before, after).splitlines()
    except subprocess.CalledProcessError:
        return apps()
    if any(path in ("scripts/app_images.py", ".github/workflows/app-images-publish.yml") for path in paths):
        return apps()
    edited = {path.split("/", 1)[0] for path in paths if re.fullmatch(r"[^/]+/config\.yaml", path)}
    return sorted(edited & set(apps()))


def matrix(names: list[str]) -> dict[str, object]:
    include = []
    for app in names:
        config = config_at(None, app)
        for arch in config["arch"]:
            include.append({
                "app": app,
                "arch": arch,
                "runner": RUNNERS[arch],
                "platform": PLATFORMS[arch],
                "version": config["version"],
                "image": str(config["image"]).replace("{arch}", arch),
            })
    return {"include": include}


def context_digest(ref: str, app: str) -> str:
    """Digest the App build context, ignoring Markdown that never reaches the image."""
    listing = [
        line for line in git("ls-tree", "-r", "--full-tree", ref, "--", f"{app}/").splitlines()
        if not line.endswith(".md")
    ]
    return "sha256:" + hashlib.sha256("\n".join(listing).encode()).hexdigest()


def labels(inspect_json: str) -> dict[str, str]:
    """Extract labels from `docker buildx imagetools inspect --format '{{json .Image}}'`."""
    image = json.loads(inspect_json)
    if "config" not in image:
        image = next((value for value in image.values() if "config" in value), {})
    return image.get("config", {}).get("Labels") or {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="verify every App declares its GHCR image")
    plan = commands.add_parser("matrix", help="print the GitHub Actions build matrix")
    plan.add_argument("--apps", default="all")
    plan.add_argument("--before", default="")
    plan.add_argument("--after", default="")
    digest = commands.add_parser("context", help="print the build-context digest of an App")
    digest.add_argument("--ref", default="HEAD")
    digest.add_argument("app")
    released = commands.add_parser("version", help="print an App version at a Git ref")
    released.add_argument("--ref", default=None)
    released.add_argument("app")
    label = commands.add_parser("label", help="read one label from imagetools JSON on stdin")
    label.add_argument("name")
    args = parser.parse_args()

    if args.command == "check":
        errors = check()
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"{len(apps())} Apps declare prebuilt GHCR images")
    elif args.command == "matrix":
        names = changed(args.before, args.after) if args.after else selected(args.apps)
        print(json.dumps(matrix(names), separators=(",", ":")))
    elif args.command == "context":
        print(context_digest(args.ref, args.app))
    elif args.command == "version":
        print(config_at(args.ref, args.app).get("version", ""))
    elif args.command == "label":
        print(labels(sys.stdin.read()).get(args.name, ""))


if __name__ == "__main__":
    main()

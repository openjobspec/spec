#!/usr/bin/env python3
"""Validate generic stable-SemVer Release Please progression."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
CHANGELOG_HEADING_RE = re.compile(
    r"^## \[([^\]]+)\] - (?:Unreleased|\d{4}-\d{2}-\d{2})$",
    re.MULTILINE,
)
SemVer = tuple[int, int, int]


def find_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(find_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(find_key(item, key) for item in value)
    return False


def parse_semver(version: object) -> SemVer:
    if not isinstance(version, str):
        raise ValueError("version must be a string")
    match = SEMVER_RE.fullmatch(version)
    if not match:
        raise ValueError(f"not a stable SemVer: {version!r}")
    return tuple(int(part) for part in match.groups())


def format_semver(version: SemVer) -> str:
    return ".".join(str(part) for part in version)


def bump_patch(version: SemVer) -> SemVer:
    major, minor, patch = version
    return major, minor, patch + 1


def bump_minor(version: SemVer) -> SemVer:
    major, minor, _patch = version
    return major, minor + 1, 0


def bump_major(version: SemVer) -> SemVer:
    major, _minor, _patch = version
    return major + 1, 0, 0


def is_monotonic(current: SemVer, target: SemVer) -> bool:
    return target >= current


def validate_semver_cycles(base: SemVer) -> list[str]:
    errors: list[str] = []
    patch = bump_patch(base)
    minor = bump_minor(base)
    major = bump_major(base)
    future = bump_minor(minor)

    for label, candidate in (
        ("current", base),
        ("patch", patch),
        ("minor", minor),
        ("major", major),
        ("future", future),
    ):
        if not is_monotonic(base, candidate):
            errors.append(f"{label} cycle is not monotonic from {format_semver(base)}")
    if is_monotonic(patch, base):
        errors.append("backward version progression was accepted")
    for invalid in ("", "v1.2.3", "1.2", "1.2.3-rc.1", "next"):
        try:
            parse_semver(invalid)
        except ValueError:
            continue
        errors.append(f"non-stable version was accepted: {invalid!r}")
    return errors


def main() -> int:
    config = json.loads(
        (ROOT / "release-please-config.json").read_text(encoding="utf-8")
    )
    manifest = json.loads(
        (ROOT / ".release-please-manifest.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []

    if find_key(config, "release-as"):
        errors.append("release-as must not be persisted in Release Please configuration")
    if config.get("bump-minor-pre-major") is not True:
        errors.append("bump-minor-pre-major must be enabled")
    manifest_version_raw = manifest.get(".")
    try:
        manifest_version = parse_semver(manifest_version_raw)
    except ValueError as exc:
        errors.append(f"manifest version is invalid: {exc}")
        manifest_version = None

    changelog_text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    target_match = CHANGELOG_HEADING_RE.search(changelog_text)
    if target_match is None:
        errors.append("CHANGELOG.md has no stable release heading")
        target_version = None
    else:
        try:
            target_version = parse_semver(target_match.group(1))
        except ValueError as exc:
            errors.append(f"changelog target is invalid: {exc}")
            target_version = None

    tags = subprocess.run(
        ["git", "-C", str(ROOT), "tag", "--list", "v*"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    tag_versions: list[SemVer] = []
    for tag in tags:
        try:
            tag_versions.append(parse_semver(tag.removeprefix("v")))
        except ValueError as exc:
            errors.append(f"release tag is invalid: {tag!r}: {exc}")
    latest_tag_version = max(tag_versions) if tag_versions else None
    if manifest_version != latest_tag_version:
        errors.append(
            "manifest must record the actual last published version "
            f"{format_semver(latest_tag_version) if latest_tag_version else None}, "
            f"found {manifest_version_raw}"
        )

    if manifest_version is not None:
        errors.extend(validate_semver_cycles(manifest_version))
    if target_version is not None:
        errors.extend(validate_semver_cycles(target_version))
    if manifest_version is not None and target_version is not None:
        if not is_monotonic(manifest_version, target_version):
            errors.append(
                "changelog target moves backward from "
                f"{format_semver(manifest_version)} to {format_semver(target_version)}"
            )
        feature_version = bump_minor(manifest_version)
        if feature_version == manifest_version:
            errors.append(
                f"feature calculation is stuck at {format_semver(manifest_version)}"
            )
        if bump_minor(target_version) == target_version:
            errors.append(
                f"post-release calculation is stuck at {format_semver(target_version)}"
            )

    if errors:
        for error in errors:
            print(f"release config error: {error}", file=sys.stderr)
        return 1
    print(
        "Release Please versions are monotonic: "
        f"manifest={format_semver(manifest_version)}, "
        f"target={format_semver(target_version)}, "
        f"next-feature={format_semver(bump_minor(manifest_version))}, "
        f"post-release={format_semver(bump_minor(target_version))}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

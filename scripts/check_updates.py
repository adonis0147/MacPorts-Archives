#!/usr/bin/env python3
"""Compare public Forge baselines with upstream; dispatch only when needed."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from urllib.request import Request, urlopen

NAME = r"[A-Za-z0-9_.+-]+"
VERSION = r"[0-9]+\.[0-9]+\.[0-9]+"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targets", type=Path, default=Path("config/targets.json"))
    parser.add_argument("--baselines", type=Path, default=Path("updates"))
    parser.add_argument("--state", type=Path, default=Path(".update-state/state.json"))
    parser.add_argument("--ports", type=Path, required=True)
    args = parser.parse_args()
    targets = load_targets(args.targets)
    if not args.ports.is_dir():
        raise ValueError("ports checkout is not a directory")
    version = latest_version()
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    if not isinstance(state, dict):
        raise ValueError("cooldown state must be an object")
    now = datetime.now(timezone.utc)

    for target, expected in targets.items():
        baseline_path = args.baselines / f"{target}.json"
        baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
        fingerprint, reasons = check(target, expected, baseline, args.ports, version, now)
        if not reasons:
            print(f"{target}: unchanged")
            continue
        if cooling_down(state.get(target), fingerprint, now):
            print(f"{target}: dispatch suppressed for 24h ({', '.join(reasons)})")
            continue
        dispatch(target)
        state[target] = {"fingerprint": fingerprint, "dispatched_at": datetime.now(timezone.utc).isoformat()}
        args.state.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.state.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, sort_keys=True) + "\n")
        temporary.replace(args.state)
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a") as output:
                output.write("dispatched=true\n")
        print(f"{target}: dispatched ({', '.join(reasons)})")


def load_targets(path):
    targets = json.loads(path.read_text())
    if not isinstance(targets, dict) or not targets:
        raise ValueError("targets must be a nonempty object")
    for target, expected in targets.items():
        if not safe_name(target) or not isinstance(expected, dict):
            raise ValueError("invalid target")
        if type(expected.get("darwin")) is not int or expected["darwin"] <= 0:
            raise ValueError("invalid Darwin major")
        if not safe_name(expected.get("arch")):
            raise ValueError("invalid architecture")
    return targets


def safe_name(value):
    return isinstance(value, str) and value not in (".", "..") and re.fullmatch(NAME, value)


def valid_directory(value):
    if not isinstance(value, str):
        return False
    parts = value.split("/")
    return value == "_resources" or (len(parts) == 2 and all(safe_name(p) for p in parts))


def utc_timestamp(value):
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO UTC")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamp must be ISO UTC")
    return parsed


def validate_baseline(baseline, target, expected):
    if not isinstance(baseline, dict) or type(baseline.get("schema")) is not int or baseline["schema"] != 1:
        raise ValueError("unsupported baseline schema")
    if baseline.get("target") != target:
        raise ValueError("baseline target mismatch")
    platform = baseline.get("platform")
    if (not isinstance(platform, list) or len(platform) != 3 or platform[0] != "Darwin"
            or not isinstance(platform[1], str) or not re.fullmatch(VERSION, platform[1])
            or int(platform[1].split(".")[0]) != expected["darwin"]
            or platform[2] != expected["arch"]):
        raise ValueError("baseline platform mismatch")
    specs = baseline.get("specs")
    if not isinstance(specs, list) or not specs:
        raise ValueError("invalid baseline specs")
    for spec in specs:
        if (not isinstance(spec, list) or not spec or not safe_name(spec[0])
                or any(not isinstance(v, str) or not re.fullmatch(r"[+-]" + NAME, v) for v in spec[1:])):
            raise ValueError("invalid baseline spec")
    version = baseline.get("macports_version")
    if not isinstance(version, str) or not re.fullmatch(VERSION, version):
        raise ValueError("invalid baseline MacPorts version")
    directories = baseline.get("directories")
    if not isinstance(directories, dict) or "_resources" not in directories:
        raise ValueError("baseline must include _resources")
    for directory, digest in directories.items():
        if not valid_directory(directory):
            raise ValueError(f"unsafe recipe directory: {directory!r}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError("invalid directory digest")
    if "checked_at" in baseline:
        utc_timestamp(baseline["checked_at"])


def directory_digest(root, directory):
    """Hash directory-relative paths, preserving symlinks without following them."""
    current = root
    for component in directory.split("/"):
        current = current / component
        if current.is_symlink():
            raise ValueError(f"symlink in recipe directory path: {directory}")
    if not current.exists():
        return None
    if not current.is_dir():
        raise ValueError(f"recipe directory is not a directory: {directory}")
    records = []
    for parent, dirs, files in os.walk(current, followlinks=False, onerror=raise_walk_error):
        for name in sorted(dirs + files):
            path = Path(parent) / name
            relative = path.relative_to(current).as_posix()
            if path.is_symlink():
                records.append([relative, "symlink", os.readlink(path)])
            elif path.is_file():
                records.append([relative, "file", hashlib.sha256(path.read_bytes()).hexdigest()])
            elif not path.is_dir():
                raise ValueError(f"unsupported file type: {path}")
    return json_digest(sorted(records))


def raise_walk_error(error):
    raise error


def json_digest(value):
    return hashlib.sha256(json.dumps(value, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def check(target, expected, baseline, ports, version, now):
    reasons = []
    directories = {}
    if baseline is None:
        reasons.append("missing baseline")
    else:
        validate_baseline(baseline, target, expected)
        directories = {directory: directory_digest(ports, directory) for directory in baseline["directories"]}
        if directories != baseline["directories"]:
            reasons.append("recipe/dependency/resources changed or removed")
        if version != baseline["macports_version"]:
            reasons.append("MacPorts release changed")
        checked = utc_timestamp(baseline["checked_at"]) if "checked_at" in baseline else None
        if checked is None or now - checked >= timedelta(days=7):
            reasons.append("weekly safety check due")
    # Baseline identity resets cooldown after publication, but no daily bucket bypasses it.
    fingerprint = json_digest({"target": target, "expected": expected, "baseline": baseline,
                               "directories": directories, "macports_version": version})
    return fingerprint, reasons


def cooling_down(marker, fingerprint, now):
    if not isinstance(marker, dict) or marker.get("fingerprint") != fingerprint:
        return False
    try:
        age = now - utc_timestamp(marker.get("dispatched_at"))
    except (ValueError, TypeError):
        return False
    return timedelta(0) <= age < timedelta(hours=24)


def latest_version(open_url=urlopen):
    request = Request("https://api.github.com/repos/macports/macports-base/releases/latest",
                      headers={"Accept": "application/vnd.github+json", "User-Agent": "MacPorts-Archives"})
    with open_url(request, timeout=60) as response:
        release = json.load(response)
    tag = release["tag_name"]
    version = tag.removeprefix("v")
    if release.get("draft") or release.get("prerelease") or not re.fullmatch(VERSION, version):
        raise ValueError("upstream latest release is not a stable version")
    return version


def dispatch(target, run=subprocess.run):
    repository = os.environ.get("FORGE_REPOSITORY") or "adonis0147/MacPorts-Forge"
    ref = os.environ.get("FORGE_REF") or "main"
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("invalid Forge repository")
    token = os.environ["FORGE_DISPATCH_TOKEN"]
    payload = json.dumps({"ref": ref, "inputs": {"macos": target}})
    # Send credentials through the environment, never command arguments or logs.
    run(["gh", "api", "--method", "POST", f"repos/{repository}/actions/workflows/build-ports.yml/dispatches",
         "--input", "-"], input=payload, text=True, check=True,
        env={**os.environ, "GH_TOKEN": token})


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Update check failed: {error}", file=sys.stderr)
        sys.exit(1)

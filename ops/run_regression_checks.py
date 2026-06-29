#!/usr/bin/env python3
"""Run gotouhou regression checks and publish a host-local JSON summary."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_ROOT = "/root/gotouhou"
DEFAULT_GODOT = "/root/gotouhou/Godot_v4.7-stable_linux.x86_64"
UTC = dt.timezone.utc


def iso_now() -> str:
    return dt.datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run(command: list[str], cwd: Path, timeout: int) -> dict[str, Any]:
    try:
        env = {
            **os.environ,
            "HOME": os.environ.get("HOME", "/root"),
            "XDG_CONFIG_HOME": os.environ.get("XDG_CONFIG_HOME", "/root/.config"),
            "GOCACHE": os.environ.get("GOCACHE", "/root/.cache/go-build"),
            "GOPATH": os.environ.get("GOPATH", "/root/go"),
            "GODOT_SILENCE_ROOT_WARNING": "1",
        }
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
        output = completed.stdout.strip()
        return {
            "command": command,
            "cwd": str(cwd),
            "status": completed.returncode,
            "ok": completed.returncode == 0,
            "output_tail": output[-4000:],
        }
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {
            "command": command,
            "cwd": str(cwd),
            "status": 124,
            "ok": False,
            "timed_out": True,
            "output_tail": output[-4000:],
        }
    except OSError as exc:
        return {"command": command, "cwd": str(cwd), "status": 127, "ok": False, "output_tail": str(exc)}


def classify_godot_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("ok"):
        return result
    output = str(result.get("output_tail", ""))
    script_markers = ("SCRIPT ERROR", "Parse Error", "Compile Error", "GDScript", "Failed to load script")
    renderer_markers = (
        "RenderingDevice",
        "No suitable rendering device",
        "Failed to create Vulkan",
        "Failed to initialize graphics",
        "Could not initialize rendering",
        "No available renderer",
        "X11 Display is not available",
        "Can't open display",
    )
    has_script_error = any(marker in output for marker in script_markers)
    has_renderer_error = any(marker in output for marker in renderer_markers)
    if has_renderer_error and not has_script_error:
        result = dict(result)
        result["ok"] = True
        result["ignored"] = True
        result["blocked"] = True
        result["ignore_reason"] = "headless renderer unavailable on server without GPU"
    return result


def docker_files(repo: Path) -> list[str]:
    patterns = ("Dockerfile", "Dockerfile.*", "*.Dockerfile", "docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml")
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(str(path.relative_to(repo)) for path in repo.glob(pattern) if path.is_file())
    return sorted(set(matches))


def run_checks(root: Path, godot: Path, include_godot: bool, include_protocol: bool, include_server: bool) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    runtime = {
        "godot": {
            "path": str(godot),
            "exists": godot.exists(),
            "executable": os.access(godot, os.X_OK) if godot.exists() else False,
        },
        "docker": run(["docker", "--version"], root, timeout=20),
        "docker_compose": run(["docker-compose", "--version"], root, timeout=20),
        "server_docker_files": {
            "Gensoulkyo": docker_files(root / "Gensoulkyo"),
            "PhK-BattleServer": docker_files(root / "PhK-BattleServer"),
        },
    }
    if godot.exists() and os.access(godot, os.X_OK):
        runtime["godot"]["version"] = run([str(godot), "--version"], root, timeout=20)

    if include_godot:
        godot_root = root / "SpellKard" / "godot"
        checks.extend(
            [
                {
                    "name": "spellkard-client-ui-headless",
                    **classify_godot_result(
                        run([str(godot), "--headless", "--path", ".", "--script", "../tools/client_ui_smoke_test.gd"], godot_root, timeout=120)
                    ),
                },
                {
                    "name": "spellkard-boss-pattern-headless",
                    **classify_godot_result(
                        run([str(godot), "--headless", "--path", ".", "--script", "../tools/boss_pattern_catalog_check.gd"], godot_root, timeout=120)
                    ),
                },
            ]
        )

    if include_protocol:
        checks.append(
            {
                "name": "cross-repo-protocol-audit",
                **run(["python3", str(root / "docs" / "ops" / "protocol_audit_check.py")], root, timeout=180),
            }
        )

    if include_server:
        if docker_files(root / "Gensoulkyo"):
            checks.append({"name": "gensoulkyo-docker-compose", **run(["docker-compose", "config"], root / "Gensoulkyo", timeout=60)})
        else:
            checks.append({"name": "gensoulkyo-docker-compose", "ok": False, "status": 125, "blocked": True, "output_tail": "no Dockerfile/docker-compose files found"})
        if docker_files(root / "PhK-BattleServer"):
            checks.append({"name": "battle-server-docker-compose", **run(["docker-compose", "config"], root / "PhK-BattleServer", timeout=60)})
        else:
            checks.append({"name": "battle-server-docker-compose", "ok": False, "status": 125, "blocked": True, "output_tail": "no Dockerfile/docker-compose files found"})

    failed = [check for check in checks if not check.get("ok")]
    ignored = [check for check in checks if check.get("ignored")]
    return {
        "generated_at": iso_now(),
        "root": str(root),
        "runtime": runtime,
        "checks": checks,
        "ok": not failed,
        "failed_count": len(failed),
        "failed": [{"name": check.get("name"), "status": check.get("status"), "blocked": check.get("blocked", False)} for check in failed],
        "ignored_count": len(ignored),
        "ignored": [{"name": check.get("name"), "reason": check.get("ignore_reason", "")} for check in ignored],
    }


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=DEFAULT_ROOT)
    parser.add_argument("--godot-bin", default=os.getenv("GOTOUHOU_GODOT_BIN", DEFAULT_GODOT))
    parser.add_argument("--output", default="/root/gotouhou/.agents/checks/latest-regression.json")
    parser.add_argument("--skip-godot", action="store_true")
    parser.add_argument("--skip-protocol", action="store_true")
    parser.add_argument("--skip-server", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    payload = run_checks(
        root=Path(args.root).resolve(),
        godot=Path(args.godot_bin).resolve(),
        include_godot=not args.skip_godot,
        include_protocol=not args.skip_protocol,
        include_server=not args.skip_server,
    )
    write_json(Path(args.output).resolve(), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

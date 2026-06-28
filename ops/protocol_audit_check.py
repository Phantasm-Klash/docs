#!/usr/bin/env python3
"""Run local cross-repository protocol and network contract checks."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


CHECKS = (
    ("PhK-Protocol", ["python3", "tools/check_protocol.py"]),
    ("Gensoulkyo", ["go", "test", "./runtime/...", "./cmd/gensoulkyo_nakama"]),
    ("PhK-BattleServer", ["python3", "tools/check_battle_server.py"]),
)

REQUIRED_SHARED_MESSAGES = {
    "BusinessSecureEnvelope": {"version", "session_id", "seq", "timestamp_ms", "nonce", "op_code", "key_id", "auth_tag"},
    "BattleTicket": {"match_id", "user_id", "player_id", "mode_id", "battle_server_id", "endpoint", "ruleset_version", "expires_at_ms"},
    "BattlePacketHeader": {"match_id", "player_id", "tick", "seq", "ack", "payload_type", "key_id", "nonce"},
    "BattleInput": {"match_id", "player_id", "tick", "seq", "direction_bits", "slow", "shoot", "bomb", "card_slot"},
    "BattleResult": {"match_id", "mode_id", "result_hash", "replay_id", "player_ids", "settled_at_ms"},
}


def run(root: Path, repo: str, command: list[str]) -> int:
    cwd = root / repo
    print(f"## {repo}: {' '.join(command)}", flush=True)
    if not cwd.exists():
        print(f"missing repository path: {cwd}", file=sys.stderr)
        return 1
    completed = subprocess.run(command, cwd=str(cwd), text=True)
    print("", flush=True)
    return completed.returncode


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_json(path: Path) -> object:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def descriptor_messages(descriptor: dict[str, object]) -> dict[str, set[str]]:
    messages: dict[str, set[str]] = {}
    for proto_file in descriptor.get("files", []):
        if not isinstance(proto_file, dict):
            continue
        for message in proto_file.get("messages", []):
            if not isinstance(message, dict):
                continue
            fields = {
                str(field.get("name", ""))
                for field in message.get("fields", [])
                if isinstance(field, dict) and field.get("name")
            }
            messages[str(message.get("name", ""))] = fields
    return messages


def parse_go_constants(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    constants: dict[str, str] = {}
    for name, raw_value, int_value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*(?:(\"(?:\\.|[^\"])*\")|([0-9]+))", text):
        constants[name] = json.loads(raw_value) if raw_value else int_value
    return constants


def check_battle_result_callback_contract(
    errors: list[str],
    fixture_path: Path,
    go_constants: dict[str, str],
    cpp_manifest: str,
    gensoul_service_test: Path,
    battle_server_tests: Path,
) -> None:
    fixture = load_json(fixture_path)
    if not isinstance(fixture, dict):
        fail(errors, "PhK-Protocol fixture is not a JSON object")
        return
    callback = fixture.get("signed_battle_result_callback")
    if not isinstance(callback, dict):
        fail(errors, "PhK-Protocol fixture missing signed_battle_result_callback")
        return
    result = callback.get("result")
    if not isinstance(result, dict):
        fail(errors, "PhK-Protocol signed battle result callback missing result object")
        result = {}

    expected = {
        "BattleResultCallbackMatchID": str(result.get("match_id", "")),
        "BattleResultCallbackModeID": str(result.get("mode_id", "")),
        "BattleResultCallbackResultHash": str(result.get("result_hash", "")),
        "BattleResultCallbackReplayID": str(result.get("replay_id", "")),
        "BattleResultCallbackRewardProjectionJSON": str(result.get("reward_projection_json", "")),
        "BattleResultCallbackModeResultJSON": str(result.get("mode_result_json", "")),
        "BattleResultCallbackSignatureAlg": str(callback.get("signature_alg", "")),
        "BattleResultCallbackKeyID": str(callback.get("key_id", "")),
        "BattleResultCallbackPublicKeyHex": str(callback.get("public_key_hex", "")),
        "BattleResultCallbackSignatureHex": str(callback.get("signature_hex", "")),
        "BattleResultCallbackSubmitPath": str(callback.get("submit_path", "")),
        "BattleResultCallbackSettlementKey": str(callback.get("settlement_key", "")),
        "BattleResultCallbackSettledAtMS": str(result.get("settled_at_ms", "")),
    }
    cpp_names = {
        "BattleResultCallbackMatchID": "kBattleResultCallbackMatchId",
        "BattleResultCallbackModeID": "kBattleResultCallbackModeId",
        "BattleResultCallbackResultHash": "kBattleResultCallbackResultHash",
        "BattleResultCallbackReplayID": "kBattleResultCallbackReplayId",
        "BattleResultCallbackRewardProjectionJSON": "kBattleResultCallbackRewardProjectionJson",
        "BattleResultCallbackModeResultJSON": "kBattleResultCallbackModeResultJson",
        "BattleResultCallbackSignatureAlg": "kBattleResultCallbackSignatureAlg",
        "BattleResultCallbackKeyID": "kBattleResultCallbackKeyId",
        "BattleResultCallbackPublicKeyHex": "kBattleResultCallbackPublicKeyHex",
        "BattleResultCallbackSignatureHex": "kBattleResultCallbackSignatureHex",
        "BattleResultCallbackSubmitPath": "kBattleResultCallbackSubmitPath",
        "BattleResultCallbackSettlementKey": "kBattleResultCallbackSettlementKey",
        "BattleResultCallbackSettledAtMS": "kBattleResultCallbackSettledAtMs",
    }
    for go_name, value in expected.items():
        actual = go_constants.get(go_name, "")
        if actual != value:
            fail(errors, f"Go manifest {go_name}={actual!r} does not match callback fixture {value!r}")
        cpp_name = cpp_names[go_name]
        quoted = f"{cpp_name} = {json.dumps(value, ensure_ascii=True)}"
        numeric = f"{cpp_name} = {value}"
        if quoted not in cpp_manifest and numeric not in cpp_manifest:
            fail(errors, f"C++ manifest {cpp_name} does not match callback fixture {value!r}")

    gensoul_test = gensoul_service_test.read_text(encoding="utf-8")
    for token in [
        "phkv1.BattleResultCallbackResultHash",
        "phkv1.BattleResultCallbackReplayID",
        "phkv1.BattleResultCallbackRewardProjectionJSON",
        "phkv1.BattleResultCallbackModeResultJSON",
        "phkv1.BattleResultCallbackSettledAtMS",
        "phkv1.BattleResultCallbackSignatureAlg",
        "phkv1.BattleResultCallbackSignatureHex",
        "phkv1.BattleResultCallbackPublicKeyHex",
    ]:
        if token not in gensoul_test:
            fail(errors, f"Gensoulkyo signed battle result test missing shared callback constant {token}")

    battle_test = battle_server_tests.read_text(encoding="utf-8")
    for token in [
        "phk::v1::kBattleResultCallbackMatchId",
        "phk::v1::kBattleResultCallbackModeId",
        "phk::v1::kBattleResultCallbackResultHash",
        "phk::v1::kBattleResultCallbackReplayId",
        "phk::v1::kBattleResultCallbackRewardProjectionJson",
        "phk::v1::kBattleResultCallbackModeResultJson",
        "phk::v1::kBattleResultCallbackSettledAtMs",
        "phk::v1::kBattleResultCallbackKeyId",
        "phk::v1::kBattleResultCallbackPublicKeyHex",
        "phk::v1::kBattleResultCallbackSignatureHex",
        "phk::v1::kBattleResultCallbackSettlementKey",
    ]:
        if token not in battle_test:
            fail(errors, f"PhK-BattleServer tests missing shared callback constant {token}")


def check_cross_repo_contract(root: Path) -> int:
    errors: list[str] = []
    protocol_root = root / "PhK-Protocol"
    spell_root = root / "SpellKard"
    gensoul_root = root / "Gensoulkyo"
    battle_root = root / "PhK-BattleServer"

    descriptor_path = protocol_root / "descriptors" / "phk_v1_descriptor.json"
    fixture_path = protocol_root / "fixtures" / "v0_1_minimal_flow.json"
    go_manifest_path = protocol_root / "gen" / "go" / "phk" / "v1" / "manifest.go"
    cpp_manifest_path = protocol_root / "gen" / "cpp" / "phk" / "v1" / "manifest.hpp"
    spell_descriptor_model = spell_root / "godot" / "scripts" / "protocol_descriptor_model.gd"
    gensoul_go_mod = gensoul_root / "go.mod"
    gensoul_contract_test = gensoul_root / "runtime" / "core" / "protocol_contract_test.go"
    gensoul_service_test = gensoul_root / "runtime" / "core" / "service_test.go"
    battle_version = battle_root / "include" / "phk" / "battle" / "version.hpp"
    battle_server_tests = battle_root / "tests" / "battle_server_tests.cpp"

    descriptor = load_json(descriptor_path)
    if not isinstance(descriptor, dict):
        fail(errors, "PhK-Protocol descriptor is not a JSON object")
        descriptor = {}
    descriptor_constants = {
        "ProtocolVersion": str(descriptor.get("protocol_version", "")),
        "BusinessAPIVersion": str(descriptor.get("business_api_version", "")),
        "BattleAPIVersion": str(descriptor.get("battle_api_version", "")),
        "RulesetVersion": str(descriptor.get("ruleset_version", "")),
        "RulesetHash": str(descriptor.get("ruleset_hash", "")),
        "SourceDigestSHA256": str(descriptor.get("source_digest_sha256", "")),
    }
    go_constants = parse_go_constants(go_manifest_path)
    go_manifest = go_manifest_path.read_text(encoding="utf-8")
    for name, expected in descriptor_constants.items():
        actual = go_constants.get(name, "")
        if actual != expected:
            fail(errors, f"Go manifest {name}={actual!r} does not match descriptor {expected!r}")

    cpp_manifest = cpp_manifest_path.read_text(encoding="utf-8")
    cpp_constant_map = {
        "kProtocolVersion": descriptor_constants["ProtocolVersion"],
        "kBusinessApiVersion": descriptor_constants["BusinessAPIVersion"],
        "kBattleApiVersion": descriptor_constants["BattleAPIVersion"],
        "kRulesetVersion": descriptor_constants["RulesetVersion"],
        "kRulesetHash": descriptor_constants["RulesetHash"],
        "kSourceDigestSha256": descriptor_constants["SourceDigestSHA256"],
    }
    for name, expected in cpp_constant_map.items():
        quoted = f'{name} = "{expected}"'
        numeric = f"{name} = {expected}"
        if quoted not in cpp_manifest and numeric not in cpp_manifest:
            fail(errors, f"C++ manifest {name} does not match descriptor {expected!r}")
    check_battle_result_callback_contract(
        errors,
        fixture_path,
        go_constants,
        cpp_manifest,
        gensoul_service_test,
        battle_server_tests,
    )

    messages = descriptor_messages(descriptor)
    for message, fields in REQUIRED_SHARED_MESSAGES.items():
        actual_fields = messages.get(message, set())
        missing = fields - actual_fields
        if missing:
            fail(errors, f"descriptor missing fields for {message}: {sorted(missing)}")
        for field in fields:
            if f'"{message}":' not in go_manifest or f'"{field}"' not in go_manifest:
                fail(errors, f"Go manifest may be missing {message}.{field}")
            if f'{{"{message}", "{field}"}}' not in cpp_manifest:
                fail(errors, f"C++ manifest missing {message}.{field}")

    spell_text = spell_descriptor_model.read_text(encoding="utf-8")
    if "PhK-Protocol/descriptors/phk_v1_descriptor.json" not in spell_text:
        fail(errors, "SpellKard ProtocolDescriptorModel is not pointed at PhK-Protocol descriptor")
    for message in ["BusinessSecureEnvelope", "BattleTicket", "BattlePacketHeader", "BattleInput", "BattleResult"]:
        if message not in spell_text:
            fail(errors, f"SpellKard minimal descriptor validation missing {message}")

    go_mod = gensoul_go_mod.read_text(encoding="utf-8")
    if "github.com/phantasm-klash/phk-protocol" not in go_mod or "../PhK-Protocol" not in go_mod:
        fail(errors, "Gensoulkyo go.mod is not wired to local PhK-Protocol replace")
    gensoul_test = gensoul_contract_test.read_text(encoding="utf-8")
    for constant in ["ProtocolVersion", "BusinessAPIVersion", "BattleAPIVersion", "RulesetVersion"]:
        if constant not in gensoul_test:
            fail(errors, f"Gensoulkyo protocol contract test missing {constant}")

    battle_text = battle_version.read_text(encoding="utf-8")
    for token in ["phk/v1/manifest.hpp", "phk::v1::kProtocolVersion", "phk::v1::kBattleApiVersion", "phk::v1::kRulesetVersion"]:
        if token not in battle_text:
            fail(errors, f"PhK-BattleServer version boundary missing {token}")

    if errors:
        for error in errors:
            print(f"cross-repo contract failed: {error}", file=sys.stderr)
        return 1
    print("cross-repo contract ok")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    failures = 0
    for repo, command in CHECKS:
        if run(root, repo, command) != 0:
            failures += 1
    if check_cross_repo_contract(root) != 0:
        failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

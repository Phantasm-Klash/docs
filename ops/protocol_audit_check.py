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
    "BattleInput": {"match_id", "player_id", "tick", "seq", "direction_bits", "slow", "shoot", "bomb", "card_slot", "mode_action_id"},
    "BattleModeAction": {"match_id", "player_id", "tick", "seq", "action_id", "action_type", "payload_json", "client_result_authoritative"},
    "BattleSnapshot": {"match_id", "snapshot_tick", "snapshot_kind", "state_hash", "players", "bullets_delta", "mode_state", "event_cursor"},
    "BattleEvent": {"match_id", "cursor", "tick", "type", "player_id", "payload_json", "server_authoritative"},
    "BattleResult": {"match_id", "mode_id", "result_hash", "replay_id", "player_ids", "settled_at_ms"},
}

GOLDEN_REPLAY_SUMMARY_FIELDS = (
    "replay_id",
    "match_id",
    "owner_user_id",
    "input_count",
    "event_count",
    "input_stream_hash",
    "event_stream_hash",
    "final_state_hash",
    "final_tick",
)


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
    for name, raw_value in re.findall(r"\b([A-Za-z][A-Za-z0-9_]*)\s*=\s*(\"(?:\\.|[^\"])*\"|[0-9]+|true|false)", text):
        constants[name] = json.loads(raw_value) if raw_value.startswith('"') else raw_value
    return constants


def fixture_scalar(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def cpp_constant_matches(cpp_manifest: str, cpp_name: str, value: str) -> bool:
    quoted = f"{cpp_name} = {json.dumps(value, ensure_ascii=True)}"
    literal = f"{cpp_name} = {value}"
    return quoted in cpp_manifest or literal in cpp_manifest


def go_const_suffix(field_name: str) -> str:
    parts = field_name.split("_")
    converted: list[str] = []
    for part in parts:
        if part == "id":
            converted.append("ID")
        elif part == "json":
            converted.append("JSON")
        elif part == "ms":
            converted.append("MS")
        else:
            converted.append(part[:1].upper() + part[1:])
    return "".join(converted)


def cpp_const_suffix(field_name: str) -> str:
    parts = field_name.split("_")
    return "".join(part[:1].upper() + part[1:] for part in parts)


def gdscript_function(text: str, name: str) -> str:
    marker = f"func {name}("
    start = text.find(marker)
    if start < 0:
        return ""
    next_func = text.find("\nfunc ", start + len(marker))
    if next_func < 0:
        return text[start:]
    return text[start:next_func]


def require_tokens(errors: list[str], text: str, tokens: list[str], label: str) -> None:
    for token in tokens:
        if token not in text:
            fail(errors, f"{label} missing {token}")


def check_golden_replay_summary_contract(
    errors: list[str],
    fixture_path: Path,
    go_constants: dict[str, str],
    cpp_manifest: str,
    gensoul_contract_test: Path,
    gensoul_service_test: Path,
    battle_server_tests: Path,
) -> None:
    fixture = load_json(fixture_path)
    if not isinstance(fixture, dict):
        fail(errors, "PhK-Protocol fixture is not a JSON object")
        return
    summary = fixture.get("golden_replay_summary")
    if not isinstance(summary, dict):
        fail(errors, "PhK-Protocol fixture missing golden_replay_summary")
        return

    expected: dict[str, str] = {}
    for field in GOLDEN_REPLAY_SUMMARY_FIELDS:
        if field not in summary:
            fail(errors, f"PhK-Protocol golden_replay_summary missing {field}")
            continue
        expected[field] = fixture_scalar(summary.get(field))

    for field, value in expected.items():
        go_name = f"GoldenReplaySummary{go_const_suffix(field)}"
        actual = go_constants.get(go_name, "")
        if actual != value:
            fail(errors, f"Go manifest {go_name}={actual!r} does not match golden replay summary fixture {value!r}")
        cpp_name = f"kGoldenReplaySummary{cpp_const_suffix(field)}"
        if not cpp_constant_matches(cpp_manifest, cpp_name, value):
            fail(errors, f"C++ manifest {cpp_name} does not match golden replay summary fixture {value!r}")

    for hash_field in ("input_stream_hash", "event_stream_hash", "final_state_hash"):
        if hash_field in expected and not expected[hash_field].startswith("sha256:"):
            fail(errors, f"golden_replay_summary {hash_field} must be sha256-prefixed")

    gensoul_contract = gensoul_contract_test.read_text(encoding="utf-8")
    for field in GOLDEN_REPLAY_SUMMARY_FIELDS:
        token = f"phkv1.GoldenReplaySummary{go_const_suffix(field)}"
        if token not in gensoul_contract:
            fail(errors, f"Gensoulkyo protocol contract test missing golden replay summary constant {token}")

    gensoul_service = gensoul_service_test.read_text(encoding="utf-8")
    for field in GOLDEN_REPLAY_SUMMARY_FIELDS:
        token = f"phkv1.GoldenReplaySummary{go_const_suffix(field)}"
        if token not in gensoul_service:
            fail(errors, f"Gensoulkyo service tests missing golden replay summary constant {token}")

    battle_test = battle_server_tests.read_text(encoding="utf-8")
    for field in GOLDEN_REPLAY_SUMMARY_FIELDS:
        token = f"phk::v1::kGoldenReplaySummary{cpp_const_suffix(field)}"
        if token not in battle_test:
            fail(errors, f"PhK-BattleServer tests missing golden replay summary constant {token}")


def check_battle_snapshot_event_contract(
    errors: list[str],
    fixture_path: Path,
    go_constants: dict[str, str],
    cpp_manifest: str,
    gensoul_contract_test: Path,
    gensoul_service_test: Path,
    battle_server_tests: Path,
) -> None:
    fixture = load_json(fixture_path)
    if not isinstance(fixture, dict):
        fail(errors, "PhK-Protocol fixture is not a JSON object")
        return
    snapshot = fixture.get("battle_snapshot")
    if not isinstance(snapshot, dict):
        fail(errors, "PhK-Protocol fixture missing battle_snapshot")
        snapshot = {}
    event = fixture.get("battle_event")
    if not isinstance(event, dict):
        fail(errors, "PhK-Protocol fixture missing battle_event")
        event = {}

    expected = {
        "BattleSnapshotMatchID": fixture_scalar(snapshot.get("match_id", "")),
        "BattleSnapshotSnapshotTick": fixture_scalar(snapshot.get("snapshot_tick", "")),
        "BattleSnapshotSnapshotKind": fixture_scalar(snapshot.get("snapshot_kind", "")),
        "BattleSnapshotStateHash": fixture_scalar(snapshot.get("state_hash", "")),
        "BattleSnapshotEventCursor": fixture_scalar(snapshot.get("event_cursor", "")),
        "BattleEventMatchID": fixture_scalar(event.get("match_id", "")),
        "BattleEventCursor": fixture_scalar(event.get("cursor", "")),
        "BattleEventTick": fixture_scalar(event.get("tick", "")),
        "BattleEventType": fixture_scalar(event.get("type", "")),
        "BattleEventServerAuthoritative": fixture_scalar(event.get("server_authoritative", "")),
    }
    cpp_names = {
        "BattleSnapshotMatchID": "kBattleSnapshotMatchId",
        "BattleSnapshotSnapshotTick": "kBattleSnapshotSnapshotTick",
        "BattleSnapshotSnapshotKind": "kBattleSnapshotSnapshotKind",
        "BattleSnapshotStateHash": "kBattleSnapshotStateHash",
        "BattleSnapshotEventCursor": "kBattleSnapshotEventCursor",
        "BattleEventMatchID": "kBattleEventMatchId",
        "BattleEventCursor": "kBattleEventCursor",
        "BattleEventTick": "kBattleEventTick",
        "BattleEventType": "kBattleEventType",
        "BattleEventServerAuthoritative": "kBattleEventServerAuthoritative",
    }
    for go_name, value in expected.items():
        actual = go_constants.get(go_name, "")
        if actual != value:
            fail(errors, f"Go manifest {go_name}={actual!r} does not match snapshot/event fixture {value!r}")
        cpp_name = cpp_names[go_name]
        if not cpp_constant_matches(cpp_manifest, cpp_name, value):
            fail(errors, f"C++ manifest {cpp_name} does not match snapshot/event fixture {value!r}")

    if event.get("server_authoritative") is not True:
        fail(errors, "battle_event fixture must be server authoritative")
    if not str(snapshot.get("state_hash", "")).startswith("sha256:"):
        fail(errors, "battle_snapshot fixture state_hash must be sha256-prefixed")

    gensoul_contract = gensoul_contract_test.read_text(encoding="utf-8")
    for token in [
        "phkv1.BattleSnapshotMatchID",
        "phkv1.BattleSnapshotSnapshotTick",
        "phkv1.BattleSnapshotSnapshotKind",
        "phkv1.BattleSnapshotStateHash",
        "phkv1.BattleSnapshotEventCursor",
        "phkv1.BattleEventMatchID",
        "phkv1.BattleEventCursor",
        "phkv1.BattleEventTick",
        "phkv1.BattleEventType",
        "phkv1.BattleEventServerAuthoritative",
    ]:
        if token not in gensoul_contract:
            fail(errors, f"Gensoulkyo protocol contract test missing shared snapshot/event constant {token}")

    gensoul_service = gensoul_service_test.read_text(encoding="utf-8")
    for token in [
        "phkv1.BattleSnapshotStateHash",
        "phkv1.BattleSnapshotEventCursor",
        "phkv1.BattleEventType",
        "phkv1.BattleEventServerAuthoritative",
    ]:
        if token not in gensoul_service:
            fail(errors, f"Gensoulkyo service tests missing shared snapshot/event constant {token}")

    battle_test = battle_server_tests.read_text(encoding="utf-8")
    for token in [
        "phk::v1::kBattleSnapshotMatchId",
        "phk::v1::kBattleSnapshotSnapshotTick",
        "phk::v1::kBattleSnapshotSnapshotKind",
        "phk::v1::kBattleSnapshotStateHash",
        "phk::v1::kBattleSnapshotEventCursor",
        "phk::v1::kBattleEventMatchId",
        "phk::v1::kBattleEventCursor",
        "phk::v1::kBattleEventTick",
        "phk::v1::kBattleEventType",
        "phk::v1::kBattleEventServerAuthoritative",
    ]:
        if token not in battle_test:
            fail(errors, f"PhK-BattleServer tests missing shared snapshot/event constant {token}")


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
        if not cpp_constant_matches(cpp_manifest, cpp_name, value):
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


def check_battle_mode_action_contract(
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
    mode_action = fixture.get("battle_mode_action")
    if not isinstance(mode_action, dict):
        fail(errors, "PhK-Protocol fixture missing battle_mode_action")
        return
    expected = {
        "BattleModeActionMatchID": str(mode_action.get("match_id", "")),
        "BattleModeActionPlayerID": str(mode_action.get("player_id", "")),
        "BattleModeActionActionID": str(mode_action.get("action_id", "")),
        "BattleModeActionActionType": str(mode_action.get("action_type", "")),
        "BattleModeActionPayloadJSON": str(mode_action.get("payload_json", "")),
        "BattleModeActionTick": str(mode_action.get("tick", "")),
        "BattleModeActionSeq": str(mode_action.get("seq", "")),
    }
    cpp_names = {
        "BattleModeActionMatchID": "kBattleModeActionMatchId",
        "BattleModeActionPlayerID": "kBattleModeActionPlayerId",
        "BattleModeActionActionID": "kBattleModeActionActionId",
        "BattleModeActionActionType": "kBattleModeActionActionType",
        "BattleModeActionPayloadJSON": "kBattleModeActionPayloadJson",
        "BattleModeActionTick": "kBattleModeActionTick",
        "BattleModeActionSeq": "kBattleModeActionSeq",
    }
    for go_name, value in expected.items():
        actual = go_constants.get(go_name, "")
        if actual != value:
            fail(errors, f"Go manifest {go_name}={actual!r} does not match mode action fixture {value!r}")
        cpp_name = cpp_names[go_name]
        if not cpp_constant_matches(cpp_manifest, cpp_name, value):
            fail(errors, f"C++ manifest {cpp_name} does not match mode action fixture {value!r}")
    if mode_action.get("client_result_authoritative", True):
        fail(errors, "battle_mode_action fixture must not be client result authoritative")

    gensoul_test = gensoul_service_test.read_text(encoding="utf-8")
    for token in [
        "phkv1.BattleModeActionPayloadJSON",
        "phkv1.BattleModeActionActionType",
    ]:
        if token not in gensoul_test:
            fail(errors, f"Gensoulkyo mode action test missing shared fixture constant {token}")

    battle_test = battle_server_tests.read_text(encoding="utf-8")
    for token in [
        "phk::v1::kBattleModeActionMatchId",
        "phk::v1::kBattleModeActionPlayerId",
        "phk::v1::kBattleModeActionSeq",
        "phk::v1::kBattleModeActionTick",
        "phk::v1::kBattleModeActionActionId",
        "phk::v1::kBattleModeActionActionType",
        "phk::v1::kBattleModeActionPayloadJson",
    ]:
        if token not in battle_test:
            fail(errors, f"PhK-BattleServer mode action test missing shared fixture constant {token}")


def check_spellkard_mode_action_client_builder(
    errors: list[str],
    battle_network_client: Path,
    api_model: Path,
    game_mode_model: Path,
    http_client: Path,
    main_script: Path,
) -> None:
    battle_network_text = battle_network_client.read_text(encoding="utf-8")
    build_mode_action = gdscript_function(battle_network_text, "build_mode_action")
    if not build_mode_action:
        fail(errors, "SpellKard BattleNetworkClientModel missing build_mode_action")
    else:
        require_tokens(
            errors,
            build_mode_action,
            [
                'build_packet_header("mode_action", tick, ack)',
                '"match_id": match_id',
                '"player_id": player_id',
                '"action_id": normalized_action_id',
                '"action_type": normalized_action_type',
                '"payload_json": JSON.stringify(payload.duplicate(true))',
                '"seq": action_seq',
                '"client_result_authoritative": false',
            ],
            "SpellKard battle network mode action builder",
        )

    api_text = api_model.read_text(encoding="utf-8")
    mode_action_request = gdscript_function(api_text, "mode_action_request")
    if not mode_action_request:
        fail(errors, "SpellKard GensoulkyoAPIModel missing mode_action_request builder")
    else:
        require_tokens(
            errors,
            mode_action_request,
            [
                'payload_value: Variant = action_request.get("payload", {})',
                "payload = (payload_value as Dictionary).duplicate(true)",
                '"mode_id": String(action_request.get("mode_id", current_mode_id))',
                '"action_type": String(action_request.get("action_type", ""))',
                '"payload": payload',
                '"client_result_authoritative": false',
                '"/v1/matches/%s/mode-action"',
                '"match_mode_action"',
            ],
            "SpellKard mode action request builder",
        )

    apply_mode_action_response = gdscript_function(api_text, "apply_mode_action_response")
    if not apply_mode_action_response:
        fail(errors, "SpellKard GensoulkyoAPIModel missing apply_mode_action_response")
    else:
        require_tokens(
            errors,
            apply_mode_action_response,
            [
                'var accepted := bool(response.get("accepted", false))',
                '"server_authoritative": bool(response.get("server_authoritative", false))',
                '"client_result_authoritative": bool(response.get("client_result_authoritative", true))',
                'game_mode_model.apply_server_mode_action_response(response)',
            ],
            "SpellKard mode action response projection",
        )

    game_mode_text = game_mode_model.read_text(encoding="utf-8")
    record_mode_action = gdscript_function(game_mode_text, "_record_mode_action")
    if not record_mode_action:
        fail(errors, "SpellKard GameModeModel missing _record_mode_action builder")
    else:
        require_tokens(
            errors,
            record_mode_action,
            [
                '"mode_id": mode_id',
                '"action_type": action_type',
                '"payload": payload.duplicate(true)',
                '"client_result_authoritative": false',
                "mode_action_requests.append(request)",
            ],
            "SpellKard game mode action builder",
        )

    http_text = http_client.read_text(encoding="utf-8")
    submit_mode_action = gdscript_function(http_text, "submit_mode_action")
    if not submit_mode_action:
        fail(errors, "SpellKard GensoulkyoHTTPClient missing submit_mode_action")
    else:
        require_tokens(
            errors,
            submit_mode_action,
            ["api_model.mode_action_request(target_match_id, action_request)", "send_and_apply"],
            "SpellKard mode action HTTP submit path",
        )

    main_text = main_script.read_text(encoding="utf-8")
    main_submit_mode_action = gdscript_function(main_text, "_gensoulkyo_submit_mode_action")
    if not main_submit_mode_action:
        fail(errors, "SpellKard main script missing _gensoulkyo_submit_mode_action")
    else:
        require_tokens(
            errors,
            main_submit_mode_action,
            ["gensoulkyo_http_client.submit_mode_action(target_match_id, action_request)", "_update_ui_overlay()"],
            "SpellKard mode action UI submit path",
        )


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
    spell_battle_network_client = spell_root / "godot" / "scripts" / "battle_network_client_model.gd"
    spell_api_model = spell_root / "godot" / "scripts" / "gensoulkyo_api_model.gd"
    spell_game_mode_model = spell_root / "godot" / "scripts" / "game_mode_model.gd"
    spell_http_client = spell_root / "godot" / "scripts" / "gensoulkyo_http_client.gd"
    spell_main = spell_root / "godot" / "scripts" / "main.gd"
    gensoul_go_mod = gensoul_root / "go.mod"
    gensoul_contract_test = gensoul_root / "runtime" / "core" / "protocol_contract_test.go"
    gensoul_service_test = gensoul_root / "runtime" / "core" / "service_test.go"
    battle_version = battle_root / "include" / "phk" / "battle" / "version.hpp"
    battle_simulation = battle_root / "include" / "phk" / "battle" / "simulation.hpp"
    battle_server = battle_root / "include" / "phk" / "battle" / "server.hpp"
    battle_simulation_impl = battle_root / "src" / "simulation.cpp"
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
    check_battle_mode_action_contract(
        errors,
        fixture_path,
        go_constants,
        cpp_manifest,
        gensoul_service_test,
        battle_server_tests,
    )
    check_battle_snapshot_event_contract(
        errors,
        fixture_path,
        go_constants,
        cpp_manifest,
        gensoul_contract_test,
        gensoul_service_test,
        battle_server_tests,
    )
    check_golden_replay_summary_contract(
        errors,
        fixture_path,
        go_constants,
        cpp_manifest,
        gensoul_contract_test,
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
    for message in ["BusinessSecureEnvelope", "BattleTicket", "BattlePacketHeader", "BattleInput", "BattleModeAction", "BattleResult"]:
        if message not in spell_text:
            fail(errors, f"SpellKard minimal descriptor validation missing {message}")
    for token in ["BATTLE_PAYLOAD_TYPE_MODE_ACTION", "mode_action_field_missing"]:
        if token not in spell_text:
            fail(errors, f"SpellKard protocol descriptor mode action gate missing {token}")
    spell_api_text = spell_api_model.read_text(encoding="utf-8")
    for token in ["mode_action_request", '"client_result_authoritative": false']:
        if token not in spell_api_text:
            fail(errors, f"SpellKard mode action request authority guard missing {token}")
    check_spellkard_mode_action_client_builder(
        errors,
        spell_battle_network_client,
        spell_api_model,
        spell_game_mode_model,
        spell_http_client,
        spell_main,
    )

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
    battle_test = battle_server_tests.read_text(encoding="utf-8")
    for token in ["BattlePayloadType::ModeAction", "mode_action_empty_payload", "PayloadTypeName(phk::battle::BattlePayloadType::ModeAction)"]:
        if token not in battle_test:
            fail(errors, f"PhK-BattleServer mode action dispatch coverage missing {token}")
    battle_simulation_text = battle_simulation.read_text(encoding="utf-8")
    battle_server_text = battle_server.read_text(encoding="utf-8")
    battle_simulation_impl_text = battle_simulation_impl.read_text(encoding="utf-8")
    for token in ["ValidateModeAction", "AcceptModeAction", "InvalidModeAction"]:
        if token not in battle_simulation_text:
            fail(errors, f"PhK-BattleServer simulation mode action boundary missing {token}")
    if "AcceptModeAction" not in battle_server_text:
        fail(errors, "PhK-BattleServer facade missing AcceptModeAction")
    for token in ["mode_action_client_result_forbidden", "AccumulateAcceptedModeAction", "event_stream_hash_"]:
        if token not in battle_simulation_impl_text:
            fail(errors, f"PhK-BattleServer simulation mode action implementation missing {token}")

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

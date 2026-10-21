#!/usr/bin/env python3
"""Build an immutable Tonghuashun action manifest from frozen decisions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from validate_classification import Checks, validate_classification, source_groups, target_groups


TZ = ZoneInfo("Asia/Shanghai")
ALLOWED_ACTIONS = {"add", "move", "remove", "propose_group", "none"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def is_st(name: str) -> bool:
    value = re.sub(r"\s+", "", name).upper()
    return value.startswith("ST") or value.startswith("*ST")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    doc = json.loads(args.input.read_text(encoding="utf-8"))
    checks = Checks()
    validate_classification(doc, "pre-ui", checks)
    if not checks.passed:
        raise SystemExit(json.dumps({"pass": False, "failures": [x for x in checks.items if not x["pass"]]}, ensure_ascii=False))
    rows = doc.get("rows")
    if not isinstance(rows, list):
        raise SystemExit("classification input has no rows array")

    actions = []
    seen = set()
    for row in rows:
        code = str(row.get("code", ""))
        name = str(row.get("name", ""))
        if code in seen:
            raise SystemExit(f"duplicate code {code}")
        seen.add(code)
        if is_st(name) or row.get("risk_warning") is True:
            raise SystemExit(f"risk-warning stock leaked into UI manifest: {code} {name}")
        classification = row.get("classification") if isinstance(row.get("classification"), dict) else {}
        plan = row.get("ui_plan") if isinstance(row.get("ui_plan"), dict) else {}
        action = plan.get("action")
        if action not in ALLOWED_ACTIONS:
            raise SystemExit(f"invalid action for {code}: {action!r}")
        if classification.get("status") != "classified" and action != "none":
            raise SystemExit(f"unclassified code has a UI action: {code}")
        if action in {"add", "move"} and not target_groups(plan):
            raise SystemExit(f"{action} missing target group for {code}")
        if action in {"move", "remove"} and not source_groups(plan):
            raise SystemExit(f"{action} missing source group for {code}")
        actions.append(
            {
                "code": code,
                "name": name,
                "action": action,
                "source_groups": source_groups(plan),
                "target_group": plan.get("target_group"),
                "target_groups": target_groups(plan),
                "target_actions": [{"target_group": group, "action": "ensure_present_then_save_and_readback"} for group in target_groups(plan)] if action in {'add', 'move', 'none'} else [],
                "removal_requires_all_targets_verified": target_groups(plan) if action == 'move' else [],
                "reason": plan.get("reason") or classification.get("basis"),
                "classification_status": classification.get("status"),
                "relation_tier": classification.get("relation_tier"),
            }
        )

    payload = {
        "schema_version": "2.0-ui-manifest",
        "trade_date": doc.get("trade_date"),
        "classification_path": str(args.input.resolve()),
        "classification_sha256": sha256_file(args.input),
        "generated_at": datetime.now(TZ).isoformat(timespec="seconds"),
        "group_snapshot": doc.get("group_snapshot", {}),
        "new_groups": doc.get("new_groups", []),
        "actions": actions,
        "summary": {
            action: sum(item["action"] == action for item in actions)
            for action in sorted(ALLOWED_ACTIONS)
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "actions": payload["summary"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

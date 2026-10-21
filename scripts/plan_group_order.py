#!/usr/bin/env python3
"""Plan stable watchlist group ordering from caller-verified facts; never control UI."""
from __future__ import annotations
import argparse
from datetime import date
import json
from pathlib import Path
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def string_list(value, label):
    require(isinstance(value, list), f"{label} must be an array")
    require(all(isinstance(x, str) and x.strip() for x in value), f"{label} must contain nonempty strings")
    return value


def plan_order(data):
    require(isinstance(data, dict), "input must be an object")
    target_date = data.get("trade_date")
    require(isinstance(target_date, str), "trade_date must be YYYY-MM-DD")
    require(date.fromisoformat(target_date).isoformat() == target_date, "trade_date must be YYYY-MM-DD")
    require(data.get("final_data_verified") is True, "final data is not verified")
    require(data.get("risk_warning_filtered") is True, "risk-warning filtering is not verified")
    final_codes = string_list(data.get("non_st_final_limit_up_codes"), "final codes")
    require(all(re.fullmatch(r"[0-9]{6}", x) for x in final_codes), "final codes must be six-digit strings")
    require(bool(final_codes) or data.get("empty_confirmed") is True, "an empty final pool must be explicitly confirmed")
    pool = set(final_codes)
    groups = data.get("groups")
    require(isinstance(groups, list) and bool(groups), "groups must be a complete nonempty array")
    names, counts = [], {}
    for group in groups:
        require(isinstance(group, dict), "each group must be an object")
        name = group.get("name")
        require(isinstance(name, str) and bool(name.strip()), "group name must be a nonempty string")
        require(name not in names, "duplicate group name")
        require(group.get("complete") is True, f"membership incomplete: {name}")
        members = string_list(group.get("members"), "members")
        if "ui_total" in group:
            require(type(group["ui_total"]) is int and group["ui_total"] == len(set(members)), f"UI member total mismatch: {name}")
        names.append(name)
        counts[name] = len(set(members) & pool)
    system = data.get("system_group", "自选股")
    require(isinstance(system, str) and names[0] == system, "the verified system group must already be first")
    prefix = string_list(data.get("fixed_prefix", [system]), "fixed_prefix")
    require(bool(prefix) and prefix[0] == system, "fixed_prefix must start with the system group")
    require(len(set(prefix)) == len(prefix), "duplicate fixed-prefix group")
    require(set(prefix) <= set(names), "a fixed-prefix group is missing; do not create it implicitly")
    fixed = set(prefix)
    ordinary = [name for name in names if name not in fixed]
    # Python's stable sort preserves the observed order for equal counts.
    target = prefix + sorted(ordinary, key=lambda name: -counts[name])
    require(len(target) == len(names) and set(target) == set(names), "target coverage mismatch")
    unchanged = target == names
    return {"trade_date": target_date, "group_counts": counts, "target_order": target,
            "pin_to_top": list(reversed(target[1:])) if not unchanged else [],
            "no_changes_needed": unchanged, "ui_executed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = plan_order(json.loads(args.input.read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps({"ok": True, **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

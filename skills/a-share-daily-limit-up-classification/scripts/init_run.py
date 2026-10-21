#!/usr/bin/env python3
"""Create the deterministic directory and checkpoint manifest for one trade date."""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    args.root = args.root.expanduser().resolve()
    parsed = datetime.strptime(args.date, "%Y-%m-%d")
    compact = parsed.strftime("%Y%m%d")
    batch = args.root / "market_history" / "work" / f"limit_up_classification_{compact}"
    paths = {
        "batch": batch,
        "raw_eastmoney": batch / "raw" / "eastmoney",
        "raw_xuangubao": batch / "raw" / "xuangubao",
        "raw_tonghuashun": batch / "raw" / "tonghuashun",
        "evidence": batch / "evidence",
        "outputs": batch / "outputs",
        "receipts": batch / "receipts",
        "report_md": args.root / "market_history" / "outputs" / f"{args.date}_涨停分类结果.md",
    }
    for key, path in paths.items():
        if key != "report_md":
            path.mkdir(parents=True, exist_ok=True)
    paths["report_md"].parent.mkdir(parents=True, exist_ok=True)

    manifest_path = batch / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("trade_date") != args.date:
            raise SystemExit("existing manifest trade_date mismatch")
        created = False
    else:
        manifest = {
            "schema_version": "1.1-limit-up-classification-run",
            "report_mode": "text_no_html",
            "trade_date": args.date,
            "created_at": now(),
            "updated_at": now(),
            "project_root": str(args.root),
            "stages": {
                "population": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None},
                "three_source_evidence": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None},
                "classification": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None},
                "pre_ui_validation": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None},
                "tonghuashun_ui": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None},
                "final_report": {"status": "pending", "input_sha256": None, "output_sha256": None, "error": None}
            },
            "paths": {key: str(path) for key, path in paths.items()},
        }
        try:
            with manifest_path.open("x", encoding="utf-8") as handle:
                handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
            created = True
        except FileExistsError:
            raise SystemExit("same-day manifest was created concurrently; read it before continuing")

    # Preserve old artifacts; they are not current execution requirements.
    effective_paths = {key: value for key, value in manifest.get("paths", {}).items() if key != "html"}
    effective_paths["report_md"] = str(paths["report_md"])
    print(json.dumps({"created": created, "manifest": str(manifest_path), "report_mode": "text_no_html", "paths": effective_paths}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

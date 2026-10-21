#!/usr/bin/env python3
"""Collect Tonghuashun F10 facts for an already ST-filtered code list."""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


TZ = ZoneInfo("Asia/Shanghai")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
CODE_RE = re.compile(r"^\d{6}$")


def now() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def strip_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", " ", value)
    value = html_lib.unescape(value)
    value = re.sub(r"[ \t\r\f\v]+", " ", value)
    return re.sub(r"\n +", "\n", value).strip()


def first(pattern: str, text: str, flags: int = re.S) -> str:
    match = re.search(pattern, text, flags)
    return strip_html(match.group(1)) if match else ""


def parse_page(code: str, raw: bytes, raw_path: Path, url: str, trade_date: str | None = None, captured_at: str | None = None) -> dict[str, Any]:
    text = raw.decode("gbk", errors="replace")
    title = first(r"<title>(.*?)</title>", text)
    summary = first(r'class="tip f14 fl core-view-text"[^>]*title="([^"]*)"', text)
    if not summary:
        summary = first(r'class="tip f14 fl core-view-text"[^>]*>(.*?)</span>', text)
    main_business = first(r"主营业务：</span>.*?<a[^>]*>(.*?)</a>", text)
    industry = first(r"所属申万行业：</span>.*?<a[^>]*>(.*?)</a>", text)

    concepts: list[str] = []
    for value in re.findall(r"jumpToUrl\('./concept\.html',\s*'concept',\s*'',\s*'([^']+)'", text):
        value = html_lib.unescape(value).strip()
        if value and value not in concepts:
            concepts.append(value)

    today_event = first(r"<strong[^>]*>异动提醒：</strong>.*?<span>(.*?)</span>", text)
    today_reason = first(r'<span class="open_btn">涨停分析.*?</a>.*?<div class="check_else">(.*?)</div>', text)

    # Only a date inside the reason/event material can establish its date.
    # A page footer, retrieval time or caller's --date must never supply it.
    date_matches = re.findall(r"(20[0-9]{2})[-/年](0?[1-9]|1[0-2])[-/月]([12][0-9]|3[01]|0?[1-9])(?![0-9])", today_reason + " " + today_event)
    material_dates = set()
    for year, month, day in date_matches:
        try:
            material_dates.add(datetime(int(year), int(month), int(day)).date().isoformat())
        except ValueError:
            pass
    reason_date = next(iter(material_dates)) if len(material_dates) == 1 else None
    date_matches_target = reason_date is not None and reason_date == trade_date
    status = "complete" if title and today_reason and date_matches_target else "partial"
    missing_fields = [
        key
        for key, value in {
            "page_title": title,
            "business": main_business or summary,
            "today_reason": today_reason,
            "matching_reason_date": reason_date if date_matches_target else None,
        }.items()
        if not value
    ]
    return {
        "code": code,
        "url": url,
        "raw_path": str(raw_path),
        "raw_sha256": sha256_bytes(raw),
        "status": status,
        "missing_fields": missing_fields,
        "page_title": title,
        "company_summary": summary,
        "main_business": main_business,
        "industry": industry,
        "concepts": concepts,
        "today_event": today_event,
        "today_limit_up_analysis": today_reason,
        "reason": today_reason,
        "reason_date": reason_date,
        "requested_trade_date": trade_date,
        "date_matches_target": date_matches_target,
        "verified": False,
        "material_type": "daily_limit_up_reason" if today_reason else "company_profile",
        "retrieved_at": captured_at,
        "parsed_at": now(),
    }


def fetch_one(code: str, raw_dir: Path, reuse_raw: bool, trade_date: str) -> dict[str, Any]:
    url = f"https://basic.10jqka.com.cn/{code}/"
    raw_path = raw_dir / f"{code}.html"
    metadata_path = raw_path.with_suffix(".meta.json")
    try:
        if reuse_raw and raw_path.exists() and raw_path.stat().st_size > 0:
            raw = raw_path.read_bytes()
            metadata = json.loads(metadata_path.read_text()) if metadata_path.exists() else {}
            captured_at = metadata.get("retrieved_at") if metadata.get("raw_sha256") == sha256_bytes(raw) else None
        else:
            result = subprocess.run(
                [
                    "curl",
                    "--http1.1",
                    "--tls-max",
                    "1.2",
                    "-L",
                    "--compressed",
                    "--retry",
                    "2",
                    "--retry-all-errors",
                    "--max-time",
                    "30",
                    "-sS",
                    "-A",
                    UA,
                    url,
                ],
                check=True,
                capture_output=True,
                timeout=70,
            )
            raw = result.stdout
            if not raw:
                raise RuntimeError("empty response")
            captured_at = now()
            # A second fetch preserves the previous raw page rather than replacing evidence.
            if raw_path.exists():
                raw_path = raw_dir / f"{code}_{datetime.now(TZ).strftime('%H%M%S%f')}.html"
                metadata_path = raw_path.with_suffix(".meta.json")
            raw_path.write_bytes(raw)
            metadata_path.write_text(json.dumps({"retrieved_at": captured_at, "raw_sha256": sha256_bytes(raw)}, ensure_ascii=False))
        return parse_page(code, raw, raw_path, url, trade_date, captured_at)
    except Exception as exc:  # preserve a row for every requested code
        return {
            "code": code,
            "url": url,
            "raw_path": str(raw_path),
            "status": "error",
            "error": f"{type(exc).__name__}: {exc}",
            "retrieved_at": now(),
        }


def load_codes(path: Path, trade_date: str | None = None) -> list[str]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("risk_warning_filtered") is not True:
        raise SystemExit("refusing detail fetch: codes file must contain risk_warning_filtered=true")
    if trade_date is not None and doc.get("trade_date") != trade_date:
        raise SystemExit("codes file trade_date does not match requested date")
    raw_codes = doc.get("codes")
    if not isinstance(raw_codes, list):
        raise SystemExit("codes file must contain a codes array")
    codes: list[str] = []
    for raw in raw_codes:
        code = str(raw).strip()
        if not CODE_RE.fullmatch(code):
            raise SystemExit(f"invalid six-digit code: {raw!r}")
        if code not in codes:
            codes.append(code)
    return codes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", required=True, help="YYYY-MM-DD")
    parser.add_argument("--codes", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--reuse-raw", action="store_true")
    args = parser.parse_args()

    datetime.strptime(args.date, "%Y-%m-%d")
    codes = load_codes(args.codes, args.date)
    args.raw_dir.mkdir(parents=True, exist_ok=True)

    rows: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as executor:
        futures = {executor.submit(fetch_one, code, args.raw_dir, args.reuse_raw, args.date): code for code in codes}
        for future in as_completed(futures):
            row = future.result()
            rows[row["code"]] = row

    ordered = [rows.get(code, {"code": code, "status": "missing", "retrieved_at": now()}) for code in codes]
    payload = {
        "schema_version": "2.0-ths-f10-reason",
        "trade_date": args.date,
        "source": "tonghuashun",
        "source_name": "同花顺公开F10公司资料与涨停分析",
        "source_url_template": "https://basic.10jqka.com.cn/{code}/",
        "risk_warning_filtered_before_fetch": True,
        "retrieved_at": now(),
        "requested_count": len(codes),
        "complete_count": sum(row.get("status") == "complete" for row in ordered),
        "partial_count": sum(row.get("status") == "partial" for row in ordered),
        "error_or_missing_count": sum(row.get("status") in {"error", "missing"} for row in ordered),
        "rows": ordered,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "requested": payload["requested_count"],
                "complete": payload["complete_count"],
                "partial": payload["partial_count"],
                "error_or_missing": payload["error_or_missing_count"],
                "output": str(args.output),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

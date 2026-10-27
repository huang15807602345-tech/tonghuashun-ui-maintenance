#!/usr/bin/env python3
"""Check package structure, local Markdown links, JSON examples and obvious accidental secrets."""
from pathlib import Path
import ast
import json
import re


def validate(root):
    errors = []
    required = ["README.md", "README.en.md", "LICENSE", "CHANGELOG.md", ".github/workflows/validate.yml",
                "skills/tonghuashun-ui-maintenance/scripts/local_groups.py",
                "skills/tonghuashun-ui-maintenance/scripts/ui_ops.mjs",
                "skills/tonghuashun-ui-maintenance/references/local-files.md",
                "skills/tonghuashun-ui-maintenance/references/operation-functions.md"]
    for name in ["tonghuashun-ui-maintenance", "a-share-daily-limit-up-classification"]:
        folder = root/"skills"/name
        required.extend([f"skills/{name}/SKILL.md", f"skills/{name}/agents/openai.yaml"])
        skill = (folder/"SKILL.md").read_text(encoding="utf-8") if (folder/"SKILL.md").exists() else ""
        if not re.match(r"---\nname: " + re.escape(name) + r"\ndescription: .+?\n---", skill, re.S):
            errors.append(f"invalid skill frontmatter: {name}")
    for name in required:
        if not (root/name).is_file():
            errors.append(f"missing file: {name}")
    patterns = [r"/(?:Users|home)/[^/\s]+/", r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]{20,}", r"sk-[A-Za-z0-9]{24,}"]
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file() or any(part in {".git", "__pycache__"} for part in path.relative_to(root).parts):
            continue
        if path.suffix not in {".md", ".py", ".mjs", ".json", ".yaml", ".yml"} and path.name not in {"LICENSE", ".gitignore"}:
            continue
        checked += 1
        content = path.read_text(encoding="utf-8")
        for pattern in patterns:
            if re.search(pattern, content):
                errors.append(f"possible private path or secret: {path.relative_to(root)}")
        if path.suffix == ".py":
            try:
                ast.parse(content)
            except SyntaxError as error:
                errors.append(f"Python syntax: {path.relative_to(root)}: {error}")
        if path.suffix == ".json":
            try:
                json.loads(content)
            except ValueError as error:
                errors.append(f"JSON: {path.relative_to(root)}: {error}")
        if path.suffix == ".md":
            for link in re.findall(r"\[[^]]+\]\(([^)]+)\)", content):
                if link.startswith(("https://", "http://", "#", "mailto:")):
                    continue
                target = link.split("#", 1)[0]
                if not (path.parent/target).exists():
                    errors.append(f"missing link target in {path.relative_to(root)}: {target}")
    return {"ok": not errors, "checked_files": checked, "errors": errors}


if __name__ == "__main__":
    result = validate(Path(__file__).resolve().parent.parent)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 2)

# Tonghuashun UI Maintenance

[简体中文](README.md) · [Skill](SKILL.md) · [MIT License](LICENSE)

An agent skill for maintaining watchlist groups in the macOS Tonghuashun desktop client. It covers exact group/member lookup, additions, removals, moves, multiple requested destinations, ordering, local recovery, and verification after saving.

The repository contains instructions and an optional offline ordering helper. It does not bundle the client, a desktop-control runtime, market data, or trading automation. An agent must have authorized access to the user's Mac and read its current desktop-tool documentation. Browser-only and cloud-only environments cannot operate the local client.

## Install and use

Clone this repository into a new directory and load its `SKILL.md` in an Agent Skills-compatible environment. A local Codex installation can use `~/.codex/skills/tonghuashun-ui-maintenance/`. Compare and back up any existing personal version before installing.

Start with a read-only request to list group names, order, and UI totals. For mutations, provide exact stock-code strings, source/destination groups, and scope. The skill preserves the designated main window and other viewing windows. Group clearing and deletion require an explicit request.

The skill is independent of model names. The CUA examples in `references/computer-use.md` describe one tool adapter; inspect the current runtime rather than assuming that API exists everywhere.

## Optional offline helper

Python 3.10+ and the standard library are sufficient:

```bash
python3 scripts/plan_group_order.py --input examples/sorting-input.json
python3 -m unittest discover -s tests -v
python3 scripts/validate_package.py
```

The helper validates supplied data and computes a stable group order and reverse pin sequence. It never fetches market data or modifies the desktop. The caller must verify the date, final non-risk-warning limit-up set and complete live membership. Example data is synthetic.

## Verification and limits

The instructions were developed through a real desktop workflow, but the public release has not been tested across all models or client versions. Automated checks validate offline logic and package integrity, not live UI outcomes. Every action needs a fresh observation, and completion requires reopening saved settings and reading back exact members/order.

This project does not read brokerage accounts, place/cancel orders, transfer funds, edit client databases, or determine stock-market causes. See `CONTRIBUTING.md` for privacy-conscious bug reporting. AI assistance is used in development; maintainers remain responsible for review and validation.

Independent community project, not affiliated with Tonghuashun or OpenAI. Original repository content is MIT-licensed; third-party products retain their own terms.

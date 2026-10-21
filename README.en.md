# Tonghuashun Limit-Up Research and UI Maintenance

[中文](README.md) · [Research skill](skills/a-share-daily-limit-up-classification/SKILL.md) · [UI skill](skills/tonghuashun-ui-maintenance/SKILL.md) · [MIT License](LICENSE)

An agent-skill bundle for the repetitive work of researching daily A-share limit-ups and organizing watchlist groups in the macOS Tonghuashun client. A compatible AI environment researches the complete non-ST closing limit-up population, compares at least three reason websites and the session's market behavior, then operates the desktop client to save and verify the classifications.

Classification is an evidence-based judgment, not a guarantee of causal accuracy. Missing evidence, conflicting explanations and independent company events remain explicit in the report.

## Desktop demo

Creating two demo groups in the macOS Tonghuashun client, adding stocks from a demo list, and saving the changes.

https://github.com/user-attachments/assets/f86f7d66-a8f9-4b92-aef2-3c760cf85b1d

About 52 seconds, with chat footage and idle waits removed; operations remain at their original speed. The final three-second still is explicitly labeled post-recording verification: readback found that group 2 was missing `600028`, which was added and saved after the recording, then verified as a ten-stock group. That still documents the later readback, not an action captured in the original recording. The stocks are demonstration inputs; this video covers UI maintenance, not limit-up cause research.

## Modules

| Module | Responsibility | Output |
| --- | --- | --- |
| `a-share-daily-limit-up-classification` | Verify the final population, dated sources, catalysts and market linkage; investigate low-confidence cases | Evidence-backed JSON/report and a UI manifest |
| `tonghuashun-ui-maintenance` | Read groups, add/remove/move members, create groups and order them in the confirmed main window | Per-stock/per-target saved-state receipts and remaining work |

Flow: read the live group catalog → research every eligible stock → validate → apply through the UI → reopen and verify → optionally refresh consecutive-limit-up groups and ordering. Either module can also be used independently within the requested scope.

## Behavior

- Prefer Tonghuashun, Eastmoney and Xuangubao, with other reliable sites allowed. Retain original pages, dates, reasons and repost provenance; search snippets are not verification.
- Compare catalysts, actual business, intraday timing, representative stocks and counterevidence. Do not infer leadership or causality from a static concept label or closing return.
- Reuse suitable existing groups. New groups require members, linkage evidence and a reason existing groups do not fit. Taxonomy and aliases come from the caller.
- Support a single main classification or two separately justified main classifications. Every destination must be saved and read back.
- Distinguish unresolved evidence, independent events and exclusions. The validator implements the documented [default niche-exclusion rule](skills/a-share-daily-limit-up-classification/references/classification-preferences.md); changing its algorithm also requires code and test updates.
- Add and verify all destinations before removing confirmed wrong source memberships. Preserve functional groups and other quote windows.
- Require actual consecutive daily limit-ups for the consecutive-limit-up group. Count only verified eligible final limit-ups when ordering; preserve observed order on ties and use caller-configured fixed prefixes. Unknown is never zero.

## Requirements and installation

Research needs an AI environment with web access and evidence storage. Applying changes additionally requires macOS, Tonghuashun and desktop-control tools with the necessary Accessibility/Screen Recording permissions. A web-only chat or cloud executor cannot control your local client simply by loading these files.

The repository does not include a desktop runtime, market-data subscription, client or credentials. It does not require a particular model, chat ID or 15:30 start time. Preparation can start earlier; final-close writes wait for verified final data. Historical runs and resumable work are supported.

```bash
git clone https://github.com/huang15807602345-tech/tonghuashun-ui-maintenance.git
```

Load both complete directories under `skills/` in an Agent Skills-compatible environment. For local Codex skills, place each directory under `~/.codex/skills/`. Compare and back up any existing personal version first. Keep run data outside the skill directories. Read your environment's current desktop-tool documentation; the [CUA examples](skills/tonghuashun-ui-maintenance/references/computer-use.md) are adapters, not universal APIs.

Start with a read-only catalog and confirm the main window before authorizing maintenance. Example:

```text
Use $a-share-daily-limit-up-classification for all non-ST closing limit-ups on the specified trading date.
Read the current group catalog, verify at least three reason websites per stock and evaluate session linkage.
After validation, use $tonghuashun-ui-maintenance to apply and reopen every destination for verification.
Report unresolved evidence and incomplete actions. Preserve other quote windows.
```

For research only, explicitly request no desktop changes. Clearing or deleting groups and rebuilding the whole catalog require an explicit scope; ordinary classification does not imply these actions.

## Offline checks

Python 3.10+; helper scripts use the standard library:

```bash
python3 skills/tonghuashun-ui-maintenance/scripts/plan_group_order.py --input skills/tonghuashun-ui-maintenance/examples/sorting-input.json
python3 -m unittest discover -s tests -v
python3 -B skills/a-share-daily-limit-up-classification/scripts/test_classification.py
python3 scripts/validate_package.py
```

The research module includes run initialization, an F10 clue collector, classification validation and UI-manifest generation; see its [data contract](skills/a-share-daily-limit-up-classification/references/run-contract.md). Collection is not automatic verification or a complete market-data source. Fixtures are synthetic, including sample UI receipts, and must not be presented as real research or successful UI writes.

Tests cover offline behavior and structure, not live-market causality or client persistence. Real completion requires dated evidence and saved-state readback. Interface changes and connection errors require fresh observation and only the remaining delta. Not every model, macOS release or client version has been tested.

No account reading, trading, order cancellation, transfers or direct modification of the client's configuration database. See [CONTRIBUTING](CONTRIBUTING.md) for reproducible, sanitized reports. Do not submit credentials, trades, personal paths or unredacted screenshots.

AI-assisted project, unaffiliated with Tonghuashun or OpenAI. Original repository content is MIT-licensed; third-party clients, websites and tools retain their own terms.

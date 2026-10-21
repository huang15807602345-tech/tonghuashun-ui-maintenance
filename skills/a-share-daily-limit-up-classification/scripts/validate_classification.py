#!/usr/bin/env python3
"""Validate date-specific research evidence and saved UI readback, independent of model."""
from __future__ import annotations
import argparse
import hashlib
import json
from datetime import datetime, date
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
CODE_RE = re.compile(r'^\d{6}$')
UI_ACTIONS = {'add', 'move', 'remove', 'propose_group', 'none'}
UI_STATUSES = {'already_present', 'added', 'moved', 'removed', 'failed', 'pending'}
SUCCESS_UI = {'already_present', 'added', 'moved', 'removed'}
PROTECTED_GROUPS = {'自选股', '观察', '连板', '核心', '候选', '主流', '情绪标'}


def now():
    return datetime.now(TZ).isoformat(timespec='seconds')


def sha256_file(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def codes_sha256(codes):
    return hashlib.sha256('\n'.join(sorted(codes)).encode()).hexdigest()


def text(value):
    return isinstance(value, str) and bool(value.strip())


def timestamp(value):
    if not isinstance(value, str):
        return False
    try:
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return stamp.tzinfo is not None and stamp.utcoffset() is not None
    except ValueError:
        return False


def website(url):
    if not isinstance(url, str):
        return None
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or '').lower().rstrip('.')
        if parsed.scheme not in {'http', 'https'} or not host or parsed.username or parsed.password:
            return None
    except ValueError:
        return None
    # Count websites, not subdomains or differently named copies of the same card.
    parts = host.split('.')
    if len(parts) < 2 or host.replace('.', '').isdigit():
        return None
    suffix_len = 3 if '.'.join(parts[-2:]) in {'com.cn', 'net.cn', 'org.cn', 'gov.cn', 'co.uk', 'com.hk', 'com.tw'} else 2
    return '.'.join(parts[-suffix_len:])


def is_risk_warning_name(name):
    compact = re.sub(r'\s+', '', name).upper() if isinstance(name, str) else ''
    return compact.startswith(('ST', '*ST'))


def source_groups(plan):
    groups = plan.get('source_groups', [])
    if not isinstance(groups, list):
        return []
    legacy = plan.get('source_group')
    return list(dict.fromkeys([x for x in groups + ([legacy] if legacy else []) if text(x)]))


def target_groups(value):
    """Explicit multi-target list is authoritative; singular fields are legacy only."""
    if 'assignments' in value:
        return [item.get('target_group') for item in value['assignments'] if isinstance(item, dict)]
    if 'target_groups' in value:
        return value['target_groups']
    return [value['target_group']] if text(value.get('target_group')) else []


def theme_filter(activity, code):
    today, history, niche = (activity.get(key, {}) for key in ('today', 'history', 'niche'))
    conditions = [
        len(set(today.get('codes', [])) - {code}) < 1 if today.get('status') == 'verified' else None,
        niche.get('value'),
        (len(set(history.get('codes', []))) < 3 if history.get('status') == 'verified'
         else False if history.get('status') == 'verified_at_least_three' and len(set(history.get('codes', []))) >= 3 else None),
    ]
    yes = sum(value is True for value in conditions)
    unknown = sum(value is None for value in conditions)
    decision = 'exclude' if yes >= 2 else ('pending' if yes + unknown >= 2 else 'include')
    return {'conditions': conditions, 'decision': decision}


def validate_research_v4(row, doc, require):
    choice = row.get('reason_selection', {})
    require(choice.get('initial_confidence') in {'high', 'medium', 'low'}, 'missing initial confidence')
    require(text(choice.get('confidence_basis')), 'missing confidence basis')
    if choice.get('initial_confidence') == 'low' or choice.get('confidence') == 'low' or choice.get('low_confidence_triggered') is True:
        research = row.get('exploratory_research', {})
        require(research.get('status') in {'completed', 'unresolved', 'blocked'}, 'low confidence requires divergent research')
        require(bool(research.get('questions')) and text(research.get('conclusion')), 'missing research questions/conclusion')
        searches = research.get('searches', [])
        require(isinstance(searches, list) and bool(searches), 'missing divergent search record')
        for search in searches:
            require(all(text(search.get(key)) for key in ('query', 'channel', 'findings')) and isinstance(search.get('evidence_refs'), list), 'incomplete divergent search')
        trend = research.get('trend_analysis', {})
        require(trend.get('status') in {'completed', 'unavailable'}, 'low confidence requires intraday trend analysis')
        require(isinstance(trend.get('candidate_groups'), list) and bool(trend.get('candidate_groups')), 'missing trend candidates')
        if trend.get('status') == 'completed':
            require(all(text(trend.get(key)) for key in ('time_range', 'granularity', 'observations', 'market_comparison')) and bool(trend.get('evidence_refs')) and bool(trend.get('representatives')), 'missing actual intraday comparison evidence')
        else:
            require(text(trend.get('limitations')) and bool(trend.get('attempted_channels')), 'unavailable trend data needs attempts and explicit gap')
    results = row.get('theme_filter_results')
    require(isinstance(results, dict), 'missing per-theme exclusion assessment')
    activities = doc.get('theme_activity', {})
    for group, result in (results or {}).items():
        require(group in activities, 'theme assessment missing activity evidence')
        if group not in activities:
            continue
        activity = activities[group]
        if activity.get('today', {}).get('status') == 'verified':
            require(row.get('code') in activity['today']['codes'], 'candidate stock missing from complete same-day theme population')
        require(result == theme_filter(activity, row.get('code'))['decision'], 'theme exclusion result differs from any-two rule')
    if row.get('unclassified_kind') == 'niche_excluded':
        require(bool(results) and all(result == 'exclude' for result in results.values()), 'niche exclusion lacks two verified conditions for each candidate')
    if row.get('unclassified_kind') == 'theme_activity_pending':
        require(bool(results) and 'pending' in results.values() and 'include' not in results.values(), 'pending exclusion lacks decision-changing missing data')


def validate_theme_activity(doc, checks):
    activities = doc.get('theme_activity')
    errors = []
    if not isinstance(activities, dict):
        checks.add('theme_activity', False, 'theme_activity must be an object')
        return
    for group, activity in activities.items():
        def need(ok, message):
            if not ok:
                errors.append(f'{group}: {message}')
        need(text(group) and text(activity.get('mapping_basis')), 'missing canonical theme mapping')
        for period in ('today', 'history'):
            item = activity.get(period, {})
            allowed = {'verified', 'unavailable', 'not_needed'} | ({'verified_at_least_three'} if period == 'history' else set())
            need(item.get('status') in allowed, f'{period} missing completeness status')
            codes = item.get('codes')
            if item.get('status') in {'verified', 'verified_at_least_three'}:
                need(isinstance(codes, list) and all(isinstance(c, str) and CODE_RE.fullmatch(c) for c in codes) and len(codes) == len(set(codes)), f'{period} codes must be unique six-digit identifiers')
                need(bool(item.get('evidence_refs')), f'{period} lacks population and attribution evidence')
                if period == 'today':
                    need(set(codes or []) <= set(doc.get('population', {}).get('codes', [])), 'today theme exceeds final non-ST pool')
                else:
                    dates = item.get('trading_dates', [])
                    need(isinstance(dates, list) and len(dates) == 10 and len(set(dates)) == 10 and dates == sorted(dates) and dates[-1] == doc.get('trade_date') and all(date.fromisoformat(d) for d in dates) and item.get('calendar_verified') is True, 'history must cover verified last ten trading dates including D')
                    if item.get('status') == 'verified_at_least_three':
                        need(len(set(codes or [])) >= 3, 'history lower bound needs three distinct verified stocks')
                        occurrences = item.get('occurrences', [])
                        proven = {entry.get('code') for entry in occurrences if isinstance(entry, dict) and entry.get('date') in dates and bool(entry.get('evidence_refs'))}
                        need(set(codes or []) <= proven, 'history lower bound lacks dated per-code limit-up and theme evidence')
            else:
                need(codes is None and text(item.get('gap')), f'{period} unqueried/missing data must be null with a reason, not zero')
        today, history = activity.get('today', {}), activity.get('history', {})
        if today.get('status') == history.get('status') == 'verified':
            need(set(today.get('codes', [])) <= set(history.get('codes', [])), 'ten-day history omits D theme stocks')
        niche = activity.get('niche', {})
        need(niche.get('value') is None or type(niche.get('value')) is bool, 'niche judgment must be boolean or null')
        need(text(niche.get('basis')), 'niche judgment needs drivers and counterevidence')
        if niche.get('value') is not None:
            need(bool(niche.get('evidence_refs')), 'niche judgment lacks evidence')
    checks.add('theme_activity', not errors, '; '.join(errors[:30]))


def verified_reason_sites(row, trade_date):
    result = set()
    reasons = row.get('source_reasons', {})
    if not isinstance(reasons, dict):
        return result
    for item in reasons.values():
        if not isinstance(item, dict):
            continue
        site = website(item.get('url'))
        if (site and item.get('status') == 'complete' and item.get('verified') is True
            and item.get('reason_date') == trade_date and text(item.get('reason'))
            and item.get('material_type') == 'daily_limit_up_reason'
            and timestamp(item.get('retrieved_at'))):
            result.add(site)
    return result


class Checks:
    def __init__(self):
        self.items = []

    def add(self, name, ok, detail=''):
        self.items.append({'name': name, 'pass': bool(ok), 'detail': detail})

    @property
    def passed(self):
        return all(x['pass'] for x in self.items)


def _validate_classification(doc, stage, checks):
    if not isinstance(doc, dict):
        checks.add('classification_object', False)
        return [], []
    trade_date = doc.get('trade_date')
    try:
        date.fromisoformat(trade_date)
        date_ok = True
    except (ValueError, TypeError):
        date_ok = False
    checks.add('valid_trade_date', date_ok, str(trade_date))
    version = str(doc.get('schema_version', '')).split('.')[0]
    checks.add('schema_version', version in {'2', '3', '4'} and (stage == 'final' or version == '4'))
    if version == '4':
        validate_theme_activity(doc, checks)
    checks.add('scope', doc.get('scope') == 'non_st_final_limit_up')
    policy = doc.get('source_policy') if isinstance(doc.get('source_policy'), dict) else {}
    minimum = policy.get('minimum_reason_websites', 3)
    minimum_ok = type(minimum) is int and minimum >= 3
    checks.add('minimum_three_reason_websites', minimum_ok)
    minimum = minimum if minimum_ok else 3
    checks.add('risk_warning_filtered', policy.get('st_detail_policy') == 'exclude_before_detail')
    rows = doc.get('rows')
    checks.add('rows_array', isinstance(rows, list))
    rows = rows if isinstance(rows, list) else []
    population = doc.get('population') if isinstance(doc.get('population'), dict) else {}
    checks.add('population_final_reconciled', population.get('status') == 'reconciled' and population.get('final_data_verified') is True)
    counts = population.get('source_counts')
    checks.add('population_source_counts', isinstance(counts, dict) and len(counts) >= 2 and all(type(v) is int and v >= 0 for v in counts.values()))
    excluded = population.get('excluded_risk_warning_count')
    checks.add('excluded_count', type(excluded) is int and excluded >= 0)
    checks.add('row_count', type(population.get('non_st_count')) is int and population.get('non_st_count') == len(rows))
    checks.add('confirmed_empty', bool(rows) or population.get('empty_confirmed') is True)
    codes = [r.get('code') for r in rows if isinstance(r, dict)]
    valid_codes = all(isinstance(code, str) and CODE_RE.fullmatch(code) for code in codes) and len(codes) == len(rows)
    checks.add('unique_six_digit_codes', valid_codes and len(set(str(c) for c in codes)) == len(rows))
    expected = population.get('codes')
    expected_ok = isinstance(expected, list) and all(isinstance(c, str) and CODE_RE.fullmatch(c) for c in expected)
    checks.add('population_exact_codes', expected_ok and valid_codes and len(expected) == len(rows) and set(expected) == set(codes))
    checks.add('population_codes_hash', expected_ok and population.get('codes_sha256') == codes_sha256(expected))
    conflicts = population.get('conflicts')
    checks.add('population_conflicts_resolved', isinstance(conflicts, list) and not conflicts)
    snapshot = doc.get('group_snapshot') if isinstance(doc.get('group_snapshot'), dict) else {}
    groups = snapshot.get('groups')
    group_ok = isinstance(groups, list) and bool(groups) and all(text(g) for g in groups)
    checks.add('live_complete_group_snapshot', group_ok and len(set(groups)) == len(groups) and snapshot.get('complete') is True and snapshot.get('source') == 'live_ui' and snapshot.get('ui_total') == len(groups) and timestamp(snapshot.get('captured_at')))
    groups = groups if group_ok else []
    proposals = doc.get('new_groups', [])
    new_groups = {}
    proposal_errors = []
    if not isinstance(proposals, list):
        proposal_errors.append('new_groups must be an array')
        proposals = []
    for proposal in proposals:
        if not isinstance(proposal, dict):
            proposal_errors.append('new group must be an object')
            continue
        name, members = proposal.get('name'), proposal.get('members')
        if not text(name) or name in groups or name in new_groups:
            proposal_errors.append('new group name must be unique and absent from live groups')
            continue
        valid_members = isinstance(members, list) and all(isinstance(c, str) and c in codes for c in members)
        linked = proposal.get('linked_members', members)
        minimum_members = 1 if proposal.get('user_requested_singleton') is True else 2
        linked_ok = isinstance(linked, list) and all(isinstance(c, str) and CODE_RE.fullmatch(c) for c in linked)
        if not valid_members or not members or not linked_ok or len(set(linked)) < minimum_members or not set(members) <= set(linked):
            proposal_errors.append(f'{name}: missing linked members or explicit singleton request')
        if not text(proposal.get('not_reusing_reason')) or not text(proposal.get('market_linkage_evidence')):
            proposal_errors.append(f'{name}: missing new-group rationale')
        new_groups[name] = proposal
    checks.add('new_group_contract', not proposal_errors, '; '.join(proposal_errors))
    errors, classified = [], []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f'row[{index}] is not an object')
            continue
        code = row.get('code')
        prefix = f'row[{index}] {code}'
        def require(ok, message):
            if not ok:
                errors.append(f'{prefix}: {message}')
        require(text(row.get('name')) and not is_risk_warning_name(row.get('name')) and row.get('risk_warning') is not True, 'name/risk-warning mismatch')
        reasons = row.get('source_reasons')
        require(isinstance(reasons, dict), 'source_reasons must be an object')
        if isinstance(reasons, dict):
            for key, item in reasons.items():
                if not isinstance(item, dict):
                    require(False, f'{key} card must be an object')
                    continue
                require(item.get('status') in {'complete', 'partial', 'missing', 'error'}, f'{key} invalid status')
                if item.get('status') == 'complete':
                    require(text(item.get('reason')) and website(item.get('url')) and timestamp(item.get('retrieved_at')), f'{key} incomplete material')
                    provenance = item.get('provenance')
                    require(isinstance(provenance, dict) and provenance.get('kind') in {'original', 'reprint', 'unknown'}, f'{key} missing provenance')
                    if isinstance(provenance, dict) and provenance.get('kind') == 'reprint':
                        require(bool(website(provenance.get('original_url'))), f'{key} reprint lacks original URL')
        for field in ('company_business_basis', 'instant_catalyst', 'market_trading_reason', 'stock_specific_amplifier'):
            require(text(row.get(field)), f'missing {field}')
        context = row.get('market_context_evidence')
        require(isinstance(context, list), 'market_context_evidence must be an array')
        choice = row.get('reason_selection') if isinstance(row.get('reason_selection'), dict) else {}
        require(choice.get('selected_source') in set(reasons or {}) | {'synthesis', 'unresolved'} if isinstance(reasons, dict) else False, 'selected source is not in evidence')
        require(text(choice.get('selected_reason')) and text(choice.get('why_closest')), 'missing reason selection explanation')
        require(isinstance(choice.get('counterevidence'), list) and choice.get('confidence') in {'high', 'medium', 'low'}, 'invalid uncertainty fields')
        cl = row.get('classification') if isinstance(row.get('classification'), dict) else {}
        plan = row.get('ui_plan') if isinstance(row.get('ui_plan'), dict) else {}
        action, status = plan.get('action'), cl.get('status')
        require(status in {'classified', 'unclassified'}, 'invalid classification status')
        require(action in UI_ACTIONS, 'invalid UI action')
        require(text(cl.get('basis')) and isinstance(cl.get('alternative_groups'), list) and isinstance(cl.get('existing_wrong_groups'), list), 'missing classification explanation/lists')
        if version == '4':
            validate_research_v4(row, doc, require)
            assignments = cl.get('assignments')
            require(isinstance(assignments, list), 'missing assignments array')
            assignments = assignments if isinstance(assignments, list) else []
            targets = target_groups(cl)
            require(plan.get('target_groups') == targets, 'UI target list differs from all research assignments')
            require(len(targets) == len(set(targets)), 'duplicate target groups')
            primary_groups = [assignment.get('primary_group') for assignment in assignments if isinstance(assignment, dict)]
            require(len(primary_groups) == len(set(primary_groups)), 'two sub-causes in the same primary theme must be merged')
            require(not set(targets) & set(cl.get('existing_wrong_groups', [])), 'valid co-primary target cannot be marked wrong')
            if status == 'classified':
                require(cl.get('mode') == ('dual' if len(assignments) == 2 else 'single') and 1 <= len(assignments) <= 2, 'classification must have one or two targets')
                require(choice.get('confidence') in {'medium', 'high'}, 'low confidence cannot write before resolution')
                if len(assignments) == 2:
                    require(text(cl.get('dual_basis')), 'dual classification requires evidence for equal primary causes')
                    require(cl.get('primary_group') is None and cl.get('target_group') is None and plan.get('target_group') is None, 'dual classification cannot carry ambiguous singular targets')
                elif len(assignments) == 1:
                    require(cl.get('primary_group') == assignments[0].get('primary_group') and cl.get('target_group') == targets[0] and plan.get('target_group') == targets[0], 'single aliases differ from assignment')
                for assignment in assignments:
                    target = assignment.get('target_group')
                    require(all(text(assignment.get(key)) for key in ('primary_group', 'target_group', 'market_trading_reason', 'confidence_basis', 'basis')), 'incomplete primary cause assignment')
                    require(assignment.get('confidence') in {'medium', 'high'} and assignment.get('relation_tier') in {'direct', 'high_umbrella'}, 'each target needs medium/high confidence and actual trading relationship')
                    require(bool(assignment.get('evidence_refs')), 'each primary cause needs evidence')
                    require(target not in PROTECTED_GROUPS, 'functional group cannot be a theme write target')
                    require(row.get('theme_filter_results', {}).get(assignment.get('primary_group')) == 'include', 'target excluded or theme activity pending')
                    if action in {'add', 'move', 'none'}:
                        require(target in groups or (target in new_groups and new_groups[target].get('creation_authorized') is True and code in new_groups[target].get('members', [])), 'target absent and new group unauthorized')
            else:
                require(not assignments and cl.get('mode') == 'none', 'unclassified row cannot have assignments')
        if status == 'classified':
            classified.append(code)
            target = cl.get('target_group')
            if version != '4':
                require(text(cl.get('primary_group')) and text(target), 'missing primary/target group')
                require(isinstance(target, str) and target not in PROTECTED_GROUPS, 'functional group cannot be a theme write target')
                require(cl.get('relation_tier') in {'direct', 'high_umbrella'}, 'weak relationship cannot be classified')
            require(choice.get('selected_source') != 'unresolved', 'unresolved reason cannot be classified')
            if isinstance(reasons, dict) and choice.get('selected_source') in reasons:
                selected_card = reasons[choice['selected_source']]
                require(bool(verified_reason_sites({'source_reasons': {'selected': selected_card}}, trade_date)), 'selected source is not verified same-day material')
            require(len(verified_reason_sites(row, trade_date)) >= minimum, 'fewer than required verified same-day reason websites')
            require(isinstance(context, list) and bool(context), 'classified stock lacks market-linkage evidence')
            if version != '4' and action in {'add', 'move', 'none'}:
                require(plan.get('target_group') == target, 'UI target differs from research target')
                require(target in groups or (target in new_groups and new_groups[target].get('creation_authorized') is True and code in new_groups[target].get('members', [])), 'target is absent and new group is not authorized')
        elif status == 'unclassified':
            require(cl.get('primary_group') in (None, '') and cl.get('target_group') in (None, '') and action == 'none', 'unclassified stock cannot write a theme group')
            require(text(row.get('unclassified_reason')), 'missing unclassified reason')
            require(row.get('unclassified_kind') in {'independent_event', 'insufficient_evidence', 'policy_excluded', 'weak_linkage', 'niche_excluded', 'theme_activity_pending'}, 'missing unclassified kind')
        sources = source_groups(plan)
        if action in {'move', 'remove'}:
            require(bool(sources), 'missing precise source groups')
            require(not set(sources) & PROTECTED_GROUPS, 'functional group must not be removed by theme classification')
            require(all(group in groups for group in sources), 'source group missing from live directory')
            require(set(sources) <= set(x for x in cl.get('existing_wrong_groups', []) if isinstance(x, str)), 'source removals lack verified wrong-group evidence')
            require(not set(target_groups(cl)) & set(sources), 'a valid target is also a removal source')
        require(row.get('evidence_status') in {'complete', 'partial', 'missing'}, 'invalid evidence status')
    row_by_code = {r.get('code'): r for r in rows if isinstance(r, dict) and isinstance(r.get('code'), str)}
    for name, proposal in new_groups.items():
        if proposal.get('creation_authorized') is True:
            for member in proposal.get('members', []):
                member_row = row_by_code.get(member, {})
                member_class = member_row.get('classification', {})
                member_plan = member_row.get('ui_plan', {})
                if not isinstance(member_class, dict) or not isinstance(member_plan, dict) or member_class.get('status') != 'classified' or name not in target_groups(member_class) or member_plan.get('action') not in {'add', 'move'}:
                    errors.append(f'{name}: member {member} is not an eligible planned write')
    checks.add('row_contract', not errors, '; '.join(errors[:50]))
    summary = doc.get('summary') if isinstance(doc.get('summary'), dict) else {}
    checks.add('summary_counts', summary.get('classified_count') == len(classified) and summary.get('unclassified_count') == len(rows)-len(classified))
    return rows, classified


def _validate_ui(doc, audit, classification_path, classified_codes, checks, strict):
    if not isinstance(audit, dict):
        checks.add('ui_audit_object', False)
        return {'ui_all_success': False, 'unresolved_codes': classified_codes}
    checks.add('ui_trade_date', audit.get('trade_date') == doc.get('trade_date'))
    expected_sha = sha256_file(classification_path)
    checks.add('ui_classification_hash', audit.get('classification_sha256') == expected_sha)
    preflight = audit.get('preflight') if isinstance(audit.get('preflight'), dict) else {}
    checks.add('ui_preflight', all(preflight.get(k) is True for k in ('main_window', 'window_layout_preserved', 'group_dialog_verified')))
    entries = audit.get('by_code')
    checks.add('ui_entries_object', isinstance(entries, dict))
    entries = entries if isinstance(entries, dict) else {}
    rows = {r.get('code'): r for r in doc.get('rows', []) if isinstance(r, dict) and isinstance(r.get('code'), str)}
    errors, unresolved = [], []
    for code in classified_codes:
        item = entries.get(code)
        row = rows.get(code, {})
        plan = row.get('ui_plan', {})
        if not isinstance(item, dict):
            errors.append(f'{code}: missing/object expected')
            unresolved.append(code)
            continue
        status = item.get('status')
        if status not in UI_STATUSES:
            errors.append(f'{code}: invalid status')
        if status not in SUCCESS_UI:
            unresolved.append(code)
            if not text(item.get('reason')):
                errors.append(f'{code}: missing pending/failure reason')
            continue
        action = plan.get('action')
        valid_statuses = {'add': {'added', 'already_present'}, 'move': {'moved'}, 'remove': {'removed'}, 'none': {'already_present'}, 'propose_group': set()}.get(action, set())
        if status not in valid_statuses:
            errors.append(f'{code}: status does not prove planned action')
        targets = target_groups(row.get('classification', {}))
        if str(doc.get('schema_version', '')).startswith('4.') and action != 'remove':
            if len(targets) == 1 and any(key in item and item[key] != targets[0] for key in ('target_group', 'verified_target_group')):
                errors.append(f'{code}: singular receipt differs from authoritative target')
            if len(targets) == 2 and any(item.get(key) is not None for key in ('target_group', 'verified_target_group')):
                errors.append(f'{code}: dual receipt carries a misleading singular target')
            proofs = item.get('targets', [])
            actual = [proof.get('target_group') for proof in proofs if isinstance(proof, dict)] if isinstance(proofs, list) else []
            if len(actual) != len(targets) or set(actual) != set(targets):
                errors.append(f'{code}: every target needs its own saved receipt')
            for proof in proofs:
                if proof.get('status') not in {'added', 'already_present'} or proof.get('verified_target_group') != proof.get('target_group') or proof.get('readback_verified') is not True or not timestamp(proof.get('verified_at')) or not text(proof.get('verification_method')):
                    errors.append(f'{code}: target lacks saved readback proof')
                if status == 'already_present' and proof.get('status') != 'already_present':
                    errors.append(f'{code}: changed target cannot be an unchanged receipt')
        elif action != 'remove' and (item.get('target_group') != (targets or [None])[0] or item.get('verified_target_group') != (targets or [None])[0]):
            errors.append(f'{code}: actual target differs from classification')
        if not text(item.get('verification_method')) or not timestamp(item.get('verified_at')) or item.get('readback_verified') is not True:
            errors.append(f'{code}: missing saved readback proof')
        if action in {'move', 'remove'}:
            absent = item.get('verified_absent_source_groups')
            if not isinstance(absent, list) or not set(source_groups(plan)) <= set(x for x in absent if isinstance(x, str)):
                errors.append(f'{code}: source removal not verified')
    for code, item in entries.items():
        if code not in rows:
            errors.append(f'{code}: unexpected receipt code')
        elif not isinstance(item, dict):
            errors.append(f'{code}: receipt must be an object')
        elif code not in classified_codes and item.get('status') in {'added', 'moved', 'removed'}:
            errors.append(f'{code}: unclassified stock was changed')
    no_changes = audit.get('no_changes_needed') is True and all(isinstance(entries.get(c), dict) and entries[c].get('status') == 'already_present' for c in classified_codes)
    checks.add('ui_persisted', audit.get('settings_saved') is True or no_changes)
    checks.add('ui_readback_contract', not errors, '; '.join(errors[:50]))
    if strict:
        checks.add('ui_all_actions_successful', not unresolved, str(unresolved))
    return {'expected_sha256': expected_sha, 'unresolved_codes': unresolved, 'ui_all_success': not unresolved and not errors}



def validate_classification(doc, stage, checks):
    try:
        return _validate_classification(doc, stage, checks)
    except (TypeError, AttributeError, KeyError, ValueError, IndexError) as error:
        checks.add('malformed_classification_field', False, str(error))
        return [], []


def validate_ui(doc, audit, classification_path, classified_codes, checks, strict):
    try:
        return _validate_ui(doc, audit, classification_path, classified_codes, checks, strict)
    except (TypeError, AttributeError, KeyError, ValueError, IndexError) as error:
        checks.add('malformed_ui_field', False, str(error))
        return {'ui_all_success': False, 'unresolved_codes': classified_codes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--stage', choices=('pre-ui', 'final'), default='pre-ui')
    parser.add_argument('--ui-audit', type=Path)
    parser.add_argument('--receipt', type=Path)
    parser.add_argument('--strict-ui-success', action='store_true')
    args = parser.parse_args()
    checks, ui = Checks(), {}
    try:
        doc = json.loads(args.input.read_text())
        rows, classified = validate_classification(doc, args.stage, checks)
        if args.stage == 'final':
            if args.ui_audit is None:
                checks.add('ui_audit_required', False)
            else:
                audit = json.loads(args.ui_audit.read_text())
                ui = validate_ui(doc, audit, args.input, classified, checks, args.strict_ui_success)
        receipt = {'schema_version': '4.0-validation', 'stage': args.stage, 'validated_at': now(), 'input': str(args.input.resolve()), 'input_sha256': sha256_file(args.input), 'pass': checks.passed, 'checks': checks.items, 'ui': ui}
    except (OSError, ValueError, TypeError) as error:
        receipt = {'pass': False, 'error': str(error)}
    if args.receipt:
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt['pass'] else 2


if __name__ == '__main__':
    raise SystemExit(main())

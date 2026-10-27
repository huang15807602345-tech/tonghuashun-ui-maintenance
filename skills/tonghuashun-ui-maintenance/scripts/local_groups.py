#!/usr/bin/env python3
"""Read Tonghuashun local groups and verify saved deltas. Never writes app data."""
from __future__ import annotations
import argparse
import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import plistlib
import sys
import time
from zoneinfo import ZoneInfo

TZ = ZoneInfo('Asia/Shanghai')
APP_DATA = Path.home() / 'Library/Containers/cn.com.10jqka.macstock/Data'


def now():
    return datetime.now(TZ).isoformat()


def varint(data, offset):
    number = shift = 0
    while offset < len(data) and shift < 64:
        byte = data[offset]
        offset += 1
        number |= (byte & 127) << shift
        if byte < 128:
            return number, offset
        shift += 7
    raise ValueError('invalid varint')


def fields(data):
    result, offset = {}, 0
    while offset < len(data):
        tag, offset = varint(data, offset)
        number, wire = tag >> 3, tag & 7
        if not number:
            raise ValueError('invalid field number')
        if wire == 0:
            value, offset = varint(data, offset)
        elif wire in (1, 5):
            size = 8 if wire == 1 else 4
            value = data[offset:offset + size]
            if len(value) != size:
                raise ValueError('truncated field')
            offset += size
        elif wire == 2:
            size, offset = varint(data, offset)
            value = data[offset:offset + size]
            if len(value) != size:
                raise ValueError('truncated field')
            offset += size
        else:
            raise ValueError(f'unsupported wire type {wire}')
        if number in result:
            raise ValueError(f'duplicate field {number}')
        result[number] = value
    return result


def dereference(objects, value):
    if isinstance(value, plistlib.UID):
        return dereference(objects, objects[value.data])
    if isinstance(value, dict) and 'NS.data' in value:
        return value['NS.data']
    return value


def read_entity(path):
    raw = path.read_bytes()
    doc = plistlib.loads(raw)
    objects = doc['$objects']
    entity = dereference(objects, doc['$top']['root'])
    identifier = dereference(objects, entity['self.ID'])
    payload = fields(dereference(objects, entity['self.value']))
    evidence = {'path': str(path.resolve()), 'sha256': hashlib.sha256(raw).hexdigest(),
                'version': entity.get('self.version'),
                'modified_at': datetime.fromtimestamp(path.stat().st_mtime, TZ).isoformat()}
    return identifier, payload, evidence


def discover_source():
    paths = list((APP_DATA / 'Documents/cloud_store').glob('blockstock_*/public'))
    if len(paths) != 1:
        raise ValueError(f'Expected one blockstock source, found {len(paths)}; specify --source-dir without reading account credentials')
    return paths[0]


def snapshot(source):
    paths = {}
    for path in sorted(source.glob('*.dat')):
        try:
            key = base64.b64decode(path.stem.split('__')[-1], validate=True)
        except ValueError:
            continue
        # Only group records and the group registration map, never userid or credentials.
        if key[:1] != b'\x08' and key != b'StockGroupCommon':
            continue
        if key in paths:
            raise ValueError('duplicate local group file identifier')
        paths[key] = path
    if b'\x08\x00' not in paths or b'StockGroupCommon' not in paths:
        raise ValueError('local order or system registration is missing')
    _, root_fields, order_evidence = read_entity(paths[b'\x08\x00'])
    order = [int(x, 16) for x in root_fields[1].decode('ascii').split(',') if x]
    _, common_fields, common_evidence = read_entity(paths[b'StockGroupCommon'])
    registration = json.loads(common_fields[1].decode('utf-8'))
    if '0' not in registration:
        raise ValueError('system self group is not registered')
    self_id = fields(registration['0'].encode('latin1'))[1]
    records = {}
    wanted = set(order) | {self_id}
    for key, path in paths.items():
        if key == b'StockGroupCommon':
            continue
        group_id = fields(key)[1]
        if group_id not in wanted or group_id == 0:
            continue
        identifier, payload, evidence = read_entity(path)
        if identifier != key:
            raise ValueError(f'group identifier differs from filename: {path.name}')
        name = base64.b64decode(payload[1], validate=True).decode('gb18030')
        query_data = payload.get(2, b'')
        codes_text, separator, markets_text = payload.get(3, b'').decode('ascii').partition(',')
        if not separator:
            raise ValueError(f'missing code/market separator: {name or group_id}')
        codes = [x for x in codes_text.split('|') if x]
        markets = [x for x in markets_text.split('|') if x]
        if len(codes) != len(markets):
            raise ValueError(f'code/market count mismatch: {name or group_id}')
        if len(codes) != len(set(codes)):
            raise ValueError(f'duplicate code in local group: {name or group_id}')
        records[group_id] = {'id': group_id, 'name': name, 'query_record': bool(query_data),
                             'members': [{'code': c, 'market': m} for c, m in zip(codes, markets)],
                             'total': len(codes), 'complete': True, 'evidence': evidence}
    if len(order) != len(set(order)):
        raise ValueError('duplicate group identifier in local order')
    groups, names, excluded = {}, [], []
    for identifier in order:
        if identifier not in records:
            raise ValueError(f'ordered group {identifier} has no local record')
        record = records[identifier]
        if record['query_record']:
            excluded.append({'id': identifier, 'name': record['name'], 'reason': 'condition_query_record',
                             'evidence': record['evidence']})
            continue
        name = record['name']
        if not name or name in groups:
            raise ValueError('empty or duplicate custom group name')
        groups[name] = record
        names.append(name)
    if '自选股' not in groups:
        self_record = records.get(self_id)
        if self_record and self_record['name'] != '自选股':
            raise ValueError('system self group identity conflict')
        groups['自选股'] = self_record or {
            'id': self_id, 'name': '自选股', 'system': True, 'members': None, 'total': None,
            'complete': False, 'evidence': common_evidence,
            'gap': 'system membership is not cached here; fixed prefix only, never infer an empty set'}
    names = ['自选股'] + [n for n in names if n != '自选股']
    return {'schema_version': 'ths-local-groups-1', 'source': 'local_file', 'status': 'complete',
            'captured_at': now(), 'source_directory': str(source.resolve()),
            'directory_complete': True, 'ranked_members_complete': all(groups[n]['complete'] for n in names if n != '自选股'),
            'group_count': len(names), 'known_membership_count': sum(g['total'] for g in groups.values() if g['total'] is not None),
            'order': names, 'groups': groups, 'order_evidence': order_evidence,
            'system_registration_evidence': common_evidence, 'excluded_query_records': excluded}


def write_json(path, data, source):
    path = path.resolve()
    source = source.resolve()
    app_data = APP_DATA.resolve()
    if app_data == path or app_data in path.parents or source == path or source in path.parents:
        raise ValueError('output must be outside application data and source directory')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def make_snapshot(source, output):
    data = snapshot(source)
    data['group_snapshot'] = {
        'source': 'local_file', 'captured_at': data['captured_at'], 'groups': data['order'],
        'ui_total': data['group_count'], 'complete': True, 'snapshot_path': str(output.resolve()),
        'read_scope': 'custom_groups_and_registered_system_prefix'}
    write_json(output, data, source)
    return data


def code_set(data, group):
    record = data['groups'].get(group)
    if record is None or not record.get('complete') or not isinstance(record.get('members'), list):
        raise ValueError(f'membership unavailable for {group}')
    return {m['code'] for m in record['members']}


def expectations(doc, before):
    if doc.get('settings_saved') is not True and doc.get('no_changes_needed') is not True:
        raise ValueError('verification requires an actual UI save or an explicit no-change result')
    if doc.get('settings_saved') is True:
        stamp = datetime.fromisoformat(doc.get('saved_at', '').replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            raise ValueError('saved_at must have a timezone')
        if stamp > datetime.now(TZ):
            raise ValueError('saved_at is in the future; record the actual completed save time')
    changes = doc.get('changes', [])
    if changes and doc.get('settings_saved') is not True:
        raise ValueError('changed memberships require an actual UI save')
    exact = {name: set(codes) for name, codes in doc.get('exact_groups', {}).items()}
    created = doc.get('created_groups', [])
    targets = {}
    def target(group, code, present):
        if not isinstance(group, str) or not group or not isinstance(code, str) or not code:
            raise ValueError('target group and code must be nonempty strings')
        if type(present) is not bool:
            raise ValueError('target present must be boolean')
        key = (group, code)
        if key in targets and targets[key] != present:
            raise ValueError('contradictory target expectation')
        targets[key] = present
    for item in doc.get('targets', []):
        target(item['group'], item['code'], item['present'])
    derived = {}
    for item in changes:
        name, code, action = item['group'], item['code'], item['action']
        if action not in {'add', 'remove'}:
            raise ValueError('change action must be add or remove')
        if name not in derived:
            if before is None:
                raise ValueError('changes require --before for exact membership/count confirmation')
            derived[name] = set() if name in created and name not in before['groups'] else code_set(before, name)
        target(name, code, action == 'add')
        (derived[name].add if action == 'add' else derived[name].discard)(code)
    for name, codes in derived.items():
        if name in exact and exact[name] != codes:
            raise ValueError('exact group conflicts with before plus changes')
        exact[name] = codes
    order = doc.get('order')
    if order is not None and (not isinstance(order, list) or len(order) != len(set(order))):
        raise ValueError('expected order must be unique')
    if not targets and not exact and order is None and not created:
        raise ValueError('no verification targets')
    return targets, exact, order, created


def inspect_expected(data, expected):
    targets, exact, order, created = expected
    checks, pending = {'targets': [], 'groups': [], 'created_groups': []}, []
    for (group, code), present in targets.items():
        try:
            actual = code in code_set(data, group)
            passed = actual == present
            gap = None
        except ValueError as error:
            actual, passed, gap = None, False, str(error)
        checks['targets'].append({'group': group, 'code': code, 'present': present,
                                  'actual_present': actual, 'pass': passed, 'gap': gap})
        if not passed:
            pending.append(f'target:{group}:{code}')
    for group, desired in exact.items():
        try:
            actual = code_set(data, group)
            passed = actual == desired
            row = {'group': group, 'expected_count': len(desired), 'actual_count': len(actual),
                   'missing': sorted(desired - actual), 'unexpected': sorted(actual - desired), 'pass': passed}
        except ValueError as error:
            passed = False
            row = {'group': group, 'pass': False, 'gap': str(error)}
        checks['groups'].append(row)
        if not passed:
            pending.append(f'group_set:{group}')
    for group in created:
        passed = group in data['groups']
        checks['created_groups'].append({'group': group, 'pass': passed})
        if not passed:
            pending.append(f'created_group:{group}')
    if order is not None:
        passed = data['order'] == order
        checks['order'] = {'expected': order, 'actual': data['order'], 'pass': passed}
        if not passed:
            pending.append('order')
    return checks, pending


def verify(source, doc, before, output, timeout, interval):
    expected = expectations(doc, before)
    start, attempts, data, error = time.monotonic(), 0, None, None
    snapshot_path = output.with_name(output.stem + '.snapshot.json')
    while True:
        attempts += 1
        try:
            data = snapshot(source)
            checks, pending = inspect_expected(data, expected)
            error = None
        except (ValueError, KeyError, TypeError, IndexError, OSError, plistlib.InvalidFileException) as failure:
            checks, pending, error = {}, ['local_source_unavailable'], str(failure)
        if not pending or time.monotonic() - start >= timeout:
            break
        time.sleep(min(interval, max(0, timeout - (time.monotonic() - start))))
    if data is not None:
        write_json(snapshot_path, data, source)
    receipt = {'schema_version': 'ths-local-verification-1', 'source': 'local_file',
               'verification_method': 'local_file_after_save' if doc.get('settings_saved') else 'local_file_current',
               'verified_at': now(), 'settings_saved': doc.get('settings_saved') is True,
               'no_changes_needed': doc.get('no_changes_needed') is True, 'saved_at': doc.get('saved_at'),
               'pass': not pending, 'attempts': attempts, 'elapsed_seconds': round(time.monotonic() - start, 3),
               'checks': checks, 'pending': pending, 'error': error,
               'snapshot_path': str(snapshot_path.resolve()) if data is not None else None}
    write_json(output, receipt, source)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-dir', type=Path)
    sub = parser.add_subparsers(dest='command', required=True)
    read = sub.add_parser('snapshot'); read.add_argument('--output', type=Path, required=True)
    check = sub.add_parser('verify'); check.add_argument('--expect', type=Path, required=True)
    check.add_argument('--before', type=Path); check.add_argument('--output', type=Path, required=True)
    check.add_argument('--timeout-seconds', type=float, default=8)
    check.add_argument('--interval-seconds', type=float, default=0.5)
    args = parser.parse_args()
    source = (args.source_dir or discover_source()).resolve()
    if args.command == 'snapshot':
        data = make_snapshot(source, args.output)
        result = {'status': 'complete', 'snapshot_path': str(args.output.resolve()),
                  'group_count': data['group_count'], 'known_membership_count': data['known_membership_count'],
                  'groups': data['order'], 'excluded_query_names': [r['name'] for r in data['excluded_query_records']],
                  'gaps': [g['gap'] for g in data['groups'].values() if g.get('gap')]}
    else:
        if not 0 <= args.timeout_seconds <= 30 or not 0 < args.interval_seconds <= 5:
            raise ValueError('verification wait must be bounded: timeout 0..30, interval >0..5 seconds')
        doc = json.loads(args.expect.read_text(encoding='utf-8'))
        before = json.loads(args.before.read_text(encoding='utf-8')) if args.before else None
        receipt = verify(source, doc, before, args.output, args.timeout_seconds, args.interval_seconds)
        result = {key: receipt[key] for key in ('pass', 'verification_method', 'verified_at', 'attempts', 'elapsed_seconds', 'pending', 'error')}
        result.update(receipt_path=str(args.output.resolve()),
                      target_count=len(receipt['checks'].get('targets', [])),
                      changed_group_count=len(receipt['checks'].get('groups', [])),
                      order_verified=receipt['checks'].get('order', {}).get('pass'))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get('pass', True) else 2


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, KeyError, TypeError, IndexError, OSError, plistlib.InvalidFileException) as error:
        print(json.dumps({'status': 'error', 'source': 'local_file', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)

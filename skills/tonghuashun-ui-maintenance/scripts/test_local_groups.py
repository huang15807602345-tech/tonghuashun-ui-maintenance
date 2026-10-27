#!/usr/bin/env python3
"""Behavior tests using isolated native-format fixtures; no live UI changes."""
import base64
import importlib.util
import json
from pathlib import Path
import plistlib
import tempfile
import threading
import time
import unittest
from datetime import datetime, timedelta

spec = importlib.util.spec_from_file_location('local_groups', Path(__file__).with_name('local_groups.py'))
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def vi(number):
    out = bytearray()
    while number >= 128:
        out.append((number & 127) | 128)
        number >>= 7
    out.append(number)
    return bytes(out)


def field(number, value):
    return vi(number * 8 + 2) + vi(len(value)) + value


class LocalGroupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.ids = [240, 243, 40, 234, 323, 999]
        self.group(240, '观察', ['000003'])
        self.group(243, '连板', ['000004'])
        self.group(40, '核心', ['883986'], markets=['48'])
        self.group(234, '机器人', ['000005'])
        self.group(323, '医药', ['000001'])
        self.group(999, '条件选股缓存', ['000006'], query='涨幅>7%')
        self.order(self.ids)
        self.entity(b'StockGroupCommon', field(1, json.dumps({'0': '\b"'}).encode()))
        # A damaged, unreferenced old record must not block current groups.
        self.path(b'\x08' + vi(888)).write_bytes(b'old invalid tombstone')

    def path(self, key):
        return self.source / ('fixture__' + base64.b64encode(key).decode() + '.dat')

    def entity(self, key, value):
        objects = ['$null', {'self.ID': plistlib.UID(2), 'self.value': plistlib.UID(3), 'self.version': 1}, key, {'NS.data': value}]
        doc = {'$version': 100000, '$archiver': 'NSKeyedArchiver', '$top': {'root': plistlib.UID(1)}, '$objects': objects}
        path = self.path(key)
        temporary = path.with_suffix('.tmp')
        temporary.write_bytes(plistlib.dumps(doc, fmt=plistlib.FMT_BINARY))
        temporary.replace(path)

    def group(self, identifier, name, codes, markets=None, query=''):
        markets = markets if markets is not None else ['33'] * len(codes)
        packed = ('|'.join(codes) + ('|' if codes else '') + ',' + '|'.join(markets) + ('|' if markets else '')).encode()
        value = field(1, base64.b64encode(name.encode('gb18030'))) + field(2, base64.b64encode(query.encode('gb18030')) if query else b'') + field(3, packed)
        self.entity(b'\x08' + vi(identifier), value)

    def order(self, identifiers):
        self.entity(b'\x08\x00', field(1, ','.join(format(i, 'x') for i in identifiers).encode()))

    def saved(self, **extra):
        return {'settings_saved': True, 'saved_at': '2026-10-27T10:00:00+08:00', **extra}

    def verify(self, doc, before=None, timeout=0):
        return reader.verify(self.source, doc, before, self.root / 'receipt.json', timeout, .02)

    def test_current_directory_without_history_or_ui(self):
        data = reader.make_snapshot(self.source, self.root / 'snapshot.json')
        self.assertEqual(data['group_count'], 6)
        self.assertEqual(data['order'][:4], ['自选股', '观察', '连板', '核心'])
        self.assertEqual(len(data['excluded_query_records']), 1)
        self.assertIsNone(data['groups']['自选股']['members'])
        self.assertEqual(data['groups']['核心']['members'][0]['market'], '48')

    def test_new_manual_group_does_not_need_old_whitelist(self):
        self.group(1002, '新分类', ['000007'])
        self.order(self.ids + [1002])
        self.assertIn('新分类', reader.snapshot(self.source)['groups'])

    def test_missing_active_record_is_not_an_empty_group(self):
        self.path(b'\x08' + vi(323)).unlink()
        with self.assertRaises(ValueError):
            reader.snapshot(self.source)

    def test_market_mismatch_rejected(self):
        self.group(323, '医药', ['000001'], markets=[])
        with self.assertRaises(ValueError):
            reader.snapshot(self.source)

    def test_saved_add_confirms_code_count_and_exact_delta(self):
        before = reader.snapshot(self.source)
        self.group(323, '医药', ['000001', '000002'])
        result = self.verify(self.saved(changes=[{'group': '医药', 'code': '000002', 'action': 'add'}]), before)
        self.assertTrue(result['pass'])
        self.assertEqual(result['checks']['groups'][0]['actual_count'], 2)

    def test_stale_file_fails_instead_of_claiming_success(self):
        before = reader.snapshot(self.source)
        result = self.verify(self.saved(changes=[{'group': '医药', 'code': '000002', 'action': 'add'}]), before)
        self.assertFalse(result['pass'])

    def test_unexpected_member_is_detected_even_when_target_exists(self):
        before = reader.snapshot(self.source)
        self.group(323, '医药', ['000001', '000002', '009999'])
        result = self.verify(self.saved(changes=[{'group': '医药', 'code': '000002', 'action': 'add'}]), before)
        self.assertFalse(result['pass'])
        self.assertEqual(result['checks']['groups'][0]['unexpected'], ['009999'])

    def test_dual_targets_and_source_removal(self):
        self.group(240, '观察', ['000001'])
        before = reader.snapshot(self.source)
        self.group(234, '机器人', ['000005', '000001'])
        result = self.verify(self.saved(changes=[{'group': '机器人', 'code': '000001', 'action': 'add'}],
            targets=[{'group': '医药', 'code': '000001', 'present': True}, {'group': '机器人', 'code': '000001', 'present': True}]), before)
        self.assertTrue(result['pass'])
        after = reader.snapshot(self.source)
        self.group(240, '观察', [])
        removed = self.verify(self.saved(changes=[{'group': '观察', 'code': '000001', 'action': 'remove'}],
            targets=[{'group': '医药', 'code': '000001', 'present': True}, {'group': '机器人', 'code': '000001', 'present': True}]), after)
        self.assertTrue(removed['pass'])
        self.assertFalse(next(p for p in removed['checks']['targets'] if p['group']=='观察')['actual_present'])

    def test_new_group_creation_and_member_count(self):
        before = reader.snapshot(self.source)
        self.group(1002, '新分类', ['000007'])
        self.order(self.ids + [1002])
        result = self.verify(self.saved(created_groups=['新分类'], changes=[{'group': '新分类', 'code': '000007', 'action': 'add'}]), before)
        self.assertTrue(result['pass'])
        self.assertEqual(result['checks']['groups'][0]['expected_count'], 1)

    def test_order_mismatch_and_saved_order(self):
        desired = ['自选股', '观察', '连板', '核心', '医药', '机器人']
        self.assertFalse(self.verify(self.saved(order=desired))['pass'])
        self.order([240, 243, 40, 323, 234, 999])
        self.assertTrue(self.verify(self.saved(order=desired))['pass'])

    def test_no_change_needs_neither_ui_nor_save(self):
        result = self.verify({'no_changes_needed': True, 'settings_saved': False,
                              'targets': [{'group': '医药', 'code': '000001', 'present': True}]})
        self.assertTrue(result['pass'])
        self.assertEqual(result['verification_method'], 'local_file_current')

    def test_asynchronous_file_update_is_waited_for_locally(self):
        before = reader.snapshot(self.source)
        worker = threading.Thread(target=lambda: (time.sleep(.05), self.group(323, '医药', ['000001', '000002'])))
        worker.start()
        try:
            result = self.verify(self.saved(changes=[{'group': '医药', 'code': '000002', 'action': 'add'}]), before, timeout=1)
        finally:
            worker.join()
        self.assertTrue(result['pass'])
        self.assertGreater(result['attempts'], 1)

    def test_never_writes_application_source(self):
        with self.assertRaises(ValueError):
            reader.make_snapshot(self.source, self.source / 'forbidden.json')

    def test_changed_batch_cannot_claim_no_changes(self):
        with self.assertRaises(ValueError):
            self.verify({'no_changes_needed': True, 'changes': [{'group': '医药', 'code': '000002', 'action': 'add'}]}, reader.snapshot(self.source))

    def test_future_save_time_cannot_prove_a_completed_save(self):
        future = (datetime.now(reader.TZ) + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            self.verify(self.saved(saved_at=future, targets=[{'group': '医药', 'code': '000001', 'present': True}]))


if __name__ == '__main__':
    unittest.main()

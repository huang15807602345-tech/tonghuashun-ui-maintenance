#!/usr/bin/env python3
"""Offline tests with synthetic stock data, no market or UI calls."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest import TestCase, main
import validate_classification as v
import collect_ths_f10 as f

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT/'examples/minimal-valid-classification.json'
AUDIT = ROOT/'examples/minimal-valid-ui-audit.json'


class ClassificationTests(TestCase):
    def setUp(self):
        self.doc = json.loads(DATA.read_text())
        self.audit = json.loads(AUDIT.read_text())

    def check(self, doc=None):
        checks = v.Checks()
        v.validate_classification(self.doc if doc is None else doc, 'pre-ui', checks)
        return checks

    def check_ui(self):
        checks = v.Checks()
        v.validate_ui(self.doc, self.audit, DATA, ['000001'], checks, True)
        return checks

    def test_valid_research_and_receipt(self):
        self.assertTrue(self.check().passed, self.check().items)
        self.assertTrue(self.check_ui().passed, self.check_ui().items)

    def test_missing_all_reasons_cannot_write(self):
        for card in self.doc['rows'][0]['source_reasons'].values():
            card.update(status='missing', reason='')
            card.pop('retrieved_at', None)
        self.assertFalse(self.check().passed)

    def test_additional_website_is_accepted(self):
        card = copy.deepcopy(self.doc['rows'][0]['source_reasons']['tonghuashun'])
        card['url'] = 'https://www.cls.cn/detail/example'
        self.doc['rows'][0]['source_reasons']['cls'] = card
        self.assertTrue(self.check().passed)

    def test_fourth_website_can_fill_a_missing_preferred_source(self):
        reasons = self.doc['rows'][0]['source_reasons']
        card = copy.deepcopy(reasons['tonghuashun']); card['url'] = 'https://www.cls.cn/detail/example'
        reasons['cls'] = card; reasons['tonghuashun'] = {'status':'missing','reason':''}
        self.doc['rows'][0]['reason_selection']['selected_source']='cls'
        self.assertTrue(self.check().passed)

    def test_same_site_subdomains_cannot_count_three_times(self):
        for n, card in enumerate(self.doc['rows'][0]['source_reasons'].values()):
            card['url'] = f'https://sub{n}.10jqka.com.cn/example'
        self.assertFalse(self.check().passed)

    def test_wrong_date_or_not_verified_blocks_writing(self):
        for field, value in [('reason_date','2020-01-01'), ('verified',False), ('material_type','company_profile')]:
            d = copy.deepcopy(self.doc)
            d['rows'][0]['source_reasons']['tonghuashun'][field] = value
            self.assertFalse(self.check(d).passed)

    def test_reprint_requires_original_link(self):
        card = self.doc['rows'][0]['source_reasons']['tonghuashun']
        card['provenance'] = {'kind':'reprint'}
        self.assertFalse(self.check().passed)
        card['provenance']['original_url'] = 'https://www.cls.cn/detail/example'
        self.assertTrue(self.check().passed)

    def test_unverified_stock_can_remain_in_full_report_without_action(self):
        row = self.doc['rows'][0]
        row['classification'].update(status='unclassified',primary_group=None,target_group=None,relation_tier='none',mode='none',assignments=[])
        row['ui_plan'] = {'action':'none','target_group':None,'target_groups':[]}
        row['unclassified_reason'] = '三家原因材料尚未齐全'
        row['unclassified_kind'] = 'insufficient_evidence'
        row['source_reasons'] = {key:{'status':'missing'} for key in ['xuangubao','eastmoney','tonghuashun']}
        row['reason_selection']['selected_source'] = 'unresolved'
        self.doc['summary'] = {'classified_count':0,'unclassified_count':2}
        self.assertTrue(self.check().passed)

    def test_nonmaximized_window_is_valid(self):
        self.audit['preflight']['maximized'] = False
        self.assertTrue(self.check_ui().passed)

    def test_wrong_actual_group_and_missing_readback_fail(self):
        item = self.audit['by_code']['000001']
        item['target_group'] = '错误组'
        self.assertFalse(self.check_ui().passed)
        item['target_group'] = '液冷'; item.pop('verification_method')
        self.assertFalse(self.check_ui().passed)

    def test_malformed_receipt_is_reported_without_exception(self):
        for value in ('pending', None, [], 123):
            self.audit['by_code']['000001'] = value
            self.assertFalse(self.check_ui().passed)

    def test_noop_readback_does_not_force_save(self):
        self.audit['by_code']['000001']['status'] = 'already_present'
        self.audit['by_code']['000001']['targets'][0]['status'] = 'already_present'
        self.audit['settings_saved'] = False
        self.audit['no_changes_needed'] = True
        self.assertTrue(self.check_ui().passed)
        self.audit['by_code']['000001']['status'] = 'added'
        self.assertFalse(self.check_ui().passed)

    def test_population_mismatch_and_false_empty_are_rejected(self):
        self.doc['population']['codes'] = ['000001']
        self.assertFalse(self.check().passed)
        self.doc['rows'] = []; self.doc['population'].update(codes=[],non_st_count=0,codes_sha256=v.codes_sha256([]))
        self.doc['theme_activity'] = {}
        self.doc['summary'] = {'classified_count':0,'unclassified_count':0}
        self.assertFalse(self.check().passed)
        self.doc['population']['empty_confirmed'] = True
        self.assertTrue(self.check().passed)

    def test_functional_groups_cannot_be_removed(self):
        row = self.doc['rows'][0]
        row['ui_plan'].update(action='move',source_groups=['核心'])
        row['classification']['existing_wrong_groups']=['核心']
        self.doc['group_snapshot']['groups'].append('核心'); self.doc['group_snapshot']['ui_total'] += 1
        self.assertFalse(self.check().passed)

    def test_core_cannot_be_an_automatic_theme_target(self):
        row = self.doc['rows'][0]
        row['classification']['target_group']='核心';row['ui_plan']['target_group']='核心'
        self.doc['group_snapshot']['groups'].append('核心');self.doc['group_snapshot']['ui_total']+=1
        self.assertFalse(self.check().passed)

    def test_source_removal_must_be_proven(self):
        row=self.doc['rows'][0];row['ui_plan'].update(action='move',source_groups=['消费'])
        row['classification']['existing_wrong_groups']=['消费']
        self.assertTrue(self.check().passed)
        self.audit['by_code']['000001']['status']='moved'
        self.assertFalse(self.check_ui().passed)
        self.audit['by_code']['000001']['verified_absent_source_groups']=['消费']
        self.assertTrue(self.check_ui().passed)

    def test_malformed_research_fields_return_errors(self):
        for field in ('code','source_reasons','classification','ui_plan','market_context_evidence'):
            for value in (None, [], 123):
                d=copy.deepcopy(self.doc);d['rows'][0][field]=value
                self.assertFalse(self.check(d).passed, (field,value))

    def test_ui_manifest_cannot_bypass_research_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory)/'input.json', Path(directory)/'manifest.json'
            self.doc['rows'][0]['source_reasons']['tonghuashun']['verified']=False
            source.write_text(json.dumps(self.doc))
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/build_ui_manifest.py'),'--input',str(source),'--output',str(output)],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(output.exists())

    def test_init_uses_caller_directory_and_preserves_existing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            cmd=[sys.executable,'-B',str(ROOT/'scripts/init_run.py'),'--date','2026-09-09']
            first=json.loads(subprocess.run(cmd,cwd=directory,capture_output=True,text=True,check=True).stdout)
            manifest=Path(first['manifest']);raw=manifest.read_bytes()
            self.assertTrue(manifest.is_relative_to(Path(directory).resolve()))
            second=json.loads(subprocess.run(cmd,cwd=directory,capture_output=True,text=True,check=True).stdout)
            self.assertFalse(second['created']);self.assertEqual(raw,manifest.read_bytes())

    def test_f10_wrong_or_missing_date_is_partial(self):
        for material in ('2020-01-01 涨停原因：旧日公告','涨停原因：未注明日期'):
            raw=f'<title>示例</title><span class="open_btn">涨停分析</a><div class="check_else">{material}</div>'.encode('gbk')
            row=f.parse_page('000001',raw,Path('/not-used.html'),'https://basic.10jqka.com.cn/000001/','2026-08-26','2026-08-26T16:00:00+08:00')
            self.assertEqual(row['status'],'partial');self.assertFalse(row['verified'])

    def test_f10_same_day_material_still_requires_source_verification(self):
        raw='<title>示例</title><span class="open_btn">涨停分析</a><div class="check_else">2026-08-26 涨停原因：公告</div>'.encode('gbk')
        row=f.parse_page('000001',raw,Path('/not-used.html'),'https://basic.10jqka.com.cn/000001/','2026-08-26','2026-08-26T16:00:00+08:00')
        self.assertEqual(row['status'],'complete');self.assertFalse(row['verified'])
        self.assertEqual(row['reason_date'],'2026-08-26')

    def test_code_file_date_must_match_request(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'codes.json';p.write_text(json.dumps({'trade_date':'2020-01-01','codes':['000001'],'risk_warning_filtered':True}))
            with self.assertRaises(SystemExit):f.load_codes(p,'2026-08-26')

    def make_dual(self):
        row = self.doc['rows'][0]
        second = copy.deepcopy(row['classification']['assignments'][0])
        second.update(primary_group='消费',target_group='消费',market_trading_reason='合成样本：消费订单也是当日并列原因',confidence='medium')
        row['classification'].update(mode='dual',primary_group=None,target_group=None,dual_basis='两条实际交易路径各有证据且无法判断明显主次')
        row['classification']['assignments'].append(second)
        row['ui_plan'].update(target_group=None,target_groups=['液冷','消费'])
        self.doc['theme_activity']['消费'] = copy.deepcopy(self.doc['theme_activity']['液冷'])
        row['theme_filter_results']['消费']='include'
        item=self.audit['by_code']['000001'];item.pop('target_group');item.pop('verified_target_group')
        proof=copy.deepcopy(item['targets'][0]);proof.update(target_group='消费',verified_target_group='消费')
        item['targets'].append(proof)

    def add_exploration(self):
        row=self.doc['rows'][0];row['reason_selection']['initial_confidence']='low'
        row['exploratory_research']={'status':'completed','questions':['为何液冷而非泛硬件？'],'searches':[{'query':'示例股票 日期 订单 液冷','channel':'公告与行情','evidence_refs':['synthetic://original'],'findings':'实际产品订单与关键拉升时段一致'}],'conclusion':'补查后主分类达到中高置信度','trend_analysis':{'status':'completed','candidate_groups':['液冷','硬件'],'representatives':['000003'],'time_range':'09:30-10:30','granularity':'1分钟','evidence_refs':['synthetic://intraday'],'observations':'液冷代表股启动后跟随，硬件候选未同步','market_comparison':'该时段大盘平稳，共同变化不只来自指数'}}

    def test_dual_causes_require_and_accept_both_saved_targets(self):
        self.make_dual();self.assertTrue(self.check().passed,self.check().items)
        self.assertTrue(self.check_ui().passed,self.check_ui().items)
        self.audit['by_code']['000001']['targets'].pop()
        self.assertFalse(self.check_ui().passed)

    def test_dual_low_confidence_or_duplicate_group_is_rejected(self):
        self.make_dual();self.doc['rows'][0]['classification']['assignments'][1]['confidence']='low'
        self.assertFalse(self.check().passed)
        self.doc['rows'][0]['classification']['assignments'][1]['confidence']='medium'
        self.doc['rows'][0]['classification']['assignments'][1]['target_group']='液冷'
        self.doc['rows'][0]['ui_plan']['target_groups']=['液冷','液冷']
        self.assertFalse(self.check().passed)

    def test_dual_valid_group_cannot_be_removed(self):
        self.make_dual();row=self.doc['rows'][0]
        row['ui_plan'].update(action='move',source_groups=['消费'])
        row['classification']['existing_wrong_groups']=['消费']
        self.assertFalse(self.check().passed)

    def test_two_causes_in_one_canonical_theme_are_not_dual_classification(self):
        self.make_dual();self.doc['rows'][0]['classification']['assignments'][1]['primary_group']='液冷'
        self.assertFalse(self.check().passed)

    def test_dual_manifest_carries_both_targets_and_removal_dependency(self):
        self.make_dual();row=self.doc['rows'][0]
        self.doc['group_snapshot']['groups'].append('旧组');self.doc['group_snapshot']['ui_total']+=1
        row['ui_plan'].update(action='move',source_groups=['旧组']);row['classification']['existing_wrong_groups']=['旧组']
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'input.json';out=Path(folder)/'manifest.json';p.write_text(json.dumps(self.doc))
            result=subprocess.run([sys.executable,'-B',str(ROOT/'scripts/build_ui_manifest.py'),'--input',str(p),'--output',str(out)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            action=json.loads(out.read_text())['actions'][0]
            self.assertEqual(action['target_groups'],['液冷','消费'])
            self.assertEqual(action['removal_requires_all_targets_verified'],['液冷','消费'])
            self.assertEqual(len(action['target_actions']),2)

    def test_low_confidence_requires_search_and_trend_before_promotion(self):
        self.doc['rows'][0]['reason_selection']['initial_confidence']='low'
        self.assertFalse(self.check().passed)
        self.add_exploration();self.assertTrue(self.check().passed,self.check().items)
        self.doc['rows'][0]['exploratory_research'].pop('trend_analysis')
        self.assertFalse(self.check().passed)

    def test_unavailable_trend_must_record_attempts_and_gap(self):
        self.add_exploration();trend=self.doc['rows'][0]['exploratory_research']['trend_analysis']
        trend.clear();trend.update(status='unavailable',candidate_groups=['液冷'])
        self.assertFalse(self.check().passed)
        trend.update(attempted_channels=['分钟数据接口','公开分时图'],limitations='均不可获得；公告证据补强但盘面归因保留缺口')
        self.assertTrue(self.check().passed,self.check().items)

    def test_final_low_confidence_cannot_write_even_after_search(self):
        self.add_exploration();self.doc['rows'][0]['reason_selection']['confidence']='low'
        self.assertFalse(self.check().passed)

    def test_any_two_exclusion_combinations(self):
        a=self.doc['theme_activity']['液冷']
        # D只有目标一股，十日只有两股：即使不是小众，也按已确认的任意两项排除。
        a['history']['codes']=['000001','000003']
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'exclude')
        a['history']['codes'].append('000004');a['niche']['value']=True
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'exclude')
        a['today']['codes']=['000001','000003'];a['history']['codes']=['000001','000003']
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'exclude')
        a['niche']['value']=False
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'include')

    def test_exact_three_distinct_stocks_does_not_trigger_history_rule(self):
        a=self.doc['theme_activity']['液冷']
        self.assertEqual(v.theme_filter(a,'000001')['conditions'],[True,False,False])
        self.assertTrue(self.check().passed)
        a['history']['codes']=['000001','000001','000003']
        self.assertFalse(self.check().passed)

    def test_unknown_history_is_not_zero_or_false(self):
        a=self.doc['theme_activity']['液冷'];a['history']={'status':'unavailable','codes':None,'gap':'历史池缺两日'}
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'pending')
        self.assertFalse(self.check().passed)
        a['niche']['value']=True
        self.assertEqual(v.theme_filter(a,'000001')['decision'],'exclude')
        a['history']['codes']=[]
        self.assertFalse(self.check().passed)

    def test_history_window_must_include_d_and_today_members(self):
        h=self.doc['theme_activity']['液冷']['history'];h['trading_dates']=h['trading_dates'][:-1]
        self.assertFalse(self.check().passed)
        self.setUp();self.doc['theme_activity']['液冷']['history']['codes']=['000003','000004','000005']
        self.assertFalse(self.check().passed)

    def test_today_activity_cannot_use_stocks_outside_final_pool(self):
        self.doc['theme_activity']['液冷']['today']['codes'].append('000099')
        self.assertFalse(self.check().passed)

    def test_excluded_direction_does_not_force_other_dual_candidate_out(self):
        self.make_dual();row=self.doc['rows'][0]
        self.doc['theme_activity']['消费']['niche']['value']=True
        row['theme_filter_results']['消费']='exclude'
        self.assertFalse(self.check().passed)
        row['classification']['assignments'].pop();row['classification'].update(mode='single',primary_group='液冷',target_group='液冷')
        row['ui_plan'].update(target_group='液冷',target_groups=['液冷'])
        self.assertTrue(self.check().passed,self.check().items)

    def test_niche_excluded_row_requires_matching_counts_and_no_write(self):
        row=self.doc['rows'][0];self.doc['theme_activity']['液冷']['niche']['value']=True
        row['theme_filter_results']['液冷']='exclude'
        row['classification'].update(status='unclassified',mode='none',assignments=[],primary_group=None,target_group=None)
        row['ui_plan'].update(action='none',target_group=None,target_groups=[])
        row.update(unclassified_kind='niche_excluded',unclassified_reason='当日剔除自身0只，且极小众无驱动；统计依据见theme_activity')
        self.doc['summary']={'classified_count':0,'unclassified_count':2}
        self.assertTrue(self.check().passed,self.check().items)
        self.doc['theme_activity']['液冷']['niche']['value']=False
        self.assertFalse(self.check().passed)

    def test_old_schema_cannot_start_new_ui_work(self):
        self.doc['schema_version']='3.0'
        self.assertFalse(self.check().passed)

    def test_recent_linked_members_can_support_one_today_member_new_group(self):
        self.doc['group_snapshot']['groups'].remove('液冷');self.doc['group_snapshot']['ui_total']-=1
        self.doc['new_groups']=[{'name':'液冷','members':['000001'],'linked_members':['000001','000003','000004'],'not_reusing_reason':'当前无相关已有组','market_linkage_evidence':'合成样本：近十日有三个直接活跃成员','creation_authorized':True}]
        self.assertTrue(self.check().passed,self.check().items)

    def test_verified_three_stock_lower_bound_avoids_unnecessary_full_history(self):
        h=self.doc['theme_activity']['液冷']['history'];h['status']='verified_at_least_three'
        h['occurrences']=[{'code':c,'date':d,'evidence_refs':['synthetic://dated-final-cause']} for c,d in zip(h['codes'],['2026-08-26','2026-08-25','2026-08-24'])]
        self.assertTrue(self.check().passed,self.check().items)
        h['occurrences'].pop();self.assertFalse(self.check().passed)

    def test_lower_bound_cannot_be_used_to_claim_fewer_than_three(self):
        h=self.doc['theme_activity']['液冷']['history'];h.update(status='verified_at_least_three',codes=['000001','000003'])
        self.assertFalse(self.check().passed)
        self.assertIsNone(v.theme_filter(self.doc['theme_activity']['液冷'],'000001')['conditions'][2])

    def test_skipped_irrelevant_history_remains_unknown_without_blocking_result(self):
        a=self.doc['theme_activity']['液冷'];a['today']['codes']=['000001','000002'];a['history']={'status':'not_needed','codes':None,'gap':'当日有其它同类且不是小众无驱动，第三项不影响结果'}
        self.assertEqual(v.theme_filter(a,'000001'),{'conditions':[False,False,None],'decision':'include'})
        self.assertTrue(self.check().passed,self.check().items)


if __name__=='__main__':
    main()

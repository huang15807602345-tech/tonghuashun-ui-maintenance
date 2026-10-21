import copy
import importlib.util
import itertools
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("planner", ROOT/"skills/tonghuashun-ui-maintenance/scripts/plan_group_order.py")
planner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(planner)


class OrderingTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT/"skills/tonghuashun-ui-maintenance/examples/sorting-input.json").read_text(encoding="utf-8"))

    def test_counts_and_requested_prefix(self):
        plan = planner.plan_order(self.data)
        self.assertEqual(plan["target_order"], ["自选股", "观察", "示例组乙", "示例组甲", "示例组丙"])
        self.assertEqual(plan["group_counts"]["示例组乙"], 2)
        self.assertFalse(plan["ui_executed"])

    def test_reverse_pin_sequence_reaches_exact_order(self):
        for ordering in itertools.permutations(self.data["groups"][1:]):
            data = copy.deepcopy(self.data)
            data["groups"] = [data["groups"][0], *ordering]
            plan = planner.plan_order(data)
            actual = [group["name"] for group in data["groups"]]
            for name in plan["pin_to_top"]:
                actual.remove(name); actual.insert(1, name)
            self.assertEqual(actual, plan["target_order"])

    def test_ties_preserve_observed_order(self):
        self.data["groups"][1]["members"] = []
        plan = planner.plan_order(self.data)
        self.assertLess(plan["target_order"].index("示例组甲"), plan["target_order"].index("示例组丙"))

    def test_duplicates_and_non_a_share_members(self):
        self.data["groups"][1]["members"] = ["000001", "000001", "KS11"]
        self.assertEqual(planner.plan_order(self.data)["group_counts"]["示例组甲"], 1)

    def test_already_correct_needs_no_clicks(self):
        order = planner.plan_order(self.data)["target_order"]
        by_name = {g["name"]: g for g in self.data["groups"]}
        self.data["groups"] = [by_name[name] for name in order]
        plan = planner.plan_order(self.data)
        self.assertTrue(plan["no_changes_needed"])
        self.assertEqual(plan["pin_to_top"], [])

    def test_missing_or_incomplete_data_is_not_zero(self):
        for key in ["final_data_verified", "risk_warning_filtered"]:
            data = copy.deepcopy(self.data); data[key] = False
            with self.assertRaises(ValueError): planner.plan_order(data)
        self.data["groups"][1]["complete"] = False
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_zero_pool_requires_confirmation(self):
        self.data["non_st_final_limit_up_codes"] = []
        with self.assertRaises(ValueError): planner.plan_order(self.data)
        self.data["empty_confirmed"] = True
        self.assertEqual(set(planner.plan_order(self.data)["group_counts"].values()), {0})

    def test_missing_prefix_does_not_create_groups(self):
        self.data["fixed_prefix"].append("不存在的组")
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_duplicate_names_rejected(self):
        self.data["groups"].append(copy.deepcopy(self.data["groups"][1]))
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_system_group_is_not_moved(self):
        self.data["groups"] = list(reversed(self.data["groups"]))
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_numeric_codes_cannot_lose_leading_zero(self):
        self.data["non_st_final_limit_up_codes"] = [1]
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_member_totals_must_match(self):
        self.data["groups"][1]["ui_total"] = 2
        with self.assertRaises(ValueError): planner.plan_order(self.data)

    def test_input_is_not_mutated(self):
        before = copy.deepcopy(self.data)
        planner.plan_order(self.data)
        self.assertEqual(before, self.data)

    def test_malformed_inputs_are_rejected(self):
        for value in (None, [], "data"):
            with self.assertRaises(ValueError): planner.plan_order(value)


if __name__ == "__main__":
    unittest.main()

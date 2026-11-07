import unittest
from datetime import datetime, timedelta
from src.planner import (
    generate_plan,
    realign_or_resume_plan,
    compute_metrics,
    compute_week_number,
    update_plan_availability,
    recalculate_future_schedule,
)


class PlannerTestCase(unittest.TestCase):
    def test_planner_algorithm(self):
        availability = {
            "Monday": 2.0,
            "Tuesday": 2.0,
            "Wednesday": 0.0,
            "Thursday": 2.0,
            "Friday": 2.0,
            "Saturday": 4.0,
            "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        self.assertEqual(plan["total_problems"], 495)
        self.assertGreater(plan["total_study_days"], 0)
        self.assertGreater(plan["total_rest_days"], 0)
        self.assertIsNotNone(plan["target_completion_date"])
        self.assertIn("total_weeks", plan)
        self.assertGreater(plan["total_weeks"], 0)

        # Verify each day has week_number and that days 0..6 belong to week 1
        for idx, day in enumerate(plan["schedule"]):
            self.assertIn("week_number", day)
            self.assertEqual(day["week_number"], (idx // 7) + 1)

        # Verify problems contain slug and takeuforward practice_link only when article_link is absent
        all_problems = [p for d in plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(all_problems), 495)

        pattern_1 = next((p for p in all_problems if p.get("slug") == "pattern-1"), None)
        self.assertIsNotNone(pattern_1)
        self.assertEqual(pattern_1["slug"], "pattern-1")
        self.assertIsNone(pattern_1.get("article_link"))
        self.assertEqual(pattern_1["practice_link"], "https://takeuforward.org/practice/dsa/pattern-1")

        breaking_myth = next((p for p in all_problems if p.get("slug") == "breaking-the-myth"), None)
        self.assertIsNotNone(breaking_myth)
        self.assertIsNotNone(breaking_myth.get("article_link"))
        self.assertIsNone(breaking_myth.get("practice_link"))

        # Verify all problems: if article_link present, practice_link is None; else practice_link is set
        for p in all_problems:
            self.assertTrue(p["slug"])
            if p.get("article_link"):
                self.assertIsNone(p.get("practice_link"))
            else:
                self.assertEqual(p["practice_link"], f"https://takeuforward.org/practice/dsa/{p['slug']}")

        # Test metrics
        metrics = compute_metrics(plan, current_date_str="2026-10-19")
        self.assertEqual(metrics["completed_problems"], 0)
        self.assertEqual(metrics["completion_percent"], 0.0)
        self.assertIsNotNone(metrics["today_day_data"])

    def test_week_number_strictly_monday_to_sunday(self):
        # 2026-10-19 is a Monday
        start = "2026-10-19"
        self.assertEqual(compute_week_number("2026-10-19", start), 1)  # Mon
        self.assertEqual(compute_week_number("2026-10-25", start), 1)  # Sun
        self.assertEqual(compute_week_number("2026-10-26", start), 2)  # Mon
        self.assertEqual(compute_week_number("2026-11-01", start), 2)  # Sun
        self.assertEqual(compute_week_number("2026-11-02", start), 3)  # Mon

        # Start mid-week: 2026-10-21 is a Wednesday
        start_wed = "2026-10-21"
        self.assertEqual(compute_week_number("2026-10-21", start_wed), 1)  # Wed
        self.assertEqual(compute_week_number("2026-10-25", start_wed), 1)  # Sun
        self.assertEqual(compute_week_number("2026-10-26", start_wed), 2)  # Mon
        self.assertEqual(compute_week_number("2026-11-01", start_wed), 2)  # Sun

    def test_realign_or_resume_plan(self):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        first_study_day = next(d for d in plan["schedule"] if d.get("type") == "study")
        for p in first_study_day["problems"]:
            p["completed"] = True
            p["completed_at"] = "2026-10-19T10:00:00"
        first_study_day["completed"] = True

        resumed = realign_or_resume_plan(plan, resume_date_str="2026-11-01")
        self.assertFalse(resumed["is_paused"])
        self.assertEqual(resumed["total_problems"], 495)
        self.assertGreater(resumed["total_study_days"], 0)

        # Verify completed day was retained
        completed_days = [d for d in resumed["schedule"] if d.get("completed")]
        self.assertEqual(len(completed_days), 1)

    def test_update_plan_availability_hours_and_5_day(self):
        initial_avail = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 4.0
        }
        plan = generate_plan(initial_avail, start_date_str="2026-10-19")

        # Mark Day 1 & Day 2 problems as completed and mark 2 problems for revision
        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        d1 = study_days[0]
        d2 = study_days[1]
        for p in d1["problems"]:
            p["completed"] = True
            p["completed_at"] = "2026-10-19T12:00:00"
        d1["completed"] = True

        rev_p1_uid = d1["problems"][0]["uid"]
        d1["problems"][0]["revision"] = True
        d1["problems"][0]["revision_marked_at"] = "2026-10-19T13:00:00"

        rev_p2_uid = d2["problems"][0]["uid"]
        d2["problems"][0]["revision"] = True
        d2["problems"][0]["revision_marked_at"] = "2026-10-20T14:00:00"

        completed_count_before = sum(1 for d in plan["schedule"] for p in d.get("problems", []) if p.get("completed"))
        self.assertEqual(completed_count_before, len(d1["problems"]))

        # Switch to 5-day plan (weekends 0h) with different hours
        new_avail = {
            "Monday": 2.5, "Tuesday": 2.5, "Wednesday": 2.5,
            "Thursday": 2.5, "Friday": 2.5, "Saturday": 0.0, "Sunday": 0.0
        }

        updated = update_plan_availability(
            plan, new_avail, from_date_str="2026-10-21"
        )

        # 1. Total problems preserved
        all_problems_after = [p for d in updated["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(all_problems_after), 495)

        # 2. Completed count strictly preserved
        completed_count_after = sum(1 for p in all_problems_after if p.get("completed"))
        self.assertEqual(completed_count_after, completed_count_before)

        # 3. REVISION QUESTIONS STRICTLY PRESERVED AND NEVER UNMARKED
        rev_after = [p for p in all_problems_after if p.get("revision")]
        self.assertEqual(len(rev_after), 2)
        rev_uids = [p["uid"] for p in rev_after]
        self.assertIn(rev_p1_uid, rev_uids)
        self.assertIn(rev_p2_uid, rev_uids)

        # 4. Saturday and Sunday are now rest days in the future schedule
        future_days = [d for d in updated["schedule"] if d.get("date") >= "2026-10-21"]
        for d in future_days:
            if d.get("day_name") in ["Saturday", "Sunday"]:
                self.assertEqual(d.get("type"), "rest")
            else:
                self.assertEqual(d.get("type"), "study")

    def test_recalculate_ahead_of_schedule_problem(self):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        day3 = study_days[2]
        day7 = study_days[6]

        day7_first_problem = day7["problems"][0]
        day7_prob_uid = day7_first_problem["uid"]
        old_day3_prob_count = len(day3["problems"])
        old_target_date = plan["target_completion_date"]

        # 1. Complete Day 7 question while on Day 3
        updated_plan, was_recalc, was_moved, old_t, new_t = recalculate_future_schedule(
            plan, today_date_str=day3["date"], problem_completed_uid=day7_prob_uid
        )

        self.assertTrue(was_recalc)
        self.assertTrue(was_moved)
        self.assertEqual(old_t, old_target_date)

        # 2. Check problem moved into Day 3
        new_study_days = [d for d in updated_plan["schedule"] if d.get("type") == "study"]
        new_day3 = new_study_days[2]
        new_day3_uids = [p["uid"] for p in new_day3["problems"]]
        self.assertIn(day7_prob_uid, new_day3_uids)
        self.assertEqual(len(new_day3["problems"]), old_day3_prob_count + 1)

        moved_p = next(p for p in new_day3["problems"] if p["uid"] == day7_prob_uid)
        self.assertTrue(moved_p["completed"])
        self.assertIsNotNone(moved_p["completed_at"])

        # 3. Check Day 7 was backfilled and no longer has day7_prob_uid
        new_day7 = new_study_days[6]
        new_day7_uids = [p["uid"] for p in new_day7["problems"]]
        self.assertNotIn(day7_prob_uid, new_day7_uids)
        self.assertGreater(len(new_day7["problems"]), 0)

        # 4. Check all 495 problems are preserved without duplicates or omissions
        all_problems = [p for d in updated_plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(all_problems), 495)
        self.assertEqual(len(set(p["uid"] for p in all_problems)), 495)

    def test_backlog_problem_stay_in_past_day(self):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        day1 = study_days[0]
        day3 = study_days[2]

        day1_prob_uid = day1["problems"][0]["uid"]

        # Completing Day 1 problem while on Day 3 should NOT move it to Day 3
        updated_plan, was_recalc, was_moved, old_t, new_t = recalculate_future_schedule(
            plan, today_date_str=day3["date"], problem_completed_uid=day1_prob_uid
        )

        self.assertFalse(was_recalc)
        self.assertFalse(was_moved)

    def test_update_weekly_plan_after_solving_early_preserves_all_problems(self):
        """
        Verify that when a user has a 7-day plan, solves several questions early,
        and updates their weekly plan to e.g. 5 days, all questions (both completed
        and incomplete) remain in the schedule and syllabus (all 495 problems).
        Subsequent ahead-of-time solves must also never drop previously completed questions.
        """
        initial_avail = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(initial_avail, start_date_str="2026-11-06")
        self.assertEqual(sum(len(d.get("problems", [])) for d in plan["schedule"]), 495)

        # 1. Solve problems early from future days
        p1_uid = plan["schedule"][1]["problems"][0]["uid"]
        p2_uid = plan["schedule"][2]["problems"][0]["uid"]

        plan, was_recalc1, was_moved1, _, _ = recalculate_future_schedule(
            plan, today_date_str="2026-11-06", problem_completed_uid=p1_uid
        )
        self.assertTrue(was_moved1)

        plan, was_recalc2, was_moved2, _, _ = recalculate_future_schedule(
            plan, today_date_str="2026-11-06", problem_completed_uid=p2_uid
        )
        self.assertTrue(was_moved2)

        completed_before_update = sum(1 for d in plan["schedule"] for p in d.get("problems", []) if p.get("completed"))
        self.assertEqual(completed_before_update, 2)

        # 2. User updates weekly availability (e.g. switch to 5-day plan with different hours)
        new_avail = {
            "Monday": 2.5, "Tuesday": 2.5, "Wednesday": 2.5,
            "Thursday": 2.5, "Friday": 2.5, "Saturday": 0.0, "Sunday": 0.0
        }
        updated_plan = update_plan_availability(plan, new_avail, from_date_str="2026-11-06")

        # Check total problems after update is strictly 495
        all_probs_after = [p for d in updated_plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(all_probs_after), 495)
        self.assertEqual(len(set(p["uid"] for p in all_probs_after)), 495)

        # Check completed questions are preserved
        completed_after_update = sum(1 for p in all_probs_after if p.get("completed"))
        self.assertEqual(completed_after_update, completed_before_update)
        completed_uids = [p["uid"] for p in all_probs_after if p.get("completed")]
        self.assertIn(p1_uid, completed_uids)
        self.assertIn(p2_uid, completed_uids)

        # Future days must not contain already-completed problems
        future_study_days = [d for d in updated_plan["schedule"] if d.get("date") > "2026-11-06"]
        completed_in_future = sum(1 for d in future_study_days for p in d.get("problems", []) if p.get("completed"))
        self.assertEqual(completed_in_future, 0)

        # 3. User now solves another question ahead of schedule
        future_p3_uid = [p["uid"] for d in future_study_days for p in d.get("problems", []) if not p.get("completed")][0]
        final_plan, was_recalc3, was_moved3, _, _ = recalculate_future_schedule(
            updated_plan, today_date_str="2026-11-06", problem_completed_uid=future_p3_uid
        )
        self.assertTrue(was_moved3)

        # Final check: absolutely all 495 problems must be present
        final_probs = [p for d in final_plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(final_probs), 495)
        self.assertEqual(len(set(p["uid"] for p in final_probs)), 495)

        # All 3 completed questions must be completed and present
        final_completed_uids = [p["uid"] for p in final_probs if p.get("completed")]
        self.assertEqual(len(final_completed_uids), 3)
        self.assertIn(p1_uid, final_completed_uids)
        self.assertIn(p2_uid, final_completed_uids)
        self.assertIn(future_p3_uid, final_completed_uids)


if __name__ == "__main__":
    unittest.main()

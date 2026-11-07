import unittest
from unittest.mock import MagicMock
from src.planner import generate_plan
from src.storage import PlanlyMongoStorage


class StorageTestCase(unittest.TestCase):
    def test_storage_problem_status_update_in_place(self):
        storage = PlanlyMongoStorage()
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        day1 = plan["schedule"][0]
        prob_uid = day1["problems"][0]["uid"]

        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = plan
        storage.db = mock_db

        updated_plan = storage.update_problem_status(prob_uid, True)
        self.assertIsNotNone(updated_plan)
        first_prob = updated_plan["schedule"][0]["problems"][0]
        self.assertTrue(first_prob["completed"])
        self.assertIsNotNone(first_prob["completed_at"])

        if storage.client:
            storage.client.close()

    def test_storage_realtime_ahead_of_schedule(self):
        storage = PlanlyMongoStorage()
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        day3 = study_days[2]
        day7 = study_days[6]
        day7_prob_uid = day7["problems"][0]["uid"]

        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = plan
        storage.db = mock_db

        updated_plan, recalc_meta = storage.update_problem_status(
            day7_prob_uid, True, current_date_str=day3["date"], return_meta=True
        )

        self.assertTrue(recalc_meta["recalculated"])
        self.assertTrue(recalc_meta["moved_to_today"])
        self.assertIsNotNone(recalc_meta["new_target_date"])

        # Check mock_db saved the updated plan
        mock_db.plans.replace_one.assert_called()

        if storage.client:
            storage.client.close()

    def test_storage_reset_progress_preserves_revisions(self):
        storage = PlanlyMongoStorage()
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")

        # Mark 3 problems completed and 2 marked for revision
        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        p1 = study_days[0]["problems"][0]
        p2 = study_days[0]["problems"][1]
        p3 = study_days[1]["problems"][0]

        p1["completed"] = True
        p1["completed_at"] = "2026-10-19T10:00:00"
        p1["revision"] = True
        p1["revision_marked_at"] = "2026-10-19T10:05:00"

        p2["completed"] = True
        p2["completed_at"] = "2026-10-19T11:00:00"

        p3["completed"] = True
        p3["completed_at"] = "2026-10-20T10:00:00"
        p3["revision"] = True
        p3["revision_marked_at"] = "2026-10-20T10:05:00"

        # Mock database
        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = plan

        # Return the progress records that should be retained (the 2 revisions)
        mock_cursor = [
            {"problem_uid": p1["uid"], "revision": True, "revision_marked_at": "2026-10-19T10:05:00"},
            {"problem_uid": p3["uid"], "revision": True, "revision_marked_at": "2026-10-20T10:05:00"}
        ]
        mock_db.problem_progress.find.return_value = mock_cursor
        storage.db = mock_db

        # 1. Reset progress retaining original schedule
        reset_same_calendar = storage.reset_progress(restart_schedule=False)
        self.assertIsNotNone(reset_same_calendar)

        all_problems_1 = [p for d in reset_same_calendar["schedule"] for p in d.get("problems", [])]
        completed_count_1 = sum(1 for p in all_problems_1 if p.get("completed"))
        self.assertEqual(completed_count_1, 0)

        # 2. Reset progress with rescheduled start date
        reset_rescheduled = storage.reset_progress(restart_schedule=True, start_date_str="2026-11-03")
        self.assertIsNotNone(reset_rescheduled)
        self.assertEqual(reset_rescheduled["start_date"], "2026-11-03")

        all_problems_2 = [p for d in reset_rescheduled["schedule"] for p in d.get("problems", [])]
        completed_count_2 = sum(1 for p in all_problems_2 if p.get("completed"))
        self.assertEqual(completed_count_2, 0)

        # In both cases, revision problems must still be marked
        revisions_retained = [p for p in all_problems_2 if p.get("revision")]
        self.assertEqual(len(revisions_retained), 2)
        rev_uids = [p["uid"] for p in revisions_retained]
        self.assertIn(p1["uid"], rev_uids)
        self.assertIn(p3["uid"], rev_uids)

        if storage.client:
            storage.client.close()

    def test_auto_heal_missing_problems(self):
        storage = PlanlyMongoStorage()
        if not storage.get_engine_info()["connected"]:
            self.skipTest("MongoDB not available")

        storage.reset_plan()
        avail = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(avail, start_date_str="2026-11-06")
        storage.save_plan(plan)
        self.assertIsNotNone(plan)

        # Corrupt the plan document by removing 10 problems
        all_problems = [p for d in plan["schedule"] for p in d.get("problems", [])]
        removed_probs = all_problems[-10:]
        removed_uids = {p["uid"] for p in removed_probs}

        # Mark 3 of the removed ones as completed in problem_progress
        for p in removed_probs[:3]:
            storage.db.problem_progress.update_one(
                {"problem_uid": p["uid"]},
                {"$set": {"problem_uid": p["uid"], "completed": True, "completed_at": "2026-11-06T12:00:00"}},
                upsert=True
            )

        corrupted_schedule = []
        for d in plan["schedule"]:
            cd = dict(d)
            cd["problems"] = [p for p in d.get("problems", []) if p["uid"] not in removed_uids]
            corrupted_schedule.append(cd)

        storage.db.plans.update_one(
            {"id": "current_plan"},
            {"$set": {"schedule": corrupted_schedule, "total_problems": len(all_problems) - 10}}
        )

        # Calling get_plan should automatically heal the schedule
        healed_plan = storage.get_plan()
        healed_problems = [p for d in healed_plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(healed_problems), 495)
        self.assertEqual(len(set(p["uid"] for p in healed_problems)), 495)

        # The 3 completed removed problems should be marked completed
        for p in removed_probs[:3]:
            healed_p = next((hp for hp in healed_problems if hp["uid"] == p["uid"]), None)
            self.assertIsNotNone(healed_p)
            self.assertTrue(healed_p.get("completed"))

        if storage.client:
            storage.client.close()


if __name__ == "__main__":
    unittest.main()

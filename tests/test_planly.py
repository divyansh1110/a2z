import unittest
import os
import json
from unittest.mock import patch, MagicMock
from src.app import app
from src.logger import LOG_FILE
from src.planner import generate_plan, realign_or_resume_plan, compute_metrics

class PlanlySrcTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_logger_file_created(self):
        # Verify logs directory and log file exist
        self.assertTrue(os.path.exists(LOG_FILE))
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("[planly]", content)

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

    def test_index_route(self):
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        self.assertIn(b"Planly", res.data)
        self.assertIn(b"MongoDB", res.data)

    def test_status_endpoint(self):
        res = self.client.get("/api/status")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn("database", data)
        self.assertEqual(data["database"]["backend"], "mongodb")
        self.assertIn("connected", data["database"])

    def test_syllabus_endpoint(self):
        res = self.client.get("/api/syllabus")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["topics_summary"]), 20)
        self.assertEqual(data["total_problems"], 495)
        self.assertEqual(len(data["problems"]), 495)

    @patch("src.app.storage")
    def test_create_and_manage_plan_with_mongo(self, mock_storage):
        mock_storage.get_engine_info.return_value = {
            "backend": "mongodb",
            "host": "localhost:27017",
            "db_name": "planly_db",
            "connected": True,
            "error": None
        }

        availability = {
            "Monday": 2.0,
            "Tuesday": 2.0,
            "Wednesday": 0.0,
            "Thursday": 2.0,
            "Friday": 2.0,
            "Saturday": 4.0,
            "Sunday": 3.0
        }
        sample_plan = generate_plan(availability, start_date_str="2026-10-19")
        mock_storage.get_plan.return_value = sample_plan
        mock_storage.save_plan.return_value = None

        res = self.client.post("/api/create-plan", json={
            "weekly_availability": availability,
            "start_date": "2026-10-19"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])

        # Test today endpoint with active plan
        res = self.client.get("/api/today?date=2026-10-19")
        self.assertEqual(res.status_code, 200)
        today_data = res.get_json()
        self.assertTrue(today_data["has_plan"])
        self.assertEqual(today_data["today_date"], "2026-10-19")

        # Test pause endpoint
        sample_plan["is_paused"] = True
        mock_storage.set_pause.return_value = sample_plan
        res = self.client.post("/api/pause")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.get_json()["is_paused"])

    def test_env_configuration_loaded(self):
        from src.config import MONGO_URI, MONGO_DB_NAME, FLASK_HOST, FLASK_PORT
        self.assertTrue(MONGO_URI.startswith("mongodb://"))
        self.assertEqual(MONGO_DB_NAME, "planly_db")
        self.assertEqual(FLASK_HOST, "0.0.0.0")
        self.assertEqual(FLASK_PORT, 5000)

    def test_estimate_plan_endpoint(self):
        # Valid estimation
        avail = {
            "Monday": 2.0,
            "Tuesday": 2.0,
            "Wednesday": 2.0,
            "Thursday": 2.0,
            "Friday": 2.0,
            "Saturday": 4.0,
            "Sunday": 4.0
        }
        res = self.client.post("/api/estimate-plan", json={
            "weekly_availability": avail,
            "start_date": "2026-10-19"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["start_date"], "2026-10-19")
        self.assertEqual(data["target_completion_date"], "2026-12-26")
        self.assertEqual(data["total_study_days"], 69)
        self.assertGreater(data["est_weeks"], 0)

        # Zero hours availability
        res_zero = self.client.post("/api/estimate-plan", json={
            "weekly_availability": {"Monday": 0.0, "Tuesday": 0.0},
            "start_date": "2026-10-19"
        })
        self.assertEqual(res_zero.status_code, 200)
        self.assertFalse(res_zero.get_json()["valid"])

        # Missing availability
        res_missing = self.client.post("/api/estimate-plan", json={})
        self.assertEqual(res_missing.status_code, 400)

    def test_storage_slug_backfill(self):
        from src.storage import PlanlyMongoStorage
        storage = PlanlyMongoStorage()
        if not storage.is_connected():
            self.skipTest("MongoDB not running")

        legacy_doc = {
            "id": "current_plan",
            "schedule": [
                {
                    "type": "study",
                    "day_number": 1,
                    "date": "2026-10-19",
                    "problems": [
                        {"uid": "p_1_401", "id": 401, "title": "Pattern 1"},
                        {
                            "uid": "p_1_17136",
                            "id": 17136,
                            "title": "Breaking The Myth",
                            "article_link": "https://takeuforward.org/blogs/sample",
                            "practice_link": "https://takeuforward.org/practice/dsa/breaking-the-myth"
                        }
                    ]
                }
            ]
        }
        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = legacy_doc
        storage.db = mock_db

        plan = storage.get_plan()
        probs = plan["schedule"][0]["problems"]
        # Pattern 1 (no article) -> has practice_link
        self.assertEqual(probs[0]["slug"], "pattern-1")
        self.assertEqual(probs[0]["practice_link"], "https://takeuforward.org/practice/dsa/pattern-1")
        # Breaking The Myth (has article) -> practice_link is None
        self.assertEqual(probs[1]["slug"], "breaking-the-myth")
        self.assertIsNone(probs[1]["practice_link"])
        mock_db.plans.update_one.assert_called_once()
        if storage.client:
            storage.client.close()

    @patch("src.app.storage")
    def test_reset_progress_endpoints(self, mock_storage):
        # Case 1: No plan found -> 404
        mock_storage.get_plan.return_value = None
        res_404 = self.client.post("/api/reset-progress", json={"restart_schedule": True})
        self.assertEqual(res_404.status_code, 404)
        self.assertIn("error", res_404.get_json())

        # Case 2: Active plan reset progress
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        plan["schedule"][0]["problems"][0]["completed"] = True
        mock_storage.get_plan.return_value = plan

        fresh_plan = generate_plan(availability, start_date_str="2026-11-03")
        mock_storage.reset_progress.return_value = fresh_plan

        res = self.client.post("/api/reset-progress", json={
            "restart_schedule": True,
            "start_date": "2026-11-03"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["metrics"]["completed_problems"], 0)
        self.assertEqual(data["metrics"]["completion_percent"], 0.0)
        mock_storage.reset_progress.assert_called_with(restart_schedule=True, start_date_str="2026-11-03")

    def test_storage_reset_progress_mocked(self):
        from src.storage import PlanlyMongoStorage
        storage = PlanlyMongoStorage()
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        plan["schedule"][0]["problems"][0]["completed"] = True
        plan["schedule"][0]["completed"] = True
        plan["is_paused"] = True

        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = plan
        storage.db = mock_db

        # Test retain schedule (restart_schedule=False)
        result_retain = storage.reset_progress(restart_schedule=False)
        self.assertFalse(result_retain["schedule"][0]["problems"][0]["completed"])
        self.assertFalse(result_retain["schedule"][0]["completed"])
        self.assertFalse(result_retain["is_paused"])
        self.assertEqual(result_retain["start_date"], "2026-10-19")
        mock_db.problem_progress.delete_many.assert_called()

        # Test reschedule (restart_schedule=True)
        result_restart = storage.reset_progress(restart_schedule=True, start_date_str="2026-11-03")
        self.assertEqual(result_restart["start_date"], "2026-11-03")
        self.assertFalse(result_restart["schedule"][0]["problems"][0]["completed"])
        self.assertFalse(result_restart["is_paused"])
        if storage.client:
            storage.client.close()

    def test_problem_revision_model_and_metrics(self):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        all_problems = [p for d in plan["schedule"] for p in d.get("problems", [])]
        self.assertEqual(len(all_problems), 495)

        for p in all_problems:
            self.assertIn("revision", p)
            self.assertFalse(p["revision"])
            self.assertIsNone(p.get("revision_marked_at"))

        initial_metrics = compute_metrics(plan)
        self.assertEqual(initial_metrics["revision_problems"], 0)

        # Mark 2 problems for revision
        plan["schedule"][0]["problems"][0]["revision"] = True
        plan["schedule"][0]["problems"][1]["revision"] = True
        updated_metrics = compute_metrics(plan)
        self.assertEqual(updated_metrics["revision_problems"], 2)

    @patch("src.app.storage")
    def test_problem_revision_api(self, mock_storage):
        # 1. When no plan exists -> 404
        mock_storage.get_plan.return_value = None
        res_404 = self.client.post("/api/problem/p_1_401/revision")
        self.assertEqual(res_404.status_code, 404)

        # 2. When plan exists -> toggle revision
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        target_uid = plan["schedule"][0]["problems"][0]["uid"]

        mock_storage.get_plan.return_value = plan

        # Simulate update_problem_revision_status
        def mock_update_rev(uid, rev, rev_at=None):
            for d in plan["schedule"]:
                for p in d.get("problems", []):
                    if p["uid"] == uid:
                        p["revision"] = bool(rev)
                        p["revision_marked_at"] = "2026-10-19T10:00:00" if rev else None
            return plan

        mock_storage.update_problem_revision_status.side_effect = mock_update_rev

        # Toggle to True
        res_toggle = self.client.post(f"/api/problem/{target_uid}/revision")
        self.assertEqual(res_toggle.status_code, 200)
        data = res_toggle.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["revision"])
        self.assertEqual(data["metrics"]["revision_problems"], 1)

        # Query /api/revisions
        res_list = self.client.get("/api/revisions")
        self.assertEqual(res_list.status_code, 200)
        list_data = res_list.get_json()
        self.assertTrue(list_data["success"])
        self.assertEqual(list_data["count"], 1)
        self.assertEqual(list_data["problems"][0]["uid"], target_uid)

        # Toggle explicitly to False
        res_unmark = self.client.post(f"/api/problem/{target_uid}/revision", json={"revision": False})
        self.assertEqual(res_unmark.status_code, 200)
        data_unmark = res_unmark.get_json()
        self.assertFalse(data_unmark["revision"])
        self.assertEqual(data_unmark["metrics"]["revision_problems"], 0)

    def test_storage_update_problem_revision_mocked(self):
        from src.storage import PlanlyMongoStorage
        storage = PlanlyMongoStorage()
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        target_uid = plan["schedule"][0]["problems"][0]["uid"]

        mock_db = MagicMock()
        mock_db.plans.find_one.return_value = plan
        storage.db = mock_db

        # Mark for revision
        res_plan = storage.update_problem_revision_status(target_uid, True)
        self.assertTrue(res_plan["schedule"][0]["problems"][0]["revision"])
        self.assertIsNotNone(res_plan["schedule"][0]["problems"][0]["revision_marked_at"])
        mock_db.problem_progress.update_one.assert_called_with(
            {"problem_uid": target_uid},
            {"$set": {"problem_uid": target_uid, "revision": True, "revision_marked_at": res_plan["schedule"][0]["problems"][0]["revision_marked_at"]}},
            upsert=True
        )

        # Mark completed should not overwrite revision
        storage.update_problem_status(target_uid, True)
        mock_db.problem_progress.update_one.assert_called_with(
            {"problem_uid": target_uid},
            {"$set": {"problem_uid": target_uid, "completed": True, "completed_at": res_plan["schedule"][0]["problems"][0]["completed_at"]}},
            upsert=True
        )

        if storage.client:
            storage.client.close()

    def test_realtime_ahead_of_schedule_recalculation(self):
        from src.planner import recalculate_future_schedule
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")

        study_days = [d for d in plan["schedule"] if d.get("type") == "study"]
        day3 = study_days[2]
        day7 = study_days[6]

        self.assertEqual(day3["day_number"], 3)
        self.assertEqual(day7["day_number"], 7)

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
        from src.planner import recalculate_future_schedule
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

    @patch("src.app.storage")
    def test_api_toggle_ahead_of_schedule(self, mock_storage):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 2.0, "Sunday": 2.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        mock_storage.get_plan.return_value = plan
        mock_storage.update_problem_status.return_value = (
            plan,
            {
                "recalculated": True,
                "moved_to_today": True,
                "old_target_date": "2026-12-25",
                "new_target_date": "2026-12-24"
            }
        )

        res = self.client.post("/api/problem/p_7_100/toggle", json={
            "completed": True,
            "date": "2026-10-21"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["recalculated"])
        self.assertTrue(data["moved_to_today"])
        self.assertEqual(data["old_target_completion_date"], "2026-12-25")
        self.assertEqual(data["new_target_completion_date"], "2026-12-24")

    def test_storage_realtime_ahead_of_schedule(self):
        from src.storage import PlanlyMongoStorage
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

if __name__ == "__main__":
    unittest.main()

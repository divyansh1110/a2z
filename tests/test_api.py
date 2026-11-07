import unittest
from unittest.mock import patch
from src.app import app
from src.planner import generate_plan


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

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
        self.assertIsNotNone(data["plan"])
        mock_storage.save_plan.assert_called_once()

        # Test GET /api/today
        res_today = self.client.get("/api/today?date=2026-10-19")
        self.assertEqual(res_today.status_code, 200)
        today_data = res_today.get_json()
        self.assertTrue(today_data["has_plan"])
        self.assertIsNotNone(today_data["active_day"])

        # Test POST /api/pause
        mock_storage.set_pause.return_value = sample_plan
        res_pause = self.client.post("/api/pause")
        self.assertEqual(res_pause.status_code, 200)
        self.assertTrue(res_pause.get_json()["is_paused"])

    def test_estimate_plan_endpoint(self):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 4.0
        }
        res = self.client.post("/api/estimate-plan", json={
            "weekly_availability": availability,
            "start_date": "2026-10-19"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["valid"])
        self.assertIsNotNone(data["target_completion_date"])
        self.assertGreater(data["est_weeks"], 0)

        # Invalid: 0 hours
        zero_avail = {d: 0.0 for d in availability}
        res_zero = self.client.post("/api/estimate-plan", json={"weekly_availability": zero_avail})
        self.assertEqual(res_zero.status_code, 200)
        self.assertFalse(res_zero.get_json()["valid"])

    @patch("src.app.storage")
    def test_pause_and_resume_plan(self, mock_storage):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        sample_plan = generate_plan(availability, start_date_str="2026-10-19")
        mock_storage.get_plan.return_value = sample_plan
        mock_storage.save_plan.return_value = None
        mock_storage.set_pause.return_value = dict(sample_plan, is_paused=True, paused_at="2026-10-25T12:00:00")

        # 1. Pause
        res_pause = self.client.post("/api/pause")
        self.assertEqual(res_pause.status_code, 200)
        self.assertTrue(res_pause.get_json()["is_paused"])

        # 2. Resume
        res_resume = self.client.post("/api/resume", json={"resume_date": "2026-11-01"})
        self.assertEqual(res_resume.status_code, 200)
        data = res_resume.get_json()
        self.assertTrue(data["success"])
        self.assertFalse(data["plan"]["is_paused"])

        # 3. Realign
        res_realign = self.client.post("/api/realign", json={"from_date": "2026-11-05"})
        self.assertEqual(res_realign.status_code, 200)
        self.assertTrue(res_realign.get_json()["success"])

    @patch("src.app.storage")
    def test_problem_revision_toggle_and_retrieval(self, mock_storage):
        availability = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(availability, start_date_str="2026-10-19")
        target_uid = plan["schedule"][0]["problems"][0]["uid"]

        # 1. Mark for revision
        plan_with_rev = dict(plan)
        plan_with_rev["schedule"][0]["problems"][0]["revision"] = True
        plan_with_rev["schedule"][0]["problems"][0]["revision_marked_at"] = "2026-10-19T10:00:00"
        mock_storage.get_plan.return_value = plan
        mock_storage.update_problem_revision_status.return_value = plan_with_rev

        res = self.client.post(f"/api/problem/{target_uid}/revision", json={"revision": True})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertTrue(data["revision"])
        mock_storage.update_problem_revision_status.assert_called_with(target_uid, True)

        # 2. Retrieve revisions
        mock_storage.get_plan.return_value = plan_with_rev
        res_list = self.client.get("/api/revisions")
        self.assertEqual(res_list.status_code, 200)
        rev_data = res_list.get_json()
        self.assertTrue(rev_data["success"])
        self.assertEqual(rev_data["count"], 1)
        self.assertEqual(rev_data["problems"][0]["uid"], target_uid)

        # 3. Unmark revision
        plan_without_rev = dict(plan)
        plan_without_rev["schedule"][0]["problems"][0]["revision"] = False
        mock_storage.update_problem_revision_status.return_value = plan_without_rev
        res_unmark = self.client.post(f"/api/problem/{target_uid}/revision", json={"revision": False})
        self.assertEqual(res_unmark.status_code, 200)
        self.assertFalse(res_unmark.get_json()["revision"])

    @patch("src.app.storage")
    def test_update_plan_endpoint(self, mock_storage):
        mock_storage.get_engine_info.return_value = {"connected": True}
        initial_avail = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 2.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 4.0
        }
        plan = generate_plan(initial_avail, start_date_str="2026-10-19")
        mock_storage.get_plan.return_value = plan

        new_avail = {
            "Monday": 2.5, "Tuesday": 2.5, "Wednesday": 2.5,
            "Thursday": 2.5, "Friday": 2.5, "Saturday": 0.0, "Sunday": 0.0
        }
        updated_mock_plan = dict(plan, weekly_availability=new_avail)
        mock_storage.update_plan_availability.return_value = updated_mock_plan

        res = self.client.post("/api/update-plan", json={
            "weekly_availability": new_avail,
            "from_date": "2026-10-21"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertIn("metrics", data)
        mock_storage.update_plan_availability.assert_called_with(new_avail, from_date_str="2026-10-21", pace_multiplier=None)

    @patch("src.app.storage")
    def test_reset_progress_endpoint(self, mock_storage):
        initial_avail = {
            "Monday": 2.0, "Tuesday": 2.0, "Wednesday": 0.0,
            "Thursday": 2.0, "Friday": 2.0, "Saturday": 4.0, "Sunday": 3.0
        }
        plan = generate_plan(initial_avail, start_date_str="2026-10-19")
        mock_storage.get_plan.return_value = plan

        clean_plan = generate_plan(initial_avail, start_date_str="2026-11-03")
        mock_storage.reset_progress.return_value = clean_plan

        res = self.client.post("/api/reset-progress", json={
            "restart_schedule": True,
            "start_date": "2026-11-03"
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data["success"])
        self.assertEqual(data["plan"]["start_date"], "2026-11-03")
        mock_storage.reset_progress.assert_called_with(restart_schedule=True, start_date_str="2026-11-03")

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


if __name__ == "__main__":
    unittest.main()

import os
import json
from datetime import datetime
import re
import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from src.logger import logger
from src.config import MONGO_URI, MONGO_DB_NAME

class PlanlyMongoStorage:
    """
    Dedicated MongoDB storage manager for Planly.
    Connects using configuration from .env.
    """
    def __init__(self, mongo_uri=None, db_name=None):
        self.mongo_uri = mongo_uri or MONGO_URI
        self.db_name = db_name or MONGO_DB_NAME
        self.client = None
        self.db = None
        self._init_connection()

    def _get_display_uri(self):
        # Mask credentials in URI if present
        return re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', self.mongo_uri)

    def _init_connection(self):
        display_uri = self._get_display_uri()
        try:
            logger.info(f"Connecting to MongoDB at {display_uri} (Database: {self.db_name})...")
            self.client = pymongo.MongoClient(self.mongo_uri, serverSelectionTimeoutMS=2000)
            # Verify server availability
            self.client.admin.command('ping')
            self.db = self.client[self.db_name]
            # Ensure indexes
            self.db.plans.create_index("id", unique=True)
            self.db.problem_progress.create_index("problem_uid", unique=True)
            logger.info(f"Successfully connected to MongoDB at {display_uri}.")
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error(f"Failed to connect to MongoDB on {display_uri}: {e}")
            self.client = None
            self.db = None
        except Exception as e:
            logger.exception(f"Unexpected error initializing MongoDB connection: {e}")
            self.client = None
            self.db = None

    def _ensure_connected(self):
        if self.db is None:
            self._init_connection()
        if self.db is None:
            display_uri = self._get_display_uri()
            raise ConnectionError(
                f"MongoDB is not running or unreachable at {display_uri}. "
                "Please ensure the MongoDB service (mongod) is active."
            )

    def is_connected(self):
        try:
            if self.client is None:
                self._init_connection()
            if self.client is not None:
                self.client.admin.command('ping')
                return True
        except Exception:
            pass
        return False

    def get_engine_info(self):
        connected = self.is_connected()
        display_uri = self._get_display_uri()
        return {
            "backend": "mongodb",
            "uri": display_uri,
            "host": display_uri,
            "db_name": self.db_name,
            "connected": connected,
            "error": None if connected else f"MongoDB is not reachable at {display_uri}. Please ensure mongod is running."
        }

    def save_plan(self, plan_data):
        self._ensure_connected()
        now_str = datetime.now().isoformat()
        plan_data["updated_at"] = now_str
        plan_id = "current_plan"

        doc = dict(plan_data)
        doc["id"] = plan_id

        try:
            self.db.plans.replace_one({"id": plan_id}, doc, upsert=True)
            logger.info(f"Plan saved to MongoDB. Target completion: {plan_data.get('target_completion_date')}")
        except Exception as e:
            logger.error(f"Error saving plan to MongoDB: {e}")
            raise

    _slug_cache = None

    def _get_problem_slug_map(self):
        if PlanlyMongoStorage._slug_cache is not None:
            return PlanlyMongoStorage._slug_cache
        slug_map = {}
        syllabus_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "data",
            "full_dsa_sheet_syllabus.json"
        )
        if os.path.exists(syllabus_path):
            try:
                with open(syllabus_path, "r", encoding="utf-8") as f:
                    syllabus = json.load(f)
                for topic in syllabus:
                    for sub in topic.get("subtopics", []):
                        for p in sub.get("problems", []):
                            if p.get("id") and p.get("slug"):
                                slug_map[p["id"]] = p["slug"]
            except Exception as e:
                logger.warning(f"Could not load syllabus for slug mapping: {e}")
        PlanlyMongoStorage._slug_cache = slug_map
        return slug_map

    def get_plan(self):
        if not self.is_connected():
            return None

        try:
            doc = self.db.plans.find_one({"id": "current_plan"}, {"_id": 0})
            if doc and "schedule" in doc:
                needs_update = False
                slug_map = None

                for idx, day in enumerate(doc["schedule"]):
                    expected_week = (idx // 7) + 1
                    if day.get("week_number") != expected_week:
                        day["week_number"] = expected_week
                        needs_update = True

                    for prob in day.get("problems", []):
                        if not prob.get("slug"):
                            if slug_map is None:
                                slug_map = self._get_problem_slug_map()
                            prob_slug = slug_map.get(prob.get("id"), "")
                            if prob_slug:
                                prob["slug"] = prob_slug
                                needs_update = True

                        if "revision" not in prob:
                            prob["revision"] = False
                            prob["revision_marked_at"] = None

                        if prob.get("article_link"):
                            if prob.get("practice_link") is not None:
                                prob["practice_link"] = None
                                needs_update = True
                        else:
                            expected_practice = f"https://takeuforward.org/practice/dsa/{prob['slug']}" if prob.get("slug") else None
                            if prob.get("practice_link") != expected_practice:
                                prob["practice_link"] = expected_practice
                                needs_update = True

                if not doc.get("total_weeks"):
                    doc["total_weeks"] = (len(doc["schedule"]) + 6) // 7 if doc["schedule"] else 0
                    needs_update = True
                if needs_update:
                    try:
                        self.db.plans.update_one(
                            {"id": "current_plan"},
                            {"$set": {"schedule": doc["schedule"], "total_weeks": doc["total_weeks"]}}
                        )
                    except Exception as e:
                        logger.warning(f"Failed to auto-update week numbers / problem slugs in MongoDB: {e}")
            return doc
        except Exception as e:
            logger.error(f"Error reading plan from MongoDB: {e}")
            return None

    def update_problem_status(self, problem_uid, completed, completed_at=None, current_date_str=None, return_meta=False):
        self._ensure_connected()

        if completed and not completed_at:
            completed_at = datetime.now().isoformat()
        elif not completed:
            completed_at = None

        # 1. Update problem_progress collection
        try:
            self.db.problem_progress.update_one(
                {"problem_uid": problem_uid},
                {"$set": {"problem_uid": problem_uid, "completed": bool(completed), "completed_at": completed_at}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating problem_progress collection: {e}")

        # 2. Update embedded plan document
        plan = self.get_plan()
        if not plan:
            recalc_meta = {
                "recalculated": False,
                "moved_to_today": False,
                "old_target_date": None,
                "new_target_date": None
            }
            return (None, recalc_meta) if return_meta else None

        schedule = plan.get("schedule", [])
        old_target_date = plan.get("target_completion_date")

        # If completed == False (unchecking):
        # Rule: Keep problem in-place without triggering schedule recalculation
        if not completed:
            found = False
            for day in schedule:
                if day.get("type") != "study":
                    continue
                for prob in day.get("problems", []):
                    if prob.get("uid") == problem_uid:
                        prob["completed"] = False
                        prob["completed_at"] = None
                        found = True
                        break
                if found:
                    day["completed"] = all(p.get("completed", False) for p in day.get("problems", []))
                    break

            if found:
                self.save_plan(plan)
                logger.info(f"Problem {problem_uid} marked incomplete in-place")

            recalc_meta = {
                "recalculated": False,
                "moved_to_today": False,
                "old_target_date": old_target_date,
                "new_target_date": plan.get("target_completion_date")
            }
            return (plan, recalc_meta) if return_meta else plan

        # If completed == True:
        # Check if the problem belongs to a future day and needs dynamic recalculation
        from src.planner import recalculate_future_schedule
        updated_plan, was_recalc, was_moved, old_t, new_t = recalculate_future_schedule(
            plan, today_date_str=current_date_str, problem_completed_uid=problem_uid
        )

        if was_recalc and was_moved:
            self.save_plan(updated_plan)
            logger.info(
                f"Problem {problem_uid} completed ahead of schedule -> Moved to Today & recalculated schedule. "
                f"Target date changed: {old_t} -> {new_t}"
            )
            recalc_meta = {
                "recalculated": True,
                "moved_to_today": True,
                "old_target_date": old_t,
                "new_target_date": new_t
            }
            return (updated_plan, recalc_meta) if return_meta else updated_plan

        # If not a future day (e.g. today or past backlog day): update in-place
        found = False
        for day in schedule:
            if day.get("type") != "study":
                continue
            for prob in day.get("problems", []):
                if prob.get("uid") == problem_uid:
                    prob["completed"] = True
                    prob["completed_at"] = completed_at
                    found = True
                    break
            if found:
                day["completed"] = all(p.get("completed", False) for p in day.get("problems", []))
                break

        if found:
            self.save_plan(plan)
            logger.info(f"Problem {problem_uid} updated -> completed=True")

        recalc_meta = {
            "recalculated": False,
            "moved_to_today": False,
            "old_target_date": old_target_date,
            "new_target_date": plan.get("target_completion_date")
        }
        return (plan, recalc_meta) if return_meta else plan

    def update_problem_revision_status(self, problem_uid, revision, revision_marked_at=None):
        self._ensure_connected()

        if revision and not revision_marked_at:
            revision_marked_at = datetime.now().isoformat()
        elif not revision:
            revision_marked_at = None

        # 1. Update problem_progress collection in Mongo
        try:
            self.db.problem_progress.update_one(
                {"problem_uid": problem_uid},
                {"$set": {"problem_uid": problem_uid, "revision": bool(revision), "revision_marked_at": revision_marked_at}},
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error updating problem revision in problem_progress collection: {e}")

        # 2. Update embedded plan document
        plan = self.get_plan()
        if not plan:
            return None

        found = False
        for day in plan.get("schedule", []):
            if day.get("type") != "study":
                continue
            for prob in day.get("problems", []):
                if prob.get("uid") == problem_uid:
                    prob["revision"] = bool(revision)
                    prob["revision_marked_at"] = revision_marked_at
                    found = True
                    break
            if found:
                break

        if found:
            self.save_plan(plan)
            logger.info(f"Problem {problem_uid} updated -> revision={revision}")

        return plan

    def update_day_status(self, day_number, completed):
        self._ensure_connected()
        plan = self.get_plan()
        if not plan:
            return None

        now_str = datetime.now().isoformat() if completed else None
        target_day = None

        for day in plan.get("schedule", []):
            if day.get("type") == "study" and day.get("day_number") == day_number:
                target_day = day
                day["completed"] = bool(completed)
                for prob in day.get("problems", []):
                    prob["completed"] = bool(completed)
                    prob["completed_at"] = now_str
                    try:
                        self.db.problem_progress.update_one(
                            {"problem_uid": prob["uid"]},
                            {"$set": {"problem_uid": prob["uid"], "completed": bool(completed), "completed_at": now_str}},
                            upsert=True
                        )
                    except Exception as e:
                        logger.error(f"Error updating progress in mongo for {prob.get('uid')}: {e}")
                break

        if target_day:
            self.save_plan(plan)
            logger.info(f"Study Day {day_number} updated -> completed={completed}")

        return plan

    def set_pause(self, is_paused, paused_at=None):
        self._ensure_connected()
        plan = self.get_plan()
        if not plan:
            return None

        plan["is_paused"] = bool(is_paused)
        if is_paused:
            plan["paused_at"] = paused_at or datetime.now().isoformat()
            logger.info(f"Study plan paused at {plan['paused_at']}")
        else:
            plan["paused_at"] = None
            logger.info("Study plan resumed from pause")

        self.save_plan(plan)
        return plan

    def reset_plan(self):
        self._ensure_connected()
        try:
            self.db.plans.delete_many({"id": "current_plan"})
            self.db.problem_progress.delete_many({})
            logger.info("Active plan and progress data reset in MongoDB.")
            return True
        except Exception as e:
            logger.error(f"Error resetting plan in MongoDB: {e}")
            raise

    def reset_progress(self, restart_schedule=True, start_date_str=None):
        self._ensure_connected()
        plan = self.get_plan()
        if not plan:
            return None

        # 1. Clear individual problem progress from MongoDB collection
        try:
            self.db.problem_progress.delete_many({})
            logger.info("Cleared problem_progress collection in MongoDB.")
        except Exception as e:
            logger.error(f"Error clearing problem_progress in MongoDB: {e}")

        # 2. Reset plan schedule & problems
        if restart_schedule:
            from src.planner import generate_plan
            target_start = start_date_str or datetime.now().date().isoformat()
            weekly_avail = plan.get("weekly_availability", {})
            pace_multiplier = plan.get("pace_multiplier", 1.0)
            new_plan = generate_plan(weekly_avail, start_date_str=target_start, pace_multiplier=pace_multiplier)
            self.save_plan(new_plan)
            logger.info(f"Progress reset to 0 with rescheduled plan starting {target_start}")
            return new_plan
        else:
            # Retain existing calendar schedule dates, but reset all problem and day completion statuses
            for day in plan.get("schedule", []):
                day["completed"] = False
                for prob in day.get("problems", []):
                    prob["completed"] = False
                    prob["completed_at"] = None
            plan["is_paused"] = False
            plan["paused_at"] = None
            self.save_plan(plan)
            logger.info("Progress reset to 0 retaining original calendar schedule dates.")
            return plan

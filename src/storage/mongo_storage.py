from src.storage.connection import MongoConnectionManager, mask_mongo_uri
from src.storage.slugs import get_problem_slug_map
from src.storage.plan_ops import save_plan_doc, get_plan_doc, reset_plan_doc
from src.storage.progress_ops import (
    get_problem_progress_map as fetch_progress_map,
    update_problem_status as update_prob_status,
    update_problem_revision_status as update_prob_revision,
    update_day_status as update_d_status,
    set_pause as set_plan_pause,
    reset_progress as reset_plan_progress,
)
from src.storage.availability_ops import update_plan_availability as update_avail


class PlanlyMongoStorage:
    """
    Dedicated MongoDB storage manager for Planly.
    Connects using configuration from .env.
    """

    _slug_cache = None

    def __init__(self, mongo_uri=None, db_name=None):
        self._manager = MongoConnectionManager(mongo_uri=mongo_uri, db_name=db_name)
        self.mongo_uri = self._manager.mongo_uri
        self.db_name = self._manager.db_name
        self.client = self._manager.client
        self.db = self._manager.db

    def _sync_connection_state(self):
        """Keep self.client and self.db synchronized with connection manager."""
        if self._manager.client is not self.client and self.client is not None:
            self._manager.client = self.client
        if self._manager.db is not self.db and self.db is not None:
            self._manager.db = self.db

    def _get_display_uri(self):
        return mask_mongo_uri(self.mongo_uri)

    def _init_connection(self):
        self._manager.init_connection()
        self.client = self._manager.client
        self.db = self._manager.db

    def _ensure_connected(self):
        if self.db is not None:
            return
        self._init_connection()
        if self.db is None:
            display_uri = self._get_display_uri()
            raise ConnectionError(
                f"MongoDB is not running or unreachable at {display_uri}. "
                "Please ensure the MongoDB service (mongod) is active."
            )

    def is_connected(self):
        try:
            if self.client is not None:
                self.client.admin.command('ping')
                return True
            return self._manager.is_connected()
        except Exception:
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

    def _get_problem_slug_map(self):
        return get_problem_slug_map()

    def get_problem_progress_map(self):
        """Retrieve all recorded problem progress and revision statuses from MongoDB."""
        if not self.is_connected() or self.db is None:
            return {}
        return fetch_progress_map(self.db)

    def save_plan(self, plan_data):
        self._ensure_connected()
        save_plan_doc(self.db, plan_data)

    def get_plan(self):
        if not self.is_connected() or self.db is None:
            return None
        progress_map = self.get_problem_progress_map()
        slug_map = self._get_problem_slug_map()
        return get_plan_doc(self.db, progress_map, slug_map)

    def reset_plan(self):
        self._ensure_connected()
        return reset_plan_doc(self.db)

    def update_problem_status(self, problem_uid, completed, completed_at=None, current_date_str=None, return_meta=False):
        return update_prob_status(
            self,
            problem_uid,
            completed,
            completed_at=completed_at,
            current_date_str=current_date_str,
            return_meta=return_meta
        )

    def update_problem_revision_status(self, problem_uid, revision, revision_marked_at=None):
        return update_prob_revision(self, problem_uid, revision, revision_marked_at=revision_marked_at)

    def update_day_status(self, day_number, completed):
        return update_d_status(self, day_number, completed)

    def set_pause(self, is_paused, paused_at=None):
        return set_plan_pause(self, is_paused, paused_at=paused_at)

    def reset_progress(self, restart_schedule=True, start_date_str=None):
        return reset_plan_progress(self, restart_schedule=restart_schedule, start_date_str=start_date_str)

    def update_plan_availability(self, weekly_availability, from_date_str=None, pace_multiplier=None):
        return update_avail(
            self,
            weekly_availability,
            from_date_str=from_date_str,
            pace_multiplier=pace_multiplier
        )

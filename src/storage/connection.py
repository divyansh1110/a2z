import re
import pymongo
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError
from src.logger import logger
from src.config import MONGO_URI, MONGO_DB_NAME


def mask_mongo_uri(uri):
    """Mask credentials in MongoDB URI if present."""
    return re.sub(r'://([^:]+):([^@]+)@', r'://\1:****@', uri)


class MongoConnectionManager:
    """Manages connection lifecycle and verification to MongoDB."""

    def __init__(self, mongo_uri=None, db_name=None):
        self.mongo_uri = mongo_uri or MONGO_URI
        self.db_name = db_name or MONGO_DB_NAME
        self.client = None
        self.db = None
        self.init_connection()

    def get_display_uri(self):
        return mask_mongo_uri(self.mongo_uri)

    def init_connection(self):
        display_uri = self.get_display_uri()
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

    def is_connected(self):
        try:
            if self.client is None:
                self.init_connection()
            if self.client is not None:
                self.client.admin.command('ping')
                return True
        except Exception:
            pass
        return False

    def ensure_connected(self):
        if self.db is None:
            self.init_connection()
        if self.db is None:
            display_uri = self.get_display_uri()
            raise ConnectionError(
                f"MongoDB is not running or unreachable at {display_uri}. "
                "Please ensure the MongoDB service (mongod) is active."
            )

    def get_engine_info(self):
        connected = self.is_connected()
        display_uri = self.get_display_uri()
        return {
            "backend": "mongodb",
            "uri": display_uri,
            "host": display_uri,
            "db_name": self.db_name,
            "connected": connected,
            "error": None if connected else f"MongoDB is not reachable at {display_uri}. Please ensure mongod is running."
        }

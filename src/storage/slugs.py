import os
import json
from src.logger import logger

_SLUG_CACHE = None


def get_problem_slug_map():
    """Retrieve problem ID -> slug map from syllabus JSON with caching."""
    global _SLUG_CACHE
    if _SLUG_CACHE is not None:
        return _SLUG_CACHE

    slug_map = {}
    syllabus_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
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

    _SLUG_CACHE = slug_map
    return slug_map


def clear_slug_cache():
    global _SLUG_CACHE
    _SLUG_CACHE = None

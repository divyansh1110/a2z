from flask import Blueprint, jsonify
from src.logger import logger
from src.planner.syllabus import load_flattened_syllabus

syllabus_bp = Blueprint("syllabus", __name__)

_CACHED_SYLLABUS = None


def get_cached_syllabus():
    global _CACHED_SYLLABUS
    if _CACHED_SYLLABUS is None:
        flat_problems, topics_summary = load_flattened_syllabus()
        _CACHED_SYLLABUS = (flat_problems, topics_summary)
    return _CACHED_SYLLABUS


@syllabus_bp.route("/api/syllabus", methods=["GET"])
def get_syllabus():
    try:
        flat_problems, topics_summary = get_cached_syllabus()
        return jsonify({
            "success": True,
            "topics_summary": topics_summary,
            "problems": flat_problems,
            "total_problems": len(flat_problems)
        })
    except Exception as e:
        logger.exception(f"Error fetching syllabus: {e}")
        return jsonify({"error": str(e)}), 500

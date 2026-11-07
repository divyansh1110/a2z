import os
import json
import re
from src.logger import logger

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_SYLLABUS_PATH = os.path.join(PROJECT_ROOT, "data", "full_dsa_sheet_syllabus.json")


def parse_duration_to_minutes(dur_str, difficulty):
    """Parse duration string or return an estimate based on difficulty."""
    if dur_str:
        m = re.search(r'(\d+)\s*min', str(dur_str).lower())
        if m:
            return int(m.group(1))
    diff = (difficulty or '').lower()
    if diff == 'basic':
        return 30
    elif diff == 'core':
        return 45
    elif diff == 'pro':
        return 60
    return 35


def load_flattened_syllabus(filepath=DEFAULT_SYLLABUS_PATH):
    """Load and flatten all problems from the syllabus JSON."""
    if not os.path.exists(filepath):
        logger.error(f"Syllabus file not found at {filepath}")
        raise FileNotFoundError(f"Syllabus file not found at: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        syllabus = json.load(f)

    flat_problems = []
    topics_summary = []
    idx = 0

    for topic_order, topic in enumerate(syllabus, 1):
        topic_name = topic.get("topic", "").strip()
        topic_slug = topic.get("slug", "")
        topic_problems_count = 0
        subtopics_summary = []

        for sub_order, sub in enumerate(topic.get("subtopics", []), 1):
            sub_name = sub.get("subtopic", "").strip()
            sub_slug = sub.get("slug", "")
            sub_probs = sub.get("problems", [])
            topic_problems_count += len(sub_probs)

            subtopics_summary.append({
                "id": sub.get("id"),
                "subtopic": sub_name,
                "slug": sub_slug,
                "problem_count": len(sub_probs)
            })

            for p in sub_probs:
                idx += 1
                est_mins = parse_duration_to_minutes(p.get("duration"), p.get("difficulty"))
                uid = f"p_{idx}_{p.get('id')}"

                tag = p.get("tag")
                if not tag:
                    diff = p.get("difficulty")
                    tag = diff.capitalize() if diff else "Basic"

                prob_slug = p.get("slug", "")
                article_link = p.get("article_link")
                practice_link = (
                    f"https://takeuforward.org/practice/dsa/{prob_slug}"
                    if prob_slug and not article_link
                    else None
                )

                flat_problems.append({
                    "uid": uid,
                    "id": p.get("id"),
                    "title": p.get("title", "").strip(),
                    "slug": prob_slug,
                    "practice_link": practice_link,
                    "topic_order": topic_order,
                    "topic": topic_name,
                    "topic_slug": topic_slug,
                    "subtopic_order": sub_order,
                    "subtopic": sub_name,
                    "subtopic_slug": sub_slug,
                    "difficulty": (p.get("difficulty") or "basic").lower(),
                    "tag": tag,
                    "duration": p.get("duration"),
                    "est_minutes": est_mins,
                    "leetcode_link": p.get("leetcode_link"),
                    "youtube_link": p.get("youtube_link"),
                    "article_link": p.get("article_link"),
                    "completed": False,
                    "completed_at": None,
                    "revision": False,
                    "revision_marked_at": None
                })

        topics_summary.append({
            "order": topic_order,
            "id": topic.get("id"),
            "topic": topic_name,
            "slug": topic_slug,
            "subtopics": subtopics_summary,
            "total_problems": topic_problems_count
        })

    logger.info(f"Loaded syllabus: {len(topics_summary)} topics, {len(flat_problems)} total problems.")
    return flat_problems, topics_summary

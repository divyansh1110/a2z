import urllib.request
import re
import json
import os

def extract_all():
    url = "https://takeuforward.org/prep-hub/strivers-a2z-dsa-sheet?page=sheet"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    )
    html = urllib.request.urlopen(req).read().decode("utf-8")

    # Locate the embedded flight payload containing sheet_syllabus
    scripts = re.findall(r'<script>(self\.__next_f\.push\(.*?\))</script>', html, re.DOTALL)
    syllabus_obj = None

    for s in scripts:
        m = re.match(r'self\.__next_f\.push\(\[\d+,\s*"(.*)"\]\)', s, re.DOTALL)
        if m and "sheet_syllabus" in m.group(1):
            decoded = json.loads(f'"{m.group(1)}"')
            idx = decoded.find('"sheet_syllabus":')
            if idx != -1:
                sub = decoded[idx + len('"sheet_syllabus":'):]
                syllabus_obj, _ = json.JSONDecoder().raw_decode(sub)
                break

    if not syllabus_obj:
        raise ValueError("Could not find sheet_syllabus payload in page")

    fields = syllabus_obj["fields"]
    rows = syllabus_obj["rows"]
    roots = syllabus_obj["roots"]

    def get_row(idx):
        row_data = rows[idx]
        schema_idx = row_data[0]
        schema = fields[schema_idx]
        values = row_data[1:]
        return dict(zip(schema, values))

    full_tree = []

    for r_idx in roots:
        root_rec = get_row(r_idx)
        topic_name = root_rec["label"].strip()

        topic_full = {
            "id": root_rec["id"],
            "topic": topic_name,
            "slug": root_rec.get("slug"),
            "subtopics": []
        }

        for c_idx in root_rec.get("children", []):
            sub_rec = get_row(c_idx)
            sub_name = sub_rec.get("label", "").strip()

            sub_full = {
                "id": sub_rec.get("id"),
                "subtopic": sub_name,
                "slug": sub_rec.get("slug"),
                "type": sub_rec.get("type"),
                "total_problems": len(sub_rec.get("children", [])),
                "problems": []
            }

            for item_idx in sub_rec.get("children", []):
                item_rec = get_row(item_idx)
                raw_diff = item_rec.get("difficulty")
                tag = raw_diff.capitalize() if raw_diff else None

                item_dict = {
                    "id": item_rec.get("id"),
                    "title": item_rec.get("label", "").strip(),
                    "slug": item_rec.get("slug"),
                    "tag": tag,
                    "difficulty": raw_diff,
                    "duration": item_rec.get("duration"),
                    "leetcode_link": item_rec.get("leetcode_link"),
                    "youtube_link": item_rec.get("yt_video"),
                    "article_link": f"https://takeuforward.org{item_rec['free_blog_link']}" if item_rec.get('free_blog_link') else None
                }
                sub_full["problems"].append({k: v for k, v in item_dict.items() if v is not None})

            topic_full["subtopics"].append(sub_full)

        full_tree.append(topic_full)

    os.makedirs("data", exist_ok=True)
    target_path = os.path.join("data", "full_dsa_sheet_syllabus.json")
    with open(target_path, "w", encoding="utf-8") as f:
        json.dump(full_tree, f, indent=2, ensure_ascii=False)

    print(f"Successfully exported {len(full_tree)} topics to {target_path}")

if __name__ == "__main__":
    extract_all()

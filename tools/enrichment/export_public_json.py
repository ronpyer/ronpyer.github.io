import argparse
import json
from pathlib import Path

from db import apply_schema, connect_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export public enrichment JSON from SQLite.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--descriptions-output", type=Path, required=True)
    parser.add_argument("--faces-output", type=Path, required=True)
    parser.add_argument("--people-output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    conn = connect_db(args.db)
    apply_schema(conn)

    description_rows = conn.execute(
        """
        SELECT d.photo_id, d.description, d.search_text, d.model_name, p.display_src
        FROM photo_descriptions d
        JOIN photos p ON p.id = d.photo_id
        WHERE d.is_active = 1
        ORDER BY d.photo_id
        """
    ).fetchall()
    tags_by_photo = {}
    for row in conn.execute(
        """
        SELECT pt.photo_id, t.name, t.tag_type, pt.confidence
        FROM photo_tags pt
        JOIN tags t ON t.id = pt.tag_id
        WHERE pt.is_active = 1
        ORDER BY pt.photo_id, t.name
        """
    ):
        by_name = tags_by_photo.setdefault(row["photo_id"], {})
        key = row["name"].strip().lower()
        confidence = None if row["confidence"] is None else round(float(row["confidence"]), 4)
        current = by_name.get(key)
        if current is None or (
            confidence is not None and (current["confidence"] is None or confidence > current["confidence"])
        ):
            by_name[key] = {
                "tag": row["name"],
                "type": row["tag_type"],
                "confidence": confidence,
            }

    descriptions_payload = {
        "schema_version": 1,
        "item_count": len(description_rows),
        "items": [
            {
                "id": row["photo_id"],
                "description": row["description"],
                "search_text": row["search_text"],
                "source_image": row["display_src"],
                "tags": sorted(
                    tags_by_photo.get(row["photo_id"], {}).values(),
                    key=lambda tag: (tag["type"], tag["tag"].lower()),
                ),
                "model_name": row["model_name"],
            }
            for row in description_rows
        ],
    }

    face_rows = conn.execute(
        """
        SELECT
          fd.id AS face_detection_id,
          fd.photo_id,
          fd.face_index,
          fd.embedding_key,
          fd.x1, fd.y1, fd.x2, fd.y2,
          fd.confidence,
          pg.group_key,
          p.display_src
        FROM face_detections fd
        JOIN photos p ON p.id = fd.photo_id
        LEFT JOIN face_group_memberships fgm ON fgm.face_detection_id = fd.id
        LEFT JOIN people_groups pg ON pg.id = fgm.people_group_id AND pg.is_active = 1
        WHERE fd.is_active = 1
        ORDER BY fd.photo_id, fd.face_index
        """
    ).fetchall()
    faces_by_photo = {}
    for row in face_rows:
        faces_by_photo.setdefault(row["photo_id"], {"id": row["photo_id"], "source_image": row["display_src"], "faces": []})
        faces_by_photo[row["photo_id"]]["faces"].append(
            {
                "face_index": row["face_index"],
                "embedding_id": row["embedding_key"],
                "box": [row["x1"], row["y1"], row["x2"], row["y2"]],
                "confidence": None if row["confidence"] is None else round(float(row["confidence"]), 4),
                "person_group_id": row["group_key"],
            }
        )

    faces_payload = {
        "schema_version": 1,
        "item_count": len(faces_by_photo),
        "items": list(faces_by_photo.values()),
    }

    people_rows = conn.execute(
        """
        SELECT id, group_key, label
        FROM people_groups
        WHERE is_active = 1
        ORDER BY group_key
        """
    ).fetchall()
    groups = []
    for group in people_rows:
        sample_rows = conn.execute(
            """
            SELECT fd.photo_id, fd.face_index, fd.embedding_key
            FROM face_group_memberships fgm
            JOIN face_detections fd ON fd.id = fgm.face_detection_id
            WHERE fgm.people_group_id = ?
            ORDER BY fd.photo_id, fd.face_index
            LIMIT 6
            """,
            (group["id"],),
        ).fetchall()
        photo_ids = [
            row["photo_id"]
            for row in conn.execute(
                """
                SELECT DISTINCT fd.photo_id
                FROM face_group_memberships fgm
                JOIN face_detections fd ON fd.id = fgm.face_detection_id
                WHERE fgm.people_group_id = ?
                ORDER BY fd.photo_id
                """,
                (group["id"],),
            ).fetchall()
        ]
        face_count = conn.execute(
            "SELECT COUNT(*) FROM face_group_memberships WHERE people_group_id = ?",
            (group["id"],),
        ).fetchone()[0]
        groups.append(
            {
                "group_id": group["group_key"],
                "label": group["label"],
                "face_count": face_count,
                "photo_ids": photo_ids,
                "sample_faces": [
                    {
                        "photo_id": row["photo_id"],
                        "face_index": row["face_index"],
                        "embedding_id": row["embedding_key"],
                    }
                    for row in sample_rows
                ],
            }
        )

    people_payload = {
        "schema_version": 1,
        "group_count": len(groups),
        "groups": groups,
    }

    for output_path, payload in (
        (args.descriptions_output, descriptions_payload),
        (args.faces_output, faces_payload),
        (args.people_output, people_payload),
    ):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2))
        print(f"Wrote {output_path}")

    conn.close()


if __name__ == "__main__":
    main()

import argparse
import re
import sys
from pathlib import Path

from PIL import Image
from transformers import pipeline

sys.path.append(str(Path(__file__).resolve().parents[1]))
from db import apply_schema, connect_db, create_run, normalize_tag  # noqa: E402


DEFAULT_LABELS = [
    "portrait",
    "group photo",
    "child",
    "adult",
    "family",
    "indoor scene",
    "outdoor scene",
    "house",
    "car",
    "boat",
    "dog",
    "cat",
    "flowers",
    "holiday gathering",
    "wedding",
    "party",
    "beach",
    "snow",
    "street scene",
    "nature",
]

STOPWORDS = {
    "a",
    "an",
    "and",
    "at",
    "for",
    "from",
    "in",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate plaintext photo descriptions and search tags."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--model", default="Salesforce/blip-image-captioning-base")
    parser.add_argument("--classifier-model", default="openai/clip-vit-base-patch32")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--min-score", type=float, default=0.2)
    return parser.parse_args()


def resolve_image_path(image_root: Path, item: dict) -> Path:
    display_src = item.get("display_src")
    if not display_src:
        raise ValueError(f"Missing display src for {item.get('id')}")
    return image_root / display_src.lstrip("/")


def infer_orientation(item: dict) -> str:
    width = item.get("width", 0)
    height = item.get("height", 0)
    if width > height:
        return "landscape"
    if height > width:
        return "portrait-orientation"
    return "square"


def normalize_caption(raw_caption: str) -> str:
    caption = raw_caption.strip()
    caption = re.sub(r"\s+", " ", caption)
    if not caption:
        return "Photo from the Ronald Lee Pyer archive."
    caption = caption[0].upper() + caption[1:]
    if caption[-1] not in ".!?":
        caption += "."
    return caption


def derive_keyword_tags(caption: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", caption.lower())
    return sorted(
        {
            word
            for word in words
            if len(word) >= 4 and word not in STOPWORDS
        }
    )


def build_search_text(description: str, tags: list[str], labels: list[str], item: dict) -> str:
    chunks = [
        description,
        " ".join(tags),
        " ".join(labels),
        item.get("folder", ""),
        item.get("filename", ""),
    ]
    return " ".join(chunk for chunk in chunks if chunk).strip()


def main() -> None:
    args = parse_args()
    conn = connect_db(args.db)
    apply_schema(conn)
    limit_clause = "" if args.limit is None else f" LIMIT {int(args.limit)}"
    items = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT id, filename, folder, width, height, display_src
            FROM photos
            ORDER BY id{limit_clause}
            """
        ).fetchall()
    ]

    captioner = pipeline("image-to-text", model=args.model)
    classifier = pipeline(
        "zero-shot-image-classification",
        model=args.classifier_model,
    )
    run_id = create_run(
        conn,
        run_type="captions",
        model_name=args.model,
        classifier_model=args.classifier_model,
        parameters={"min_score": args.min_score, "limit": args.limit},
    )

    with conn:
        conn.execute("UPDATE photo_descriptions SET is_active = 0")
        conn.execute("UPDATE photo_tags SET is_active = 0 WHERE source IN ('caption-keyword', 'zero-shot-label', 'derived')")

    for index, item in enumerate(items, start=1):
        image_path = resolve_image_path(args.image_root, item)
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            caption_result = captioner(image)
            caption = normalize_caption(caption_result[0]["generated_text"])
            label_result = classifier(image, candidate_labels=DEFAULT_LABELS)

        labels = [
            entry["label"]
            for entry in label_result
            if entry["score"] >= args.min_score
        ]
        keyword_tags = derive_keyword_tags(caption)
        tags = sorted(
            {
                *labels,
                *keyword_tags,
                infer_orientation(item),
                item["folder"].lower(),
            }
        )

        with conn:
            conn.execute(
                """
                INSERT INTO photo_descriptions (photo_id, run_id, source, model_name, description, search_text, is_active)
                VALUES (?, ?, 'generated', ?, ?, ?, 1)
                """,
                (
                    item["id"],
                    run_id,
                    args.model,
                    caption,
                    build_search_text(caption, tags, labels, item),
                ),
            )
            for entry in label_result:
                if entry["score"] < args.min_score:
                    continue
                tag_name = entry["label"]
                normalized = normalize_tag(tag_name)
                conn.execute(
                    """
                    INSERT INTO tags (name, tag_type, normalized_name)
                    VALUES (?, 'zero-shot', ?)
                    ON CONFLICT(normalized_name) DO UPDATE SET name=excluded.name
                    """,
                    (tag_name, normalized),
                )
                tag_id = conn.execute(
                    "SELECT id FROM tags WHERE normalized_name = ?",
                    (normalized,),
                ).fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO photo_tags (photo_id, tag_id, run_id, source, confidence, is_active)
                    VALUES (?, ?, ?, 'zero-shot-label', ?, 1)
                    ON CONFLICT(photo_id, tag_id, source) DO UPDATE SET
                      run_id=excluded.run_id,
                      confidence=excluded.confidence,
                      is_active=1,
                      created_at=CURRENT_TIMESTAMP
                    """,
                    (item["id"], tag_id, run_id, float(entry["score"])),
                )

            for tag_name in tags:
                tag_type = "derived" if tag_name in {"landscape", "portrait-orientation", "square"} else "keyword"
                source = "derived" if tag_type == "derived" else "caption-keyword"
                normalized = normalize_tag(tag_name)
                conn.execute(
                    """
                    INSERT INTO tags (name, tag_type, normalized_name)
                    VALUES (?, ?, ?)
                    ON CONFLICT(normalized_name) DO UPDATE SET name=excluded.name, tag_type=excluded.tag_type
                    """,
                    (tag_name, tag_type, normalized),
                )
                tag_id = conn.execute(
                    "SELECT id FROM tags WHERE normalized_name = ?",
                    (normalized,),
                ).fetchone()["id"]
                conn.execute(
                    """
                    INSERT INTO photo_tags (photo_id, tag_id, run_id, source, confidence, is_active)
                    VALUES (?, ?, ?, ?, NULL, 1)
                    ON CONFLICT(photo_id, tag_id, source) DO UPDATE SET
                      run_id=excluded.run_id,
                      confidence=NULL,
                      is_active=1,
                      created_at=CURRENT_TIMESTAMP
                    """,
                    (item["id"], tag_id, run_id, source),
                )
        print(f"[{index}/{len(items)}] described {item['id']}")
    conn.close()
    print(f"Wrote caption metadata into {args.db}")


if __name__ == "__main__":
    main()

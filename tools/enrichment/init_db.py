import argparse
import json
from pathlib import Path

from db import apply_schema, connect_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize SQLite archive database.")
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    archive = json.loads(args.archive.read_text())
    items = archive.get("items", [])

    conn = connect_db(args.db)
    apply_schema(conn)

    with conn:
        for item in items:
            conn.execute(
                """
                INSERT INTO photos (
                  id, filename, folder, source_relative_path, width, height, size_bytes,
                  thumb_src, thumb_width, thumb_height,
                  display_src, display_width, display_height,
                  scanner_make, scanner_model, software, image_datetime,
                  license, credit_line, title, description, approx_year, location, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                  filename=excluded.filename,
                  folder=excluded.folder,
                  source_relative_path=excluded.source_relative_path,
                  width=excluded.width,
                  height=excluded.height,
                  size_bytes=excluded.size_bytes,
                  thumb_src=excluded.thumb_src,
                  thumb_width=excluded.thumb_width,
                  thumb_height=excluded.thumb_height,
                  display_src=excluded.display_src,
                  display_width=excluded.display_width,
                  display_height=excluded.display_height,
                  scanner_make=excluded.scanner_make,
                  scanner_model=excluded.scanner_model,
                  software=excluded.software,
                  image_datetime=excluded.image_datetime,
                  license=excluded.license,
                  credit_line=excluded.credit_line,
                  title=excluded.title,
                  description=excluded.description,
                  approx_year=excluded.approx_year,
                  location=excluded.location,
                  updated_at=CURRENT_TIMESTAMP
                """,
                (
                    item["id"],
                    item["filename"],
                    item["folder"],
                    item["source_relative_path"],
                    item["width"],
                    item["height"],
                    item["size_bytes"],
                    item.get("thumb", {}).get("src"),
                    item.get("thumb", {}).get("width"),
                    item.get("thumb", {}).get("height"),
                    item.get("display", {}).get("src"),
                    item.get("display", {}).get("width"),
                    item.get("display", {}).get("height"),
                    item.get("scanner_make"),
                    item.get("scanner_model"),
                    item.get("software"),
                    item.get("image_datetime"),
                    item.get("license"),
                    item.get("credit_line"),
                    item.get("title"),
                    item.get("description"),
                    item.get("approx_year"),
                    item.get("location"),
                ),
            )

    conn.close()
    print(f"Initialized {args.db} with {len(items)} photos")


if __name__ == "__main__":
    main()

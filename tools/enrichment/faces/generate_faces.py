import argparse
import json
import sys
from pathlib import Path

import numpy as np
import torch
from facenet_pytorch import InceptionResnetV1, MTCNN
from PIL import Image
from sklearn.cluster import DBSCAN

sys.path.append(str(Path(__file__).resolve().parents[1]))
from db import apply_schema, connect_db, create_run  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Detect faces, compute embeddings, and cluster likely people."
    )
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--image-root", type=Path, required=True)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--min-face-size", type=int, default=60)
    parser.add_argument("--cluster-eps", type=float, default=0.35)
    parser.add_argument("--cluster-min-samples", type=int, default=2)
    return parser.parse_args()


def resolve_image_path(image_root: Path, item: dict) -> Path:
    display_src = item.get("display_src")
    if not display_src:
        raise ValueError(f"Missing display src for {item.get('id')}")
    return image_root / display_src.lstrip("/")


def clip_box(box: np.ndarray, image: Image.Image) -> list[int]:
    width, height = image.size
    x1, y1, x2, y2 = box.tolist()
    return [
        max(0, round(x1)),
        max(0, round(y1)),
        min(width, round(x2)),
        min(height, round(y2)),
    ]


def normalize_embedding(vector: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vector)
    if norm == 0:
        return vector
    return vector / norm


def main() -> None:
    args = parse_args()
    conn = connect_db(args.db)
    apply_schema(conn)
    limit_clause = "" if args.limit is None else f" LIMIT {int(args.limit)}"
    items = [
        dict(row)
        for row in conn.execute(
            f"""
            SELECT id, display_src
            FROM photos
            ORDER BY id{limit_clause}
            """
        ).fetchall()
    ]

    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    mtcnn = MTCNN(
        image_size=160,
        margin=14,
        min_face_size=args.min_face_size,
        thresholds=[0.6, 0.7, 0.8],
        post_process=True,
        device=device,
        keep_all=True,
    )
    embedder = InceptionResnetV1(pretrained="vggface2").eval().to(device)
    run_id = create_run(
        conn,
        run_type="faces",
        detector_model="MTCNN",
        embedder_model="InceptionResnetV1(vggface2)",
        parameters={
            "min_face_size": args.min_face_size,
            "cluster_eps": args.cluster_eps,
            "cluster_min_samples": args.cluster_min_samples,
            "limit": args.limit,
            "device": device,
        },
    )

    embeddings = []
    embedding_index = []
    face_items = []

    with conn:
        conn.execute("UPDATE face_detections SET is_active = 0")
        conn.execute("UPDATE people_groups SET is_active = 0 WHERE source = 'face-cluster'")

    for index, item in enumerate(items, start=1):
        image_path = resolve_image_path(args.image_root, item)
        with Image.open(image_path) as image:
            image = image.convert("RGB")
            boxes, probabilities = mtcnn.detect(image)
            faces = mtcnn(image)

        item_faces = []
        if boxes is not None and faces is not None and len(boxes) == len(faces):
            if faces.ndim == 3:
                faces = faces.unsqueeze(0)

            with torch.no_grad():
                vectors = embedder(faces.to(device)).cpu().numpy()

            for face_idx, (box, probability, vector) in enumerate(
                zip(boxes, probabilities, vectors)
            ):
                normalized = normalize_embedding(vector.astype(float))
                embedding_id = f"{item['id']}::face-{face_idx}"
                embeddings.append(normalized)
                embedding_index.append(
                    {
                        "embedding_id": embedding_id,
                        "photo_id": item["id"],
                        "face_index": face_idx,
                        "confidence": round(float(probability), 4),
                        "box": clip_box(np.asarray(box), image),
                    }
                )
                item_faces.append(
                    {
                        "face_index": face_idx,
                        "embedding_id": embedding_id,
                        "box": clip_box(np.asarray(box), image),
                        "confidence": round(float(probability), 4),
                    }
                )

        face_items.append(
            {
                "id": item["id"],
                "source_image": item.get("display_src"),
                "faces": item_faces,
            }
        )
        print(f"[{index}/{len(items)}] processed {item['id']} ({len(item_faces)} faces)")

    labels = []
    if embeddings:
        matrix = np.vstack(embeddings)
        clustering = DBSCAN(
            eps=args.cluster_eps,
            min_samples=args.cluster_min_samples,
            metric="cosine",
        )
        labels = clustering.fit_predict(matrix).tolist()

    label_by_embedding = {}
    groups = {}
    for meta, label in zip(embedding_index, labels):
        group_id = None if label < 0 else f"person-group-{label:04d}"
        label_by_embedding[meta["embedding_id"]] = group_id
        if group_id is None:
            continue
        groups.setdefault(
            group_id,
            {
                "group_id": group_id,
                "label": None,
                "face_count": 0,
                "photo_ids": [],
                "sample_faces": [],
            },
        )
        group = groups[group_id]
        group["face_count"] += 1
        if meta["photo_id"] not in group["photo_ids"]:
            group["photo_ids"].append(meta["photo_id"])
        if len(group["sample_faces"]) < 6:
            group["sample_faces"].append(
                {
                    "photo_id": meta["photo_id"],
                    "face_index": meta["face_index"],
                    "embedding_id": meta["embedding_id"],
                }
            )

    for item in face_items:
        for face in item["faces"]:
            face["person_group_id"] = label_by_embedding.get(face["embedding_id"])

    with conn:
        group_db_ids = {}
        for group_key in sorted(groups):
            conn.execute(
                """
                INSERT INTO people_groups (group_key, label, source, run_id, is_active)
                VALUES (?, NULL, 'face-cluster', ?, 1)
                ON CONFLICT(group_key) DO UPDATE SET
                  source=excluded.source,
                  run_id=excluded.run_id,
                  is_active=1
                """,
                (group_key, run_id),
            )
            group_db_ids[group_key] = conn.execute(
                "SELECT id FROM people_groups WHERE group_key = ?",
                (group_key,),
            ).fetchone()["id"]

        for meta, vector in zip(embedding_index, embeddings):
            conn.execute(
                """
                INSERT INTO face_detections (
                  photo_id, run_id, face_index, embedding_key, x1, y1, x2, y2, confidence, is_active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(embedding_key) DO UPDATE SET
                  photo_id=excluded.photo_id,
                  run_id=excluded.run_id,
                  face_index=excluded.face_index,
                  x1=excluded.x1,
                  y1=excluded.y1,
                  x2=excluded.x2,
                  y2=excluded.y2,
                  confidence=excluded.confidence,
                  is_active=1
                """,
                (
                    meta["photo_id"],
                    run_id,
                    meta["face_index"],
                    meta["embedding_id"],
                    meta["box"][0],
                    meta["box"][1],
                    meta["box"][2],
                    meta["box"][3],
                    meta["confidence"],
                ),
            )
            face_detection_id = conn.execute(
                "SELECT id FROM face_detections WHERE embedding_key = ?",
                (meta["embedding_id"],),
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT INTO face_embeddings (face_detection_id, vector_json, dimension_count)
                VALUES (?, ?, ?)
                ON CONFLICT(face_detection_id) DO UPDATE SET
                  vector_json=excluded.vector_json,
                  dimension_count=excluded.dimension_count,
                  created_at=CURRENT_TIMESTAMP
                """,
                (
                    face_detection_id,
                    json.dumps([round(float(value), 8) for value in vector.tolist()]),
                    len(vector),
                ),
            )
            group_key = label_by_embedding.get(meta["embedding_id"])
            conn.execute(
                """
                INSERT INTO face_group_memberships (face_detection_id, people_group_id, run_id, confidence)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(face_detection_id) DO UPDATE SET
                  people_group_id=excluded.people_group_id,
                  run_id=excluded.run_id,
                  confidence=excluded.confidence,
                  created_at=CURRENT_TIMESTAMP
                """,
                (
                    face_detection_id,
                    None if group_key is None else group_db_ids[group_key],
                    run_id,
                    meta["confidence"],
                ),
            )

    conn.close()
    print(f"Wrote face metadata into {args.db}")


if __name__ == "__main__":
    main()

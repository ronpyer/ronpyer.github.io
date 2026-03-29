PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS photos (
  id TEXT PRIMARY KEY,
  filename TEXT NOT NULL,
  folder TEXT NOT NULL,
  source_relative_path TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL,
  size_bytes INTEGER NOT NULL,
  thumb_src TEXT,
  thumb_width INTEGER,
  thumb_height INTEGER,
  display_src TEXT,
  display_width INTEGER,
  display_height INTEGER,
  scanner_make TEXT,
  scanner_model TEXT,
  software TEXT,
  image_datetime TEXT,
  license TEXT,
  credit_line TEXT,
  title TEXT,
  description TEXT,
  approx_year INTEGER,
  location TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS enrichment_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_type TEXT NOT NULL,
  model_name TEXT,
  classifier_model TEXT,
  detector_model TEXT,
  embedder_model TEXT,
  parameters_json TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS photo_descriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id TEXT NOT NULL,
  run_id INTEGER,
  source TEXT NOT NULL,
  model_name TEXT,
  description TEXT NOT NULL,
  search_text TEXT,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  tag_type TEXT NOT NULL DEFAULT 'keyword',
  normalized_name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS photo_tags (
  photo_id TEXT NOT NULL,
  tag_id INTEGER NOT NULL,
  run_id INTEGER,
  source TEXT NOT NULL,
  confidence REAL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (photo_id, tag_id, source),
  FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
  FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS face_detections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  photo_id TEXT NOT NULL,
  run_id INTEGER,
  face_index INTEGER NOT NULL,
  embedding_key TEXT NOT NULL UNIQUE,
  x1 INTEGER NOT NULL,
  y1 INTEGER NOT NULL,
  x2 INTEGER NOT NULL,
  y2 INTEGER NOT NULL,
  confidence REAL,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(photo_id) REFERENCES photos(id) ON DELETE CASCADE,
  FOREIGN KEY(run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS face_embeddings (
  face_detection_id INTEGER PRIMARY KEY,
  vector_json TEXT NOT NULL,
  dimension_count INTEGER NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(face_detection_id) REFERENCES face_detections(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS people_groups (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  group_key TEXT NOT NULL UNIQUE,
  label TEXT,
  source TEXT NOT NULL,
  run_id INTEGER,
  is_active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS face_group_memberships (
  face_detection_id INTEGER PRIMARY KEY,
  people_group_id INTEGER,
  run_id INTEGER,
  confidence REAL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY(face_detection_id) REFERENCES face_detections(id) ON DELETE CASCADE,
  FOREIGN KEY(people_group_id) REFERENCES people_groups(id) ON DELETE SET NULL,
  FOREIGN KEY(run_id) REFERENCES enrichment_runs(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_photos_folder ON photos(folder);
CREATE INDEX IF NOT EXISTS idx_photo_descriptions_photo_active ON photo_descriptions(photo_id, is_active);
CREATE INDEX IF NOT EXISTS idx_photo_tags_photo_active ON photo_tags(photo_id, is_active);
CREATE INDEX IF NOT EXISTS idx_face_detections_photo_active ON face_detections(photo_id, is_active);

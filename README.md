# Ronald Lee Pyer Photo Archive

This repository contains the Astro site and enrichment tooling for preserving and sharing Ronald Lee Pyer's scanned 35mm photo archive.

## Site

Install dependencies and run the site locally:

```bash
npm install
npm run dev
```

Build the static site into `docs/` for GitHub Pages:

```bash
npm run build
```

## Enrichment Database

SQLite is the authoritative metadata store for enrichment work. The database lives at [data/archive.db](/Users/jarad/git/ronpyer.github.io/data/archive.db) and is initialized from [src/data/archive.json](/Users/jarad/git/ronpyer.github.io/src/data/archive.json).

Set up a local virtualenv for the enrichment tooling:

```bash
./tools/enrichment/setup_venv.sh
```

That default setup installs the caption/tag pipeline into `.venv`.
The face pipeline uses a separate environment because `facenet-pytorch` currently requires an older Torch line:

```bash
./tools/enrichment/setup_venv.sh faces
```

The schema lives in [tools/enrichment/schema.sql](/Users/jarad/git/ronpyer.github.io/tools/enrichment/schema.sql). It separates:

- photos and source metadata
- generated descriptions
- normalized tags
- face detections
- face embeddings
- people groups and memberships
- enrichment run provenance

Activate the caption environment when running caption/export tools manually:

```bash
source .venv/bin/activate
```

Initialize or refresh the base database:

```bash
python tools/enrichment/init_db.py \
  --archive src/data/archive.json \
  --db data/archive.db
```

## Enrichment Scripts

The repo includes two local Python pipelines that write into SQLite:

- `captions`: generates plaintext descriptions and normalized search tags
- `faces`: detects faces, computes embeddings, and clusters likely people groupings

Both pipelines read from [data/archive.db](/Users/jarad/git/ronpyer.github.io/data/archive.db) and the existing derivative images in [public/images/display](/Users/jarad/git/ronpyer.github.io/public/images/display), but they currently use separate virtualenvs.

Run the caption/tag pipeline:

```bash
python tools/enrichment/captions/generate_descriptions.py \
  --db data/archive.db \
  --image-root public
```

Run the face grouping pipeline:

```bash
source .venv-faces/bin/activate
python tools/enrichment/faces/generate_faces.py \
  --db data/archive.db \
  --image-root public
```

Useful overrides:

```bash
python tools/enrichment/captions/generate_descriptions.py --db data/archive.db --image-root public --limit 25
python tools/enrichment/faces/generate_faces.py --db data/archive.db --image-root public --limit 100 --min-face-size 80 --cluster-eps 0.32
```

Export public JSON build artifacts from SQLite:

```bash
python tools/enrichment/export_public_json.py \
  --db data/archive.db \
  --descriptions-output src/data/enrichment/descriptions.json \
  --faces-output src/data/enrichment/faces.json \
  --people-output src/data/enrichment/people.json
```

That export step writes:

- [src/data/enrichment/descriptions.json](/Users/jarad/git/ronpyer.github.io/src/data/enrichment/descriptions.json)
- [src/data/enrichment/faces.json](/Users/jarad/git/ronpyer.github.io/src/data/enrichment/faces.json)
- [src/data/enrichment/people.json](/Users/jarad/git/ronpyer.github.io/src/data/enrichment/people.json)

Notes:

- The first run will download model weights into your local Python cache.
- These default to CPU-friendly open-source models, so expect the first pass to be slow.
- Raw face embeddings stay in SQLite and should be treated as internal/private data.
- The generated descriptions and groupings should be treated as draft metadata for family review, not final truth.

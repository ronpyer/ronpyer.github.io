from pathlib import Path
import json
from PIL import Image, ImageOps

PROJECT_ROOT = Path('/home/rasp/ronpyer.github.io')
SOURCE_ROOT = Path('/home/rasp/pics')
MANIFEST_PATH = PROJECT_ROOT / 'data' / 'manifest.json'
SITE_PUBLIC = PROJECT_ROOT / 'public'
THUMBS_DIR = SITE_PUBLIC / 'images' / 'thumbs'
DISPLAY_DIR = SITE_PUBLIC / 'images' / 'display'
SITE_DATA = PROJECT_ROOT / 'src' / 'data'
ARCHIVE_JSON = SITE_DATA / 'archive.json'

THUMB_MAX = (480, 480)
DISPLAY_MAX = (1600, 1600)
LIMIT = None


def make_derivative(src: Path, dest: Path, max_size: tuple[int, int], quality: int) -> tuple[int, int]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert('RGB')
        img.thumbnail(max_size)
        img.save(dest, 'JPEG', quality=quality, optimize=True, progressive=True)
        return img.size


def main():
    manifest = json.loads(MANIFEST_PATH.read_text())
    items = manifest['items'] if LIMIT is None else manifest['items'][:LIMIT]
    archive_items = []

    for item in items:
        rel = Path(item['relative_path'])
        src = SOURCE_ROOT / rel
        stem = rel.as_posix().replace('/', '__').rsplit('.', 1)[0]
        thumb_name = f'{stem}.jpg'
        display_name = f'{stem}.jpg'
        thumb_path = THUMBS_DIR / thumb_name
        display_path = DISPLAY_DIR / display_name

        thumb_w, thumb_h = make_derivative(src, thumb_path, THUMB_MAX, quality=78)
        disp_w, disp_h = make_derivative(src, display_path, DISPLAY_MAX, quality=85)

        archive_items.append({
            'id': item['id'],
            'filename': item['filename'],
            'folder': item['folder'],
            'source_relative_path': item['relative_path'],
            'width': item['width'],
            'height': item['height'],
            'size_bytes': item['size_bytes'],
            'thumb': {
                'src': f'/images/thumbs/{thumb_name}',
                'width': thumb_w,
                'height': thumb_h,
            },
            'display': {
                'src': f'/images/display/{display_name}',
                'width': disp_w,
                'height': disp_h,
            },
            'scanner_make': item.get('scanner_make'),
            'scanner_model': item.get('scanner_model'),
            'software': item.get('software'),
            'image_datetime': item.get('image_datetime'),
            'license': 'CC0-1.0',
            'credit_line': 'Photograph by Ronald Lee Pyer, digitized and published by Jarad Ronald Peckenpaugh.',
            'title': None,
            'description': None,
            'tags': [],
            'approx_year': None,
            'location': None,
        })

    output = {
        'title': 'Ronald Lee Pyer Photo Archive',
        'license': 'CC0-1.0',
        'credit_line': 'Photograph by Ronald Lee Pyer, digitized and published by Jarad Ronald Peckenpaugh.',
        'item_count': len(archive_items),
        'items': archive_items,
    }

    SITE_DATA.mkdir(parents=True, exist_ok=True)
    ARCHIVE_JSON.write_text(json.dumps(output, indent=2))
    print(f'Wrote {ARCHIVE_JSON} with {len(archive_items)} items')
    print(f'Thumbnails: {THUMBS_DIR}')
    print(f'Display images: {DISPLAY_DIR}')


if __name__ == '__main__':
    main()

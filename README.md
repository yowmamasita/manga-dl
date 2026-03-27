# manga-dl

Download manga chapters from TCB Scans and compile into iPad-optimized CBZ/PDF.

Requires Chrome running with remote debugging and `chrome-remote-interface` (npm).

## Setup

```bash
npm install chrome-remote-interface
pip install Pillow
```

Chrome must be running with:
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

## Usage

### 1. List available chapters

```bash
node list_chapters.js 1058 1125 > chapters.json
```

### 2. Extract image URLs

```bash
node extract.js chapters.json chapter_images.json
```

The extractor auto-detects and retries when TCB's CDN serves cached images from the wrong chapter.

### 3. Download and compile

```bash
python build.py chapter_images.json --output-prefix "OnePiece_Egghead_Arc"
```

Options:
- `--quality 75` — JPEG quality (default: 75)
- `--max-width 1400` — max image width in px (default: 1400)
- `--images-dir ./imgs` — custom download directory
- `--skip-pdf` — only generate CBZ

## Arc Reference

| Arc | Chapters | Status |
|-----|----------|--------|
| Wano Country | 909–1057 | Completed |
| Egghead | 1058–1125 | Completed |
| Elbaf | 1126–ongoing | Ongoing (latest: 1178) |

## Output Formats

- **CBZ** — recommended for iPad. Use [Panels](https://apps.apple.com/app/panels-comic-reader/id1236567663) (free) or YACReader.
- **PDF** — fallback for Apple Books.

# manga-dl

Download One Piece chapters from TCB Scans and compile into iPad-optimized CBZ/PDF.

Pure Python — no browser, no Node.js, no Selenium/Playwright needed.

## Setup

```bash
pip install Pillow
```

## Usage

### List chapters

```bash
python manga_dl.py list 1058 1125
python manga_dl.py list 1126 1178 --json
```

### Download and compile

```bash
# Egghead arc
python manga_dl.py download 1058 1125 -o "OnePiece_Egghead"

# Elbaf arc
python manga_dl.py download 1126 1178 -o "OnePiece_Elbaf"

# Custom settings
python manga_dl.py download 1126 1178 -o "OnePiece_Elbaf" -q 80 --max-width 1600 -d ./output
```

Options:
- `-o, --output` — output filename prefix
- `-d, --output-dir` — output directory (default: current)
- `-q, --quality` — JPEG quality 1-100 (default: 75)
- `--max-width` — max image width in px (default: 1400)
- `--skip-pdf` — only generate CBZ

The tool auto-detects and retries when TCB's CDN serves cached images from the wrong chapter.

## Arc Reference

| Arc | Chapters | Status |
|-----|----------|--------|
| Wano Country | 909–1057 | Completed |
| Egghead | 1058–1125 | Completed |
| Elbaf | 1126–ongoing | Ongoing (latest: 1178) |

## Output

- **CBZ** — recommended for iPad. Use [Panels](https://apps.apple.com/app/panels-comic-reader/id1236567663) (free) or YACReader.
- **PDF** — fallback for Apple Books.

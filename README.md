# manga-dl

Download One Piece chapters from TCB Scans and compile into iPad-optimized CBZ/PDF.

Pure Python — no browser needed.

## Setup

```bash
pip install Pillow
```

## Usage

### List known arcs

```bash
python manga_dl.py arcs
```
```
Arc                  Chapters        Status
Wano Country         909-1057        completed
Egghead              1058-1125       completed
Elbaf                1126-ongoing    ongoing
```

### Download by arc

```bash
python manga_dl.py download --arc egghead
python manga_dl.py download --arc elbaf
python manga_dl.py download --arc wano
```

### Download by chapter range

```bash
python manga_dl.py download 1058 1125 -o "OnePiece_Egghead"
```

### List chapters

```bash
python manga_dl.py list --arc egghead
python manga_dl.py list 1058 1125
```

### Options

- `-a, --arc` — arc name (partial match, case-insensitive)
- `-o, --output` — output filename prefix (auto-generated from arc name if omitted)
- `-d, --output-dir` — output directory (default: current)
- `-q, --quality` — JPEG quality 1-100 (default: 75)
- `--max-width` — max image width in px (default: 1400)
- `--skip-pdf` — only generate CBZ

## Output

- **CBZ** — recommended for iPad. Use [Panels](https://apps.apple.com/app/panels-comic-reader/id1236567663) (free) or YACReader.
- **PDF** — fallback for Apple Books.

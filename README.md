# manga-dl

Download One Piece chapters from TCB Scans and compile into iPad-optimized CBZ/PDF.

Supports both B&W (latest chapters) and official Digital Colored Comics (ch 1-1065).

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
Arc                  Chapters        Colored
Romance Dawn         1-7             yes
Arlong Park          69-95           yes
Marineford           550-580         yes
Wano Country         909-1057        yes
Egghead              1058-1125       partial (to 1065)
Elbaf                1126-ongoing    no
...
```

### Download by arc

```bash
# B&W (default)
python manga_dl.py download --arc egghead
python manga_dl.py download --arc elbaf

# Colored
python manga_dl.py download --arc marineford --colored
python manga_dl.py download --arc "arlong park" --colored
```

### Download by chapter range

```bash
python manga_dl.py download 1 100 --colored
python manga_dl.py download 1058 1125 -o "OnePiece_Egghead"
```

### List chapters

```bash
python manga_dl.py list --arc wano
python manga_dl.py list 1 100 --colored
```

### Options

- `-a, --arc` — arc name (partial match, case-insensitive)
- `-c, --colored` — use colored source (chapters 1-1065)
- `-o, --output` — output filename prefix (auto-generated from arc name if omitted)
- `-d, --output-dir` — output directory (default: current)
- `-q, --quality` — JPEG quality 1-100 (default: 75)
- `--max-width` — max image width in px (default: 1400)
- `--skip-pdf` — only generate CBZ

## Sources

| Source | Chapters | Flag |
|--------|----------|------|
| TCB Scans (B&W) | latest, ongoing | default |
| Digital Colored Comics | 1-1065 | `--colored` |

## Output

- **CBZ** — recommended for iPad. Use [Panels](https://apps.apple.com/app/panels-comic-reader/id1236567663) (free) or YACReader.
- **PDF** — fallback for Apple Books.

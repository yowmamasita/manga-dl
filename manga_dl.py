#!/usr/bin/env python3
"""
manga-dl: Download manga chapters from TCB Scans and compile into CBZ/PDF.

No browser required — uses plain HTTP requests.

Usage:
    # List known arcs
    python manga_dl.py arcs

    # Download by arc name
    python manga_dl.py download --arc egghead
    python manga_dl.py download --arc elbaf

    # Download colored version (chapters 1-1065)
    python manga_dl.py download --arc marineford --colored
    python manga_dl.py download 1 100 --colored

    # Download by chapter range
    python manga_dl.py download 1058 1125 -o "OnePiece_Egghead"

    # List chapters
    python manga_dl.py list --arc wano
"""

import argparse
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from PIL import Image

ARCS_FILE = Path(__file__).parent / "arcs.json"

# Sources
SOURCES = {
    "bw": {
        "name": "TCB Scans (B&W)",
        "base_url": "https://tcbonepiecechapters.com",
        "max_chapter": None,  # ongoing
    },
    "colored": {
        "name": "Digital Colored Comics",
        "base_url": "https://ww12.readonepiece.com",
        "max_chapter": 1065,
    },
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
}


def load_arcs():
    """Load arc definitions from arcs.json."""
    with open(ARCS_FILE) as f:
        return json.load(f)["arcs"]


def resolve_arc(name):
    """Look up an arc by name (case-insensitive, partial match)."""
    arcs = load_arcs()
    name_lower = name.lower()
    for arc in arcs:
        if name_lower in arc["name"].lower():
            start = arc["chapters"][0]
            end = arc["chapters"][1] or arc.get("latest_chapter", 9999)
            return arc, start, end
    arc_names = ", ".join(a["name"] for a in arcs)
    print(f"Unknown arc '{name}'. Available: {arc_names}", file=sys.stderr)
    sys.exit(1)


def fetch(url, referer=None):
    """Fetch a URL and return the response body as string."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def fetch_bytes(url, referer=None):
    """Fetch a URL and return raw bytes."""
    headers = dict(HEADERS)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


# --- TCB Scans (B&W) ---

def tcb_list_chapters(start=0, end=9999):
    """Scrape TCB Scans index page for chapter links."""
    base = SOURCES["bw"]["base_url"]
    html = fetch(f"{base}/mangas/5/one-piece", referer=base)

    pattern = (
        r'href="(/chapters/\d+/one-piece-chapter-(\d+)[^"]*)"[^>]*>\s*'
        r'<div[^>]*>One Piece\s+Chapter \d+</div>\s*'
        r'<div[^>]*>([^<]*)</div>'
    )
    matches = re.findall(pattern, html, re.DOTALL)

    chapters = []
    seen = set()
    for path, ch_num_str, title in matches:
        ch_num = int(ch_num_str)
        if ch_num in seen or ch_num < start or ch_num > end:
            continue
        seen.add(ch_num)
        chapters.append({
            "chapter": ch_num,
            "title": title.strip(),
            "url": f"{base}{path}",
        })

    chapters.sort(key=lambda c: c["chapter"])
    return chapters


def tcb_extract_images(chapter_url, expected_ch_num):
    """Extract manga image URLs from a TCB Scans chapter page."""
    base = SOURCES["bw"]["base_url"]
    for attempt in range(3):
        html = fetch(chapter_url, referer=base)

        all_imgs = re.findall(
            r'src="(https://cdn\.onepiecechapters\.com/file/CDN-M-A-N/[^"]+)"',
            html,
        )

        manga_imgs = [
            url for url in all_imgs
            if not any(ad in url.lower() for ad in ["sticky", "halfpage", "half-page", "banner", "half_page"])
        ]

        if not manga_imgs:
            if attempt < 2:
                time.sleep(2)
                continue
            return manga_imgs

        # Check for chapter mismatch in filenames (TCB caching bug)
        file_ch_nums = []
        for url in manga_imgs:
            fname = url.split("/")[-1].lower()
            nums = re.findall(r"(\d{4})", fname)
            for n in nums:
                n_int = int(n)
                if 900 <= n_int <= 1300:
                    file_ch_nums.append(n_int)

        has_mismatch = any(n != expected_ch_num for n in file_ch_nums)

        if not has_mismatch or not file_ch_nums:
            return manga_imgs

        wrong = next(n for n in file_ch_nums if n != expected_ch_num)
        print(f"  Attempt {attempt + 1}: got ch {wrong} images, retrying...", file=sys.stderr)
        time.sleep(2)

    print(f"  WARNING: could not get correct images after 3 attempts", file=sys.stderr)
    return manga_imgs


# --- Colored (readonepiece.com) ---

def colored_list_chapters(start=0, end=9999):
    """Scrape readonepiece.com for colored chapter links."""
    base = SOURCES["colored"]["base_url"]
    max_ch = SOURCES["colored"]["max_chapter"]
    end = min(end, max_ch)

    html = fetch(f"{base}/manga/one-piece-digital-colored-comics/", referer=base)

    links = re.findall(
        r'href="(https?://[^"]*one-piece-digital-colored-comics-chapter-(\d+)/)"',
        html,
    )

    chapters = []
    seen = set()
    for url, ch_num_str in links:
        ch_num = int(ch_num_str)
        if ch_num in seen or ch_num < start or ch_num > end:
            continue
        seen.add(ch_num)
        chapters.append({
            "chapter": ch_num,
            "title": "",
            "url": url,
        })

    chapters.sort(key=lambda c: c["chapter"])
    return chapters


def colored_extract_images(chapter_url, expected_ch_num):
    """Extract manga image URLs from a readonepiece.com colored chapter page."""
    base = SOURCES["colored"]["base_url"]
    html = fetch(chapter_url, referer=base)

    all_imgs = re.findall(
        r'src="(https://cdn\.readonepiece\.com/file/[^"]+)"',
        html,
    )

    # Deduplicate while preserving order
    seen = set()
    manga_imgs = []
    for url in all_imgs:
        if url not in seen:
            seen.add(url)
            manga_imgs.append(url)

    return manga_imgs


# --- Common ---

def download_image(url, filepath, referer=None):
    """Download an image, skip if already exists."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    for attempt in range(3):
        try:
            data = fetch_bytes(url, referer=referer)
            with open(filepath, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                print(f"  FAILED: {url} -> {e}", file=sys.stderr)
                return False
    return False


def optimize_image(filepath, max_width):
    """Load image, convert to RGB, resize if needed."""
    img = Image.open(filepath)
    if img.mode != "RGB":
        img = img.convert("RGB")
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def verify_chapters(chapters, images_dir, colored=False):
    """Verify all downloaded chapters for issues."""
    issues = []
    for ch in chapters:
        ch_num = ch["chapter"]
        ch_dir = images_dir / f"ch_{ch_num}"
        pages = sorted(ch_dir.glob("page_*"))

        if len(pages) == 0:
            issues.append(f"Ch {ch_num}: NO PAGES")
            continue

        # Filename mismatch check (TCB only — colored filenames are UUIDs)
        if not colored:
            for i, url in enumerate(ch["images"]):
                fname = url.split("/")[-1].lower()
                nums = re.findall(r"(\d{4})", fname)
                for n in nums:
                    n_int = int(n)
                    if 900 <= n_int <= 1300 and n_int != ch_num:
                        issues.append(f"Ch {ch_num}: page {i} filename has ch {n_int} MISMATCH")

        for p in pages:
            if p.stat().st_size < 10000:
                issues.append(f"Ch {ch_num}: {p.name} too small ({p.stat().st_size}b)")
            try:
                img = Image.open(p)
                img.verify()
            except Exception:
                issues.append(f"Ch {ch_num}: {p.name} CORRUPT")

        if len(pages) < 10:
            issues.append(f"Ch {ch_num}: only {len(pages)} pages")

    return issues


def get_source_fns(colored=False):
    """Return the appropriate list/extract functions for the source."""
    if colored:
        return colored_list_chapters, colored_extract_images, SOURCES["colored"]
    return tcb_list_chapters, tcb_extract_images, SOURCES["bw"]


# --- Commands ---

def cmd_arcs(args):
    """List known arcs."""
    arcs = load_arcs()
    max_colored = SOURCES["colored"]["max_chapter"]
    print(f"{'Arc':<20} {'Chapters':<15} {'Colored'}")
    print(f"{'---':<20} {'--------':<15} {'-------'}")
    for arc in arcs:
        start = arc["chapters"][0]
        end = arc["chapters"][1]
        if end:
            ch_range = f"{start}-{end}"
        else:
            ch_range = f"{start}-ongoing ({arc.get('latest_chapter', '?')})"

        if end and end <= max_colored:
            colored = "yes"
        elif start <= max_colored:
            colored = f"partial (to {max_colored})"
        else:
            colored = "no"

        print(f"{arc['name']:<20} {ch_range:<15} {colored}")


def cmd_list(args):
    """List available chapters."""
    if args.arc:
        arc, args.start, args.end = resolve_arc(args.arc)
        print(f"Arc: {arc['name']}", file=sys.stderr)

    list_fn, _, source = get_source_fns(args.colored)

    if args.colored:
        max_ch = source["max_chapter"]
        if args.start > max_ch:
            print(f"Colored version only goes up to chapter {max_ch}", file=sys.stderr)
            sys.exit(1)
        args.end = min(args.end, max_ch)
        print(f"Source: {source['name']} (up to ch {max_ch})\n", file=sys.stderr)

    chapters = list_fn(args.start, args.end)
    if not chapters:
        print("No chapters found", file=sys.stderr)
        return

    if args.json:
        print(json.dumps(chapters, indent=2))
    else:
        print(f"{'Ch':>6}  Title")
        print(f"{'--':>6}  -----")
        for ch in chapters:
            print(f"{ch['chapter']:>6}  {ch['title']}")
        print(f"\n{len(chapters)} chapters ({chapters[0]['chapter']}-{chapters[-1]['chapter']})")


def cmd_download(args):
    """Download chapters and compile into CBZ/PDF."""
    if args.arc:
        arc, args.start, args.end = resolve_arc(args.arc)
        if not args.output:
            arc_slug = arc["name"].replace(" ", "_")
            suffix = "_Colored" if args.colored else ""
            args.output = f"OnePiece_{arc_slug}{suffix}"

    list_fn, extract_fn, source = get_source_fns(args.colored)

    if args.colored:
        max_ch = source["max_chapter"]
        if args.start > max_ch:
            print(f"Colored version only goes up to chapter {max_ch}", file=sys.stderr)
            sys.exit(1)
        if args.end > max_ch:
            print(f"Note: colored version ends at ch {max_ch}, capping range", file=sys.stderr)
            args.end = max_ch

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Step 1: List chapters
    print(f"Source: {source['name']}", file=sys.stderr)
    print("Fetching chapter list...", file=sys.stderr)
    chapters = list_fn(args.start, args.end)
    if not chapters:
        print("No chapters found", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(chapters)} chapters ({chapters[0]['chapter']}-{chapters[-1]['chapter']})", file=sys.stderr)

    # Step 2: Extract image URLs
    print("\n=== EXTRACTING IMAGE URLS ===", file=sys.stderr)
    for ch in chapters:
        print(f"Ch {ch['chapter']}: {ch['title']}", file=sys.stderr)
        ch["images"] = extract_fn(ch["url"], ch["chapter"])
        print(f"  -> {len(ch['images'])} pages", file=sys.stderr)
        time.sleep(0.3)

    # Save chapter data for reuse
    data_path = output_dir / "chapter_data.json"
    with open(data_path, "w") as f:
        json.dump(chapters, f, indent=2)

    total_images = sum(len(ch["images"]) for ch in chapters)
    print(f"\nTotal: {total_images} pages to download", file=sys.stderr)

    # Step 3: Download images
    referer = source["base_url"]
    print("\n=== DOWNLOADING ===", file=sys.stderr)
    downloaded = 0
    failed = 0
    for ch in chapters:
        ch_num = ch["chapter"]
        ch_dir = images_dir / f"ch_{ch_num}"
        ch_dir.mkdir(exist_ok=True)
        print(f"Ch {ch_num} ({len(ch['images'])} pages)", file=sys.stderr)
        for i, img_url in enumerate(ch["images"]):
            ext = img_url.rsplit(".", 1)[-1].split("?")[0]
            if ext not in ("png", "jpg", "jpeg", "webp"):
                ext = "png"
            filepath = ch_dir / f"page_{i:03d}.{ext}"
            if download_image(img_url, filepath, referer=referer):
                downloaded += 1
            else:
                failed += 1
            time.sleep(0.1)
    print(f"Download: {downloaded} ok, {failed} failed", file=sys.stderr)

    # Step 4: Verify
    print("\n=== VERIFYING ===", file=sys.stderr)
    issues = verify_chapters(chapters, images_dir, colored=args.colored)
    if issues:
        print(f"{len(issues)} issues found:", file=sys.stderr)
        for issue in issues:
            print(f"  !! {issue}", file=sys.stderr)
    else:
        print("All chapters verified OK", file=sys.stderr)

    # Step 5: Compile CBZ
    prefix = args.output or f"OnePiece_Ch{args.start}-{args.end}"
    cbz_path = output_dir / f"{prefix}.cbz"

    print("\n=== COMPILING CBZ ===", file=sys.stderr)
    page_num = 0
    all_images_for_pdf = []

    with zipfile.ZipFile(str(cbz_path), "w", zipfile.ZIP_STORED) as zf:
        for ch in chapters:
            ch_dir = images_dir / f"ch_{ch['chapter']}"
            pages = sorted(ch_dir.glob("page_*"))
            for page_path in pages:
                try:
                    img = optimize_image(page_path, args.max_width)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=args.quality, optimize=True)
                    zf.writestr(f"{page_num:05d}.jpg", buf.getvalue())
                    all_images_for_pdf.append(img)
                    page_num += 1
                except Exception as e:
                    print(f"  Error: {page_path}: {e}", file=sys.stderr)

    cbz_mb = cbz_path.stat().st_size / (1024 * 1024)
    print(f"CBZ: {cbz_path.name} — {cbz_mb:.0f} MB, {page_num} pages", file=sys.stderr)

    # Step 6: Compile PDF (unless skipped)
    if not args.skip_pdf and all_images_for_pdf:
        pdf_path = output_dir / f"{prefix}.pdf"
        print("Creating PDF...", file=sys.stderr)
        all_images_for_pdf[0].save(
            str(pdf_path), "PDF",
            save_all=True, append_images=all_images_for_pdf[1:],
            quality=args.quality, optimize=True,
        )
        pdf_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"PDF: {pdf_path.name} — {pdf_mb:.0f} MB", file=sys.stderr)

    # Step 7: Final CBZ integrity check
    print("\n=== FINAL CHECK ===", file=sys.stderr)
    with zipfile.ZipFile(str(cbz_path)) as zf:
        cbz_files = sorted(f for f in zf.namelist() if f.endswith(".jpg"))
        bad = [f for f in cbz_files if len(zf.read(f)) < 10000]
        if bad:
            print(f"!! {len(bad)} corrupt pages in CBZ", file=sys.stderr)
        else:
            print(f"ALL CLEAR: {len(cbz_files)} pages, no issues", file=sys.stderr)

    print("\nDone!", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="Download manga chapters from TCB Scans into CBZ/PDF"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # arcs
    sub.add_parser("arcs", help="List known arcs with colored availability")

    # list
    p_list = sub.add_parser("list", help="List available chapters")
    p_list.add_argument("start", type=int, nargs="?", help="Start chapter number")
    p_list.add_argument("end", type=int, nargs="?", help="End chapter number")
    p_list.add_argument("--arc", "-a", help="Arc name (e.g. egghead, elbaf, wano)")
    p_list.add_argument("--colored", "-c", action="store_true", help="Use colored source (ch 1-1065)")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # download
    p_dl = sub.add_parser("download", help="Download and compile chapters")
    p_dl.add_argument("start", type=int, nargs="?", help="Start chapter number")
    p_dl.add_argument("end", type=int, nargs="?", help="End chapter number")
    p_dl.add_argument("--arc", "-a", help="Arc name (e.g. egghead, elbaf, wano)")
    p_dl.add_argument("--colored", "-c", action="store_true", help="Use colored source (ch 1-1065)")
    p_dl.add_argument("--output", "-o", default=None, help="Output filename prefix")
    p_dl.add_argument("--output-dir", "-d", default=".", help="Output directory (default: current)")
    p_dl.add_argument("--quality", "-q", type=int, default=75, help="JPEG quality (default: 75)")
    p_dl.add_argument("--max-width", type=int, default=1400, help="Max image width in px (default: 1400)")
    p_dl.add_argument("--skip-pdf", action="store_true", help="Only generate CBZ, skip PDF")

    args = parser.parse_args()

    if args.command == "arcs":
        cmd_arcs(args)
    elif args.command == "list":
        if not args.arc and (args.start is None or args.end is None):
            p_list.error("provide start/end chapter numbers or --arc")
        cmd_list(args)
    elif args.command == "download":
        if not args.arc and (args.start is None or args.end is None):
            p_dl.error("provide start/end chapter numbers or --arc")
        cmd_download(args)


if __name__ == "__main__":
    main()

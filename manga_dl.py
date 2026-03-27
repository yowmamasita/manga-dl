#!/usr/bin/env python3
"""
manga-dl: Download manga chapters from TCB Scans and compile into CBZ/PDF.

No browser required — uses plain HTTP requests.

Usage:
    # List chapters for an arc
    python manga_dl.py list 1058 1125

    # Download and compile
    python manga_dl.py download 1058 1125 --output "OnePiece_Egghead"

    # Download with custom settings
    python manga_dl.py download 1126 1178 --output "OnePiece_Elbaf" --quality 80 --max-width 1600
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

BASE_URL = "https://tcbonepiecechapters.com"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Referer": f"{BASE_URL}/",
}


def fetch(url):
    """Fetch a URL and return the response body as string."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode()


def fetch_bytes(url):
    """Fetch a URL and return raw bytes."""
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


def list_chapters(start=0, end=9999):
    """Scrape the manga index page for chapter links."""
    html = fetch(f"{BASE_URL}/mangas/5/one-piece")

    # Structure: <a href="/chapters/ID/one-piece-chapter-NUM" ...>
    #              <div>One Piece Chapter NUM</div>
    #              <div>Title</div>
    #            </a>
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
            "url": f"{BASE_URL}{path}",
        })

    chapters.sort(key=lambda c: c["chapter"])
    return chapters


def extract_images(chapter_url, expected_ch_num):
    """Fetch a chapter page and extract manga image URLs."""
    for attempt in range(3):
        html = fetch(chapter_url)

        # Find all CDN image URLs with the fixed-ratio-content class
        # Pattern: <img ... class="fixed-ratio-content" ... src="URL" ...>
        # or src before class — just find all CDN image URLs in the page
        all_imgs = re.findall(
            r'src="(https://cdn\.onepiecechapters\.com/file/CDN-M-A-N/[^"]+)"',
            html,
        )

        # Filter out ads (sticky, half-page, etc.)
        manga_imgs = [
            url for url in all_imgs
            if not any(ad in url.lower() for ad in ["sticky", "halfpage", "half-page", "banner", "half_page"])
        ]

        if not manga_imgs:
            if attempt < 2:
                time.sleep(2)
                continue
            return manga_imgs

        # Check for chapter mismatch in filenames
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
    return manga_imgs  # return whatever we got last


def download_image(url, filepath):
    """Download an image, skip if already exists."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    for attempt in range(3):
        try:
            data = fetch_bytes(url)
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


def verify_chapters(chapters, images_dir):
    """Verify all downloaded chapters for issues."""
    issues = []
    for ch in chapters:
        ch_num = ch["chapter"]
        ch_dir = images_dir / f"ch_{ch_num}"
        pages = sorted(ch_dir.glob("page_*"))

        if len(pages) == 0:
            issues.append(f"Ch {ch_num}: NO PAGES")
            continue

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


def cmd_list(args):
    """List available chapters."""
    chapters = list_chapters(args.start, args.end)
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
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # Step 1: List chapters
    print("Fetching chapter list...", file=sys.stderr)
    chapters = list_chapters(args.start, args.end)
    if not chapters:
        print("No chapters found", file=sys.stderr)
        sys.exit(1)
    print(f"Found {len(chapters)} chapters ({chapters[0]['chapter']}-{chapters[-1]['chapter']})", file=sys.stderr)

    # Step 2: Extract image URLs
    print("\n=== EXTRACTING IMAGE URLS ===", file=sys.stderr)
    for ch in chapters:
        print(f"Ch {ch['chapter']}: {ch['title']}", file=sys.stderr)
        ch["images"] = extract_images(ch["url"], ch["chapter"])
        print(f"  -> {len(ch['images'])} pages", file=sys.stderr)
        time.sleep(0.3)

    # Save chapter data for reuse
    data_path = output_dir / "chapter_data.json"
    with open(data_path, "w") as f:
        json.dump(chapters, f, indent=2)

    total_images = sum(len(ch["images"]) for ch in chapters)
    print(f"\nTotal: {total_images} pages to download", file=sys.stderr)

    # Step 3: Download images
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
            if download_image(img_url, filepath):
                downloaded += 1
            else:
                failed += 1
            time.sleep(0.1)
    print(f"Download: {downloaded} ok, {failed} failed", file=sys.stderr)

    # Step 4: Verify
    print("\n=== VERIFYING ===", file=sys.stderr)
    issues = verify_chapters(chapters, images_dir)
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

    # list
    p_list = sub.add_parser("list", help="List available chapters")
    p_list.add_argument("start", type=int, help="Start chapter number")
    p_list.add_argument("end", type=int, help="End chapter number")
    p_list.add_argument("--json", action="store_true", help="Output as JSON")

    # download
    p_dl = sub.add_parser("download", help="Download and compile chapters")
    p_dl.add_argument("start", type=int, help="Start chapter number")
    p_dl.add_argument("end", type=int, help="End chapter number")
    p_dl.add_argument("--output", "-o", default=None, help="Output filename prefix")
    p_dl.add_argument("--output-dir", "-d", default=".", help="Output directory (default: current)")
    p_dl.add_argument("--quality", "-q", type=int, default=75, help="JPEG quality (default: 75)")
    p_dl.add_argument("--max-width", type=int, default=1400, help="Max image width in px (default: 1400)")
    p_dl.add_argument("--skip-pdf", action="store_true", help="Only generate CBZ, skip PDF")

    args = parser.parse_args()

    if args.command == "list":
        cmd_list(args)
    elif args.command == "download":
        cmd_download(args)


if __name__ == "__main__":
    main()

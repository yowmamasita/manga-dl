#!/usr/bin/env python3
"""
Download manga chapter images and compile into iPad-optimized CBZ and PDF.

Usage:
    python build.py <chapter_images.json> [--output-prefix PREFIX] [--quality Q] [--max-width W]

Example:
    python build.py egghead_images.json --output-prefix "OnePiece_Egghead_Arc"
"""

import argparse
import io
import json
import os
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from PIL import Image


def download_image(url, filepath):
    """Download an image, skip if already exists."""
    if filepath.exists() and filepath.stat().st_size > 0:
        return True
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                'Referer': 'https://tcbonepiecechapters.com/',
            })
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            with open(filepath, 'wb') as f:
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
    if img.mode != 'RGB':
        img = img.convert('RGB')
    if img.width > max_width:
        ratio = max_width / img.width
        new_size = (max_width, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    return img


def verify_chapters(chapters, images_dir):
    """Verify all downloaded chapters for issues."""
    issues = []
    for ch in chapters:
        ch_num = ch['chapter']
        ch_dir = images_dir / f"ch_{ch_num}"
        pages = sorted(ch_dir.glob("page_*"))

        if len(pages) == 0:
            issues.append(f"Ch {ch_num}: NO PAGES")
            continue

        for i, url in enumerate(ch['images']):
            fname = url.split('/')[-1].lower()
            nums = re.findall(r'(\d{4})', fname)
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


def main():
    parser = argparse.ArgumentParser(description='Download and compile manga chapters')
    parser.add_argument('chapter_images', help='JSON file with chapter image URLs')
    parser.add_argument('--output-prefix', default='manga', help='Output filename prefix')
    parser.add_argument('--quality', type=int, default=75, help='JPEG quality (default: 75)')
    parser.add_argument('--max-width', type=int, default=1400, help='Max image width (default: 1400)')
    parser.add_argument('--images-dir', default=None, help='Directory for downloaded images')
    parser.add_argument('--skip-pdf', action='store_true', help='Skip PDF generation')
    args = parser.parse_args()

    chapter_file = Path(args.chapter_images)
    with open(chapter_file) as f:
        chapters = json.load(f)

    images_dir = Path(args.images_dir) if args.images_dir else chapter_file.parent / "images"
    images_dir.mkdir(exist_ok=True)

    output_dir = chapter_file.parent
    cbz_path = output_dir / f"{args.output_prefix}.cbz"
    pdf_path = output_dir / f"{args.output_prefix}.pdf"

    total_images = sum(len(ch['images']) for ch in chapters)
    print(f"{len(chapters)} chapters, {total_images} pages", file=sys.stderr)

    # Download
    print("\n=== DOWNLOADING ===", file=sys.stderr)
    downloaded = 0
    failed = 0
    for ch in chapters:
        ch_num = ch['chapter']
        ch_dir = images_dir / f"ch_{ch_num}"
        ch_dir.mkdir(exist_ok=True)
        print(f"Ch {ch_num}: {ch.get('title', '')} ({len(ch['images'])} pages)", file=sys.stderr)
        for i, img_url in enumerate(ch['images']):
            ext = img_url.rsplit('.', 1)[-1].split('?')[0]
            if ext not in ('png', 'jpg', 'jpeg', 'webp'):
                ext = 'png'
            filepath = ch_dir / f"page_{i:03d}.{ext}"
            if download_image(img_url, filepath):
                downloaded += 1
            else:
                failed += 1
            time.sleep(0.1)
    print(f"Download: {downloaded} ok, {failed} failed", file=sys.stderr)

    # Verify
    print("\n=== VERIFYING ===", file=sys.stderr)
    issues = verify_chapters(chapters, images_dir)
    if issues:
        print(f"{len(issues)} issues found:", file=sys.stderr)
        for i in issues:
            print(f"  !! {i}", file=sys.stderr)
    else:
        print("All chapters verified OK", file=sys.stderr)

    # Compile CBZ
    print("\n=== COMPILING CBZ ===", file=sys.stderr)
    page_num = 0
    all_images = []

    with zipfile.ZipFile(str(cbz_path), 'w', zipfile.ZIP_STORED) as zf:
        for ch in chapters:
            ch_dir = images_dir / f"ch_{ch['chapter']}"
            pages = sorted(ch_dir.glob("page_*"))
            for page_path in pages:
                try:
                    img = optimize_image(page_path, args.max_width)
                    buf = io.BytesIO()
                    img.save(buf, format='JPEG', quality=args.quality, optimize=True)
                    zf.writestr(f"{page_num:05d}.jpg", buf.getvalue())
                    all_images.append(img)
                    page_num += 1
                except Exception as e:
                    print(f"  Error: {page_path}: {e}", file=sys.stderr)

    cbz_mb = cbz_path.stat().st_size / (1024 * 1024)
    print(f"CBZ: {cbz_path.name} — {cbz_mb:.0f} MB, {page_num} pages", file=sys.stderr)

    # Compile PDF
    if not args.skip_pdf and all_images:
        print("Creating PDF...", file=sys.stderr)
        all_images[0].save(
            str(pdf_path), "PDF",
            save_all=True, append_images=all_images[1:],
            quality=args.quality, optimize=True,
        )
        pdf_mb = pdf_path.stat().st_size / (1024 * 1024)
        print(f"PDF: {pdf_path.name} — {pdf_mb:.0f} MB, {len(all_images)} pages", file=sys.stderr)

    # Final verification of CBZ
    print("\n=== CBZ INTEGRITY CHECK ===", file=sys.stderr)
    with zipfile.ZipFile(str(cbz_path)) as zf:
        cbz_files = sorted(f for f in zf.namelist() if f.endswith('.jpg'))
        for i, f in enumerate(cbz_files):
            if f != f"{i:05d}.jpg":
                print(f"  !! Naming gap at position {i}: {f}", file=sys.stderr)
        bad = [f for f in cbz_files if len(zf.read(f)) < 10000]
        if bad:
            print(f"  !! {len(bad)} corrupt pages in CBZ", file=sys.stderr)
        else:
            print(f"CBZ verified: {len(cbz_files)} pages, no issues", file=sys.stderr)

    print("\nDone!", file=sys.stderr)


if __name__ == '__main__':
    main()

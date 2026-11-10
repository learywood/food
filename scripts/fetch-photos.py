#!/usr/bin/env python3
"""Fetch cover photos (og:image) for each recipe's Source URL.

Saves images to docs/img/<slug>.<ext> and records results in
scripts/photo-cache.json, so rebuilds only fetch new or changed URLs.
Recipes without a reachable image get null (the site shows a placeholder).

Usage:
    python scripts/fetch-photos.py [--force]   # --force refetches everything
"""

import html as htmlmod
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(REPO, "recipes")
IMG_DIR = os.path.join(REPO, "docs", "img")
CACHE_PATH = os.path.join(REPO, "scripts", "photo-cache.json")

UA = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/145.0 Safari/537.36"
    )
}
EXT_BY_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "image/avif": ".avif",
}
MAX_BYTES = 6_000_000
MIN_BYTES = 2_000


def recipe_source_urls():
    """{slug: source url or None} for every recipe."""
    out = {}
    for fn in sorted(os.listdir(RECIPES_DIR)):
        if not fn.endswith(".md"):
            continue
        slug = fn[:-3]
        with open(os.path.join(RECIPES_DIR, fn), encoding="utf-8") as f:
            text = f.read()
        url = None
        m = re.search(r"^## Source\s*\n+(.*?)(?=^## |\Z)", text, re.M | re.S)
        if m:
            link = re.search(r"\((https?://[^)]+)\)", m.group(1))
            if link:
                url = link.group(1).strip()
        if not url:
            link = re.search(r"\((https?://[^)]+)\)", text)
            if link:
                url = link.group(1).strip()
        out[slug] = url
    return out


def extract_og_image(page_html, page_url):
    for tag in re.findall(r"<meta\s+([^>]+)>", page_html, re.I):
        attrs = dict(re.findall(r"(\w+)=[\"']([^\"']*)[\"']", tag))
        key = (attrs.get("property") or attrs.get("name") or "").lower()
        if key in ("og:image", "twitter:image"):
            val = htmlmod.unescape(attrs.get("content", "")).strip()
            if val and not val.startswith("data:"):
                return urljoin(page_url, val)
    m = re.search(
        r"<link[^>]+rel=[\"']image_src[\"'][^>]*>", page_html, re.I
    )
    if m:
        href = re.search(r"href=[\"']([^\"']+)[\"']", m.group(0), re.I)
        if href:
            return urljoin(page_url, htmlmod.unescape(href.group(1)))
    return None


def fetch_page(url):
    req = Request(url, headers=UA)
    with urlopen(req, timeout=20) as r:
        if "html" not in r.headers.get("Content-Type", ""):
            return None
        return r.read(400_000).decode("utf-8", "replace")


def download_image(img_url):
    req = Request(img_url, headers=UA)
    with urlopen(req, timeout=30) as r:
        ctype = r.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if not ctype.startswith("image/") or "svg" in ctype:
            return None, None
        data = r.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES or len(data) < MIN_BYTES:
            return None, None
    return data, ctype


def process(args):
    slug, url, cached = args
    if not url:
        return slug, url, None, "no-url"
    hit = cached.get(url)
    if hit and hit.get("photo"):
        photo = hit["photo"]
        if photo.startswith("http") or os.path.exists(
            os.path.join(REPO, "docs", photo)
        ):
            return slug, url, photo, "cache"
    try:
        page = fetch_page(url)
    except Exception:
        return slug, url, None, "fetch-fail"
    if not page:
        return slug, url, None, "no-html"
    img_url = extract_og_image(page, url)
    if not img_url:
        return slug, url, None, "no-image"
    try:
        data, ctype = download_image(img_url)
    except Exception:
        data, ctype = None, None
    if not data:
        return slug, url, img_url, "remote"  # hotlink fallback
    ext = EXT_BY_TYPE.get(ctype, ".jpg")
    filename = "img/%s%s" % (slug, ext)
    with open(os.path.join(REPO, "docs", filename), "wb") as f:
        f.write(data)
    return slug, url, filename, "ok"


def main():
    force = "--force" in sys.argv
    os.makedirs(IMG_DIR, exist_ok=True)
    cached = {}
    if os.path.exists(CACHE_PATH) and not force:
        with open(CACHE_PATH, encoding="utf-8") as f:
            cached = json.load(f)

    urls = recipe_source_urls()
    print("recipes=%d cached=%d" % (len(urls), len(cached)))
    jobs = [(slug, url, cached) for slug, url in urls.items()]

    results = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for slug, url, photo, how in pool.map(process, jobs):
            results[slug] = (url, photo)
            print("%-8s %-50s %s" % (how, slug, photo or url or "-"))

    new_cache = dict(cached)
    for slug, (url, photo) in results.items():
        if url:
            new_cache[url] = {"photo": photo, "slug": slug}
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(new_cache, f, indent=2, sort_keys=True)

    ok = sum(1 for _, p in results.values() if p and not p.startswith("http"))
    remote = sum(1 for _, p in results.values() if p and p.startswith("http"))
    print("local=%d remote=%d none=%d" % (ok, remote, len(results) - ok - remote))


if __name__ == "__main__":
    main()

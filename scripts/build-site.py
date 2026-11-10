#!/usr/bin/env python3
"""Build docs/data.json from recipes/*.md + photo cache.

Usage:  python scripts/build-site.py
"""

import json
import os
import re

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RECIPES_DIR = os.path.join(REPO, "recipes")
DOCS_DIR = os.path.join(REPO, "docs")
CACHE_PATH = os.path.join(REPO, "scripts", "photo-cache.json")


def parse_recipe(slug):
    with open(os.path.join(RECIPES_DIR, slug + ".md"), encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()

    title = ""
    for ln in lines:
        if ln.startswith("# "):
            title = ln[2:].strip()
            break

    meta_raw = ""
    meta = {}
    for i, ln in enumerate(lines):
        if ln.startswith("**Serves:**"):
            j = i
            while j < len(lines) and lines[j].strip():
                meta_raw += lines[j].strip() + " "
                j += 1
            break
    for m in re.finditer(r"\*\*(\w+):\*\*\s*([^*\u00b7]+?)(?=\s*(?:\*\*|\u00b7|$))", meta_raw):
        meta[m.group(1).lower()] = " ".join(m.group(2).split())

    sections = {}
    current, buf = None, []
    for ln in lines:
        if ln.startswith("## "):
            if current:
                sections[current] = buf
            current = ln[3:].strip().lower()
            buf = []
        elif current is not None:
            buf.append(ln)
    if current:
        sections[current] = buf

    def bullets(key):
        out = []
        for ln in sections.get(key, []):
            s = ln.strip()
            if s.startswith("- "):
                out.append(s[2:].strip())
        return out

    def numbered(key):
        out = []
        for ln in sections.get(key, []):
            s = ln.strip()
            m = re.match(r"^\d+[.)]\s+(.*\S)\s*$", s)
            if m:
                out.append(m.group(1))
            elif s.startswith("> "):
                out.append(s[2:])
        return out

    phases = {}
    ingredients, method = [], []
    for key in sections:
        if key.startswith("phase"):
            items = bullets(key)
            steps = numbered(key)
            if key.startswith("phase 0"):
                phases["prep"] = [re.sub(r"^\*\*(.+?)\*\*", r"\1:", s)
                                  for s in items]
            elif key.startswith("phase 1"):
                ingredients = items
            elif key.startswith("phase 2"):
                method = steps or items
        elif key == "ingredients":
            ingredients = bullets(key)
        elif key == "method":
            method = numbered(key) or bullets(key)

    trial_entries = []
    trial_to_try = []
    log = sections.get("trial log", [])
    entry, entry_body = None, []
    to_try_mode = False
    for ln in log:
        s = ln.strip()
        if s.startswith("### "):
            if entry:
                trial_entries.append({"title": entry, "lines": entry_body})
            entry, entry_body = s[4:].strip(), []
            to_try_mode = entry.lower().startswith("to try")
        elif s.startswith("- ") and entry:
            entry_body.append(s[2:].strip())
        elif to_try_mode and entry:
            entry_body.append(s)
    if entry:
        if to_try_mode:
            trial_to_try = [b for b in entry_body if b]
        else:
            trial_entries.append({"title": entry, "lines": entry_body})

    source = None
    for ln in sections.get("source", []):
        m = re.search(r"\((https?://[^)]+)\)", ln)
        if m:
            source = m.group(1)
            break
    if not source:
        m = re.search(r"\((https?://[^)]+)\)", text)
        if m:
            source = m.group(1)

    return {
        "slug": slug,
        "title": title,
        "meta": meta,
        "prep": phases.get("prep", []),
        "ingredients": ingredients,
        "method": method,
        "notes": bullets("notes"),
        "trials": trial_entries,
        "to_try": trial_to_try,
        "source": source,
    }


def main():
    cache = {}
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            cache = json.load(f)

    slugs = sorted(fn[:-3] for fn in os.listdir(RECIPES_DIR) if fn.endswith(".md"))
    recipes = []
    for slug in slugs:
        r = parse_recipe(slug)
        n_trials = len(r["trials"])
        trial_txt = " ".join(
            t["title"] + " " + " ".join(t["lines"]) for t in r["trials"]
        )
        trial_txt += " " + " ".join(r["to_try"])
        if "(trial)" in json.dumps({"m": r["meta"], "i": r["ingredients"],
                                    "d": r["method"]}, ensure_ascii=False):
            status = "trial"
        elif n_trials > 0 or r["to_try"]:
            status = "trial" if re.search(r"untested|retest|to try",
                                          trial_txt, re.I) else "tested"
        else:
            status = "stable"
        r["status"] = status
        photo = None
        for url, hit in cache.items():
            if isinstance(hit, dict) and hit.get("slug") == slug and hit.get("photo"):
                photo = hit["photo"]
                break
        r["photo"] = photo
        recipes.append(r)

    os.makedirs(DOCS_DIR, exist_ok=True)
    with open(os.path.join(DOCS_DIR, "data.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": __import__("datetime").date.today().isoformat(),
                   "count": len(recipes), "recipes": recipes}, f, ensure_ascii=False)
    print("wrote docs/data.json with %d recipes" % len(recipes))


if __name__ == "__main__":
    main()

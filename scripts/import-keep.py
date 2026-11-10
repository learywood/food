#!/usr/bin/env python3
"""Import Google Keep recipes (Google Takeout *.json) into recipes/*.md.

Reads the Takeout Keep folder directly -- no need to copy anything into the repo.
Default is a dry run: prints what would happen without writing files.

Usage:
    python scripts/import-keep.py --keep-dir <path-to-Takeout/Keep> [--write]

Decisions (see AGENTS.md "Importing from Google Keep"):
    - URL-only notes are imported as stubs (to-try list).
    - "cocktail" label included alongside "Recipe".
    - Photo attachments are NOT copied; the note is still imported.
    - Existing recipes/<name>.md files are never overwritten.
    - A note whose source URL already appears in an existing recipe is skipped
      (e.g. the leek-pie Keep note this repo was built from).
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

URL_RE = re.compile(r"^https?://\S+$")
HASHTAG_RE = re.compile(r"^#\w+\s*$")
SECTION_ING = re.compile(r"^\s*ingredients?\s*:?\s*$", re.IGNORECASE)
SECTION_MET = re.compile(
    r"^\s*(process|method|directions?|instructions?|preparation|steps?)\s*:?\s*$",
    re.IGNORECASE,
)
DASH_SEP = re.compile(r"^-{5,}\s*$")
NUMBERED = re.compile(r"^(\d+)[.)]\s+(.*\S)\s*$")
BULLET = re.compile(r"^[-*\u2022+]\s+")
QTY = re.compile(
    r"^\s*(\d|\u00bc|\u00bd|\u00be|\u2153|\u2154|\u215b|\u215c|\u215d|\u215e"
    r"|half\b|one\b|two\b|three\b|four\b|a\b|an\b|few\b|some\b"
    r"|dash\b|sprig\b|squeeze\b|shot\b|drizzle\b)",
    re.IGNORECASE,
)
SEPARATOR_ITEM = re.compile(r"^-+\s*(.+?)\s*-+$")
DROP_SLUG_TOKENS = {"recipe", "recipes", "html", "htm"}


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or "untitled"


def title_from_slug(url):
    """Derive 'Gazpacho Andaluz' from '.../gazpacho-andaluz-841.html'."""
    path = urlparse(url).path
    seg = ""
    for part in reversed([p for p in path.split("/") if p]):
        seg = unquote(part)
        break
    seg = re.sub(r"\.(html?|php|aspx?)$", "", seg, flags=re.IGNORECASE)
    words = [w for w in re.split(r"[-_]+", seg) if w]
    words = [w for w in words if not w.isdigit() and w.lower() not in DROP_SLUG_TOKENS]
    if not words:
        return "Untitled"
    return " ".join(w.capitalize() for w in words)


def clean_title(title, fallback_url):
    t = (title or "").strip()
    # A bare app/site name ('Pinterest') is the autofill default, not a title.
    if t.lower() in {"pinterest"}:
        t = ""
    # Strip recipe-site instruction prefixes like "How to Make X".
    t = re.sub(r"^(how to make|how to cook)\s+", "", t, flags=re.IGNORECASE)
    if not t:
        return title_from_slug(fallback_url) if fallback_url else "Untitled"
    if URL_RE.match(t):
        return title_from_slug(fallback_url or t)
    if " | " in t:
        t = t.split(" | ")[0]
    if " \u2014 " in t:
        t = t.split(" \u2014 ")[0]
    if " - " in t:
        head, tail = t.rsplit(" - ", 1)
        tail_words = tail.split()
        if (
            "." in tail
            or tail.lower().startswith("how to make")
            or head.strip().lower().endswith("recipe")
            or (
                len(tail_words) <= 4
                and len(head.split()) >= 3
                and not re.search(r"\d", tail)
            )
        ):
            t = head
    m = re.match(r"^(.+?)\s*:\s*[Hh]ow to .+$", t)
    if m:
        t = m.group(1)
    return t.strip() or "Untitled"


def note_date(note):
    usec = note.get("createdTimestampUsec") or note.get("userEditedTimestampUsec")
    if not usec:
        return "????-??-??"
    return datetime.fromtimestamp(int(usec) / 1e6, tz=timezone.utc).date().isoformat()


def existing_source_urls(recipes_dir):
    urls = set()
    if not os.path.isdir(recipes_dir):
        return urls
    for fn in os.listdir(recipes_dir):
        if not fn.endswith(".md"):
            continue
        with open(os.path.join(recipes_dir, fn), encoding="utf-8") as f:
            for m in re.finditer(r"\((https?://[^)]+)\)", f.read()):
                urls.add(normalize_url(m.group(1)))
    return urls


def normalize_url(url):
    url = url.strip().rstrip("/")
    url = re.sub(r"#.*$", "", url)
    return url


def split_text_body(lines):
    """Try to split lines into (ingredients, method). Returns None if no structure."""
    ings, mets, pre = [], [], []
    mode = None
    for raw in lines:
        s = raw.strip()
        if not s:
            continue
        if SECTION_ING.match(s):
            mode = "ing"
            continue
        if SECTION_MET.match(s):
            mode = "met"
            continue
        if DASH_SEP.match(s):
            if ings or pre:
                mode = "met"
            continue
        m = NUMBERED.match(s)
        if m:
            mode = "met"
            mets.append(m.group(2))
            continue
        s = BULLET.sub("", s)
        if mode == "ing":
            ings.append(s)
        elif mode == "met":
            mets.append(s)
        else:
            pre.append(s)
    if not ings and not mets:
        return None
    if not ings and mets:
        qty_pre = [BULLET.sub("", p) for p in pre if QTY.match(p)]
        if len(qty_pre) >= 2:
            ings = qty_pre
            rest = [p for p in pre if not QTY.match(p)]
            mets = rest + mets
    return ings, mets


def shape_text_note(title, text, source_url):
    """Returns (ingredients, method_lines, notes, stub)."""
    lines = [ln for ln in text.splitlines()]
    body = []
    for ln in lines:
        s = ln.strip()
        if not s or HASHTAG_RE.match(s) or URL_RE.match(s):
            continue
        body.append(s)
    if body and body[0].rstrip() == title.strip():
        body = body[1:]
    if not body:
        return [], [], [], True  # url-only stub
    split = split_text_body(body)
    if split:
        return split[0], split[1], [], False
    qty_lines = [BULLET.sub("", b) for b in body if QTY.match(b)]
    if len(qty_lines) >= 3:
        rest = [BULLET.sub("", b) for b in body if not QTY.match(b)]
        return qty_lines, rest, [], False
    if sum(len(b) for b in body) <= 120:
        notes = [BULLET.sub("", re.sub(r"^\+\s+", "", b)) for b in body]
        return [], [], notes, False
    return [], body, [], False  # verbatim method


def shape_list_note(items):
    """Checklist items -> (ingredients, source_urls_in_items)."""
    ings, urls = [], []
    for it in items:
        s = (it.get("text") or "").strip()
        if not s or HASHTAG_RE.match(s):
            continue
        if URL_RE.match(s):
            urls.append(normalize_url(s))
            continue
        m = SEPARATOR_ITEM.match(s)
        if m:
            ings.append("**%s**" % m.group(1).strip())
            continue
        ings.append(BULLET.sub("", s))
    return ings, urls


def render(title, serves, ingredients, method_lines, notes, trial_change,
           trial_date, source_url, verbatim):
    out = []
    out.append("# %s" % title)
    out.append("")
    out.append("**Serves:** %s" % serves)
    out.append("")
    out.append("## Ingredients")
    out.append("")
    if ingredients:
        out.extend("- %s" % i for i in ingredients)
    else:
        out.append("- (ingredients to add)")
    out.append("")
    out.append("## Method")
    out.append("")
    if method_lines:
        if verbatim:
            out.append("> Imported verbatim from Google Keep -- needs cleanup.")
            out.append(">")
            out.extend("> %s" % ln for ln in method_lines)
        else:
            numbered = any(NUMBERED.match(m) for m in method_lines)
            for i, m in enumerate(method_lines, 1):
                m = NUMBERED.sub(r"\2", m).strip() if NUMBERED.match(m) else m
                out.append("%d. %s" % (i, m))
    else:
        out.append("1. (method to add -- see source)")
    out.append("")
    if notes:
        out.append("## Notes")
        out.append("")
        out.extend("- %s" % n for n in notes)
        out.append("")
    out.append("## Trial log")
    out.append("")
    out.append("### %s -- imported from Keep" % trial_date)
    out.append("- Change: %s" % trial_change)
    out.append("- Result: untested")
    out.append("- Decision: retest")
    out.append("")
    if source_url:
        out.append("## Source")
        out.append("")
        out.append("[Original recipe](%s)" % source_url)
        out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description="Import Google Keep recipes into recipes/")
    ap.add_argument("--keep-dir", required=True, help="Path to Takeout/Keep folder")
    ap.add_argument("--labels", default="Recipe,cocktail",
                    help="Comma-separated Keep labels to import")
    ap.add_argument("--recipes-dir", default=os.path.join(REPO, "recipes"))
    ap.add_argument("--write", action="store_true",
                    help="Write files (default is dry run)")
    args = ap.parse_args()

    labels = {lb.strip().lower() for lb in args.labels.split(",") if lb.strip()}
    recipes_dir = args.recipes_dir
    existing_urls = existing_source_urls(recipes_dir)
    used_slugs = set()
    for fn in os.listdir(recipes_dir) if os.path.isdir(recipes_dir) else []:
        if fn.endswith(".md"):
            used_slugs.add(fn[:-3])

    notes = []
    for fn in sorted(os.listdir(args.keep_dir)):
        if not fn.endswith(".json"):
            continue
        with open(os.path.join(args.keep_dir, fn), encoding="utf-8") as f:
            try:
                note = json.load(f)
            except json.JSONDecodeError:
                print("UNREADABLE  %s" % fn)
                continue
        note_labels = {(lb.get("name") or "").lower() for lb in note.get("labels", [])}
        if note.get("isTrashed") or not (note_labels & labels):
            continue
        notes.append((fn, note))

    rows = []
    photo_count = 0
    for fn, note in notes:
        annots = [a for a in note.get("annotations", [])
                  if a.get("source") == "WEBLINK" and a.get("url")]
        annot_url = normalize_url(annots[0]["url"]) if annots else None
        annot_title = (annots[0].get("title") or "").strip() if annots else ""
        host = urlparse(annots[0]["url"]).netloc if annots else "-"
        if note.get("attachments"):
            photo_count += 1
        date = note_date(note)

        if note.get("listContent"):
            ings, item_urls = shape_list_note(note["listContent"])
            src = annot_url or (item_urls[0] if item_urls else None)
            title = clean_title(note.get("title"), src)
            change = "initial import from Keep (checklist, untested)"
            if not ings and not src:
                rows.append(("SKIP-empty", "-", (note.get("title") or fn), "checklist", host))
                continue
            rows.append(("CREATE", title, ings, [], [], change, date, src, False, host, fn))
        else:
            text = note.get("textContent") or ""
            src = annot_url
            if not src:
                for ln in text.splitlines():
                    if URL_RE.match(ln.strip()):
                        src = normalize_url(ln.strip())
                        break
            title = clean_title(note.get("title"), src)
            if title in ("Untitled", "Pinterest") and annot_title:
                title = clean_title(annot_title, src)
            if title == "Untitled" and annot_title.lower() == "pinterest":
                pass  # genuinely untitled; flagged NEEDS-TITLE
            ings, mets, nts, stub = shape_text_note(title, text, src)
            change = "initial import from Keep (%s, untested)" % (
                "link only" if stub else "note")
            # Verbatim blockquote only when no structure was found.
            verb = bool(mets) and not ings and not nts and not stub
            rows.append(("CREATE", title, ings, mets, nts, change, date, src, verb, host, fn))

    # When several notes share one source URL they are the same saved recipe:
    # keep the richest note (full text > checklist > short note > stub).
    def richness(row):
        (_, title, ings, mets, nts, change, date, src, verb, host, fn) = row
        if verb and not ings and not mets and not nts:
            return 0
        return len(ings) + len(mets) + len(nts)

    # Group CREATE rows by source URL using their index in `rows`.
    url_groups = {}
    for i, row in enumerate(rows):
        if row[0] != "CREATE" or not row[7]:
            continue
        url_groups.setdefault(normalize_url(row[7]), []).append(i)
    for url, idxs in url_groups.items():
        if len(idxs) < 2:
            continue
        ordered = sorted(idxs, key=lambda i: (-richness(rows[i]), rows[i][10]))
        for loser_i in ordered[1:]:
            loser = rows[loser_i]
            rows[loser_i] = ("SKIP-dupe-url", slugify(loser[1]) + ".md",
                             loser[1], "", loser[9], loser[10])

    # resolve filenames, skip existing + dupe urls
    seen_slugs = set()
    final = []
    for row in rows:
        if row[0] != "CREATE":
            final.append(row)
            continue
        (_, title, ings, mets, nts, change, date, src, verb, host, fn) = row
        needs_title = title == "Untitled"
        slug = slugify(title)
        base, n = slug, 2
        while slug in used_slugs or slug in seen_slugs:
            slug = "%s-%d" % (base, n)
            n += 1
        target = os.path.join(recipes_dir, slug + ".md")
        if os.path.exists(target):
            final.append(("SKIP-exists", slug + ".md", title, "", host, fn))
            continue
        if src and normalize_url(src) in existing_urls:
            final.append(("SKIP-dupe-url", slug + ".md", title, "", host, fn))
            continue
        seen_slugs.add(slug)
        if src:
            existing_urls.add(normalize_url(src))
        final.append(("CREATE", slug + ".md", title, ings, mets, nts, change,
                      date, src, verb, host, needs_title, fn))

    created = [r for r in final if r[0] == "CREATE"]
    skipped = [r for r in final if r[0] != "CREATE"]

    print("DRY-RUN -- add --write to create files" if not args.write else "WRITING FILES")
    print("notes matching labels: %d" % len(notes))
    print("")
    for r in created:
        (_, fn, title, ings, mets, nts, change, date, src, verb, host, needs_title, _) = r
        flag = "  NEEDS-TITLE" if needs_title else ""
        body = "%ding/%dmethod/%dnotes" % (len(ings), len(mets), len(nts))
        print("CREATE  %-55s | %-45s | %-16s | %s%s" % (fn, title[:45], body, host, flag))
    for r in skipped:
        print("%-11s %-55s | %-45s | %s" % (r[0], r[1], r[2][:45], r[4]))
    print("")
    print("create=%d skipped=%d (photo attachments ignored: %d notes had them)" % (
        len(created), len(skipped), photo_count))

    if args.write:
        os.makedirs(recipes_dir, exist_ok=True)
        for r in created:
            (_, fn, title, ings, mets, nts, change, date, src, verb, _, _, _) = r
            content = render(title, "?", ings, mets, nts, change, date, src, verb)
            with open(os.path.join(recipes_dir, fn), "w", encoding="utf-8") as f:
                f.write(content)
        print("wrote %d files to %s" % (len(created), recipes_dir))


if __name__ == "__main__":
    sys.exit(main())

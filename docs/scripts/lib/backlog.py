#!/usr/bin/env python3
"""
backlog.py — shared parsing and validation rules for docs/backlog.md.

SINGLE SOURCE of the backlog's structural rules: imported by `sync-backlog-to-issues.py` (which
opens the GitHub issues), by `backlog-lint.py` (which validates in CI) and by
`generate-roadmap.py`. No regex or convention is duplicated between the three.

A backlog item looks like this:

    ### `stable-id` — Title
    - **status**: open|done          (default: open)
    - **priority**: low|medium|high  (optional)
    - **labels**: a, b, c            (optional)
    - **milestone**: <title>         (optional)
    - **owner**: <username>          (optional)
    - **ref**: <link>                (optional)

    prose … (becomes the issue body)

`parse_backlog()` is PURE (no sys.exit): it returns the list of items. Besides the fields the sync
uses, every item carries two technical keys for the linter:
  - `_line`      : 1-based line number of the `### ...` heading
  - `_meta_seen` : list of {key, line, value} for the `- **k**: v` bullets found in the *meta
                   block* (the run of bullets right below the heading, before the first line of
                   prose) — that is what lets the linter spot mistyped keys.
"""
import re

# --- structural regexes (single source) ------------------------------------------------
# item: "### `id` — Title"  (id in backticks; the — or - separator is optional)
ITEM_RE = re.compile(r"^###\s+`([^`]+)`\s*[—\-]*\s*(.*)$")
META_RE = re.compile(r"^[-*]\s+\*\*(\w+)\*\*:\s*(.+)$")
FP_RE = re.compile(r"<!--\s*backlog-id:\s*([a-zA-Z0-9._-]+)")        # id (with or without | hash:)
HASH_RE = re.compile(r"backlog-id:\s*[\w.-]+\s*\|\s*hash:\s*([0-9a-f]+)")

# --- accepted vocabulary ---------------------------------------------------------------
KNOWN_META = {"status", "priority", "labels", "milestone", "owner", "ref"}
VALID_STATUS = {"open", "done"}
VALID_PRIORITY = {"low", "medium", "high"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")   # lowercase kebab-case


def _new_item(item_id, title, line):
    return {"id": item_id, "title": title,
            "labels": [], "status": "open", "priority": "", "ref": "", "owner": "",
            "milestone": "", "body": [], "_line": line, "_meta_seen": []}


def parse_backlog(path):
    """Parse docs/backlog.md → list of items (PURE, no sys.exit).

    A `- **k**: v` bullet with a known `k` sets the field; every other line (blank, prose,
    checklist, bullet with an unknown key) ends up in the body. Bullets seen in the initial meta
    block (until prose starts) are also recorded in `_meta_seen` so the linter can report typos.
    """
    items, cur, in_meta = [], None, False
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines()
    for i, ln in enumerate(lines, start=1):
        m = ITEM_RE.match(ln)
        if m:
            if cur:
                items.append(cur)
            cur = _new_item(m.group(1).strip(), m.group(2).strip(), i)
            in_meta = True
            continue
        if cur is None:
            continue
        if re.match(r"^#{1,3}\s", ln):   # a new (non-item) section closes the current item
            items.append(cur)
            cur, in_meta = None, False
            continue
        mm = META_RE.match(ln)
        if mm:
            k, v = mm.group(1).lower(), mm.group(2).strip()
            if in_meta:
                cur["_meta_seen"].append({"key": mm.group(1), "line": i, "value": v})
            if k == "labels":
                cur["labels"] = [x.strip().strip("`") for x in v.split(",") if x.strip()]
            elif k in ("status", "priority", "ref", "owner", "milestone"):
                cur[k] = v.strip().lstrip("@")
            else:
                cur["body"].append(ln)   # unknown key → body
        else:
            if ln.strip():               # first non-blank prose line → end of the meta block
                in_meta = False
            cur["body"].append(ln)
    if cur:
        items.append(cur)
    return items


def item_hash(item):
    """Stable hash of the synced content (title/labels/priority/ref/owner/milestone/body).
    Embedded in the issue's fingerprint: if it changes, the issue needs updating."""
    import hashlib
    canon = "\x1f".join([
        item["title"],
        ",".join(sorted(item["labels"])),
        item.get("priority", ""),
        item.get("ref", ""),
        item.get("owner", ""),
        item.get("milestone", ""),
        "\n".join(item["body"]).strip(),
    ])
    return hashlib.sha1(canon.encode("utf-8")).hexdigest()[:12]


def _norm_milestone(title):
    """Normalise a milestone title for the "same milestone?" check (case + collapsed spaces)."""
    return re.sub(r"\s+", " ", title).strip().casefold()


def lint(items):
    """Validate the parsed items. Returns (errors, warnings): two lists of formatted strings
    (with line numbers). A non-empty `errors` means the linter must exit non-zero."""
    errors, warnings = [], []

    # 1) duplicate ids (fatal: the sync itself would refuse them)
    by_id = {}
    for it in items:
        by_id.setdefault(it["id"], []).append(it["_line"])
    for iid, ls in by_id.items():
        if len(ls) > 1:
            errors.append(f"duplicate id `{iid}` (lines {', '.join(map(str, ls))})")

    for it in items:
        line, iid = it["_line"], it["id"]
        loc = f"line {line} [{iid}]"

        # 2) id format
        if not ID_RE.match(iid):
            errors.append(f"{loc}: invalid id (expected lowercase kebab-case `[a-z0-9._-]`)")

        # 3) non-empty title
        if not it["title"].strip():
            errors.append(f"{loc}: empty title")

        # 4) status / priority in the vocabulary
        if it["status"] and it["status"].lower() not in VALID_STATUS:
            errors.append(f"{loc}: status `{it['status']}` is not valid (expected {sorted(VALID_STATUS)})")
        if it["priority"] and it["priority"].lower() not in VALID_PRIORITY:
            errors.append(f"{loc}: priority `{it['priority']}` is not valid (expected {sorted(VALID_PRIORITY)})")

        # 5) unknown meta keys in the initial block (typos such as `- **lables**:`)
        for meta in it["_meta_seen"]:
            if meta["key"].lower() not in KNOWN_META:
                errors.append(f"line {meta['line']} [{iid}]: unknown meta key "
                              f"`{meta['key']}` (known: {sorted(KNOWN_META)}) — typo?")

        # 5b) the same meta key twice in one item: the last one wins and the first is lost in
        #     silence (usually a copy-pasted item). Happened while writing the first backlog.
        seen_keys = {}
        for meta in it["_meta_seen"]:
            seen_keys.setdefault(meta["key"].lower(), []).append(meta["line"])
        for k, ls in seen_keys.items():
            if len(ls) > 1:
                errors.append(f"{loc}: meta key `{k}` repeated (lines "
                              f"{', '.join(map(str, ls))}) — the last one wins")

    # 6) milestone titles must match character for character; flag case/space variants
    variants = {}
    for it in items:
        if it["milestone"]:
            variants.setdefault(_norm_milestone(it["milestone"]), set()).add(it["milestone"])
    for norm, raws in variants.items():
        if len(raws) > 1:
            warnings.append("milestone spelled in different ways (the same milestone?): "
                            + " · ".join(f"«{r}»" for r in sorted(raws))
                            + " → make the title identical (matched exactly)")

    return errors, warnings

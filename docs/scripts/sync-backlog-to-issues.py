#!/usr/bin/env python3
"""
sync-backlog-to-issues.py — sync docs/backlog.md → GitHub issues (IDEMPOTENT).

docs/backlog.md is the SINGLE source of truth. Every item has a stable `id`. For each item whose
status is not done the script guarantees an open issue; removed or `status: done` items close theirs.
Re-running never duplicates anything, thanks to the fingerprint hidden in the issue body:
    <!-- backlog-id: <id> | hash: <sha> -->
plus the `backlog-sync` label on every managed issue.

The matrix (idempotent):
  item open  + no issue                 → CREATE
  item open  + open issue, hash ==      → SKIP (already aligned)
  item open  + open issue, hash !=      → UPDATE (title/labels/body/milestone diverged)
  item open  + closed issue             → REOPEN (+ realign the content)
  item done/removed + open issue        → CLOSE (automatic comment + the reason from the backlog)

Milestones: an item may carry `- **milestone**: <title>`; the script looks the repository milestone
up by exact title and CREATES it if missing (idempotent), then assigns the issue. The milestone
title is part of the hash → changing or dropping it realigns the issue on the next sync. It never
removes a milestone assigned by hand when the item does not declare one.

Careful, GitHub replaces the whole label set on PATCH: the script UNIONS them with the labels
already on the issue, so labels added by hand survive.

Careful, GitHub's `/issues` listing includes pull requests: they are filtered out (the
`pull_request` key), otherwise a PR carrying the sync label would look like a phantom item and get
closed.

Auth: a token with `issues: write` on the repository.
  - $GITHUB_TOKEN (in Actions: `permissions: issues: write`) or $GH_TOKEN
  - or --token-file <path>

Default: --dry-run (prints the plan, writes NOTHING). Use --apply to actually run it.
With no token, --dry-run only lists the parsed items (it cannot compare with the existing issues).

Requires: stdlib only (urllib, json, re, argparse).
"""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import backlog as B   # noqa: E402  — shared parsing/rules (single source with backlog-lint.py)

DEFAULT_REPO = "Allan-Nava/Docker-FFmpeg-Nvenc"
SYNC_LABEL = "backlog-sync"

FP_RE = B.FP_RE
HASH_RE = B.HASH_RE
item_hash = B.item_hash


# ----------------------------------------------------------------------------- parsing
def parse_backlog(path):
    """Parse the backlog (via lib/backlog.py) and refuse duplicate ids (fatal for the sync)."""
    items = B.parse_backlog(path)
    counts = {}
    for it in items:
        counts[it["id"]] = counts.get(it["id"], 0) + 1
    dups = sorted(k for k, n in counts.items() if n > 1)
    if dups:
        sys.exit(f"ERROR: duplicate ids in backlog.md: {dups}")
    return items


def build_body(item, backlog_url):
    parts = []
    body = "\n".join(item["body"]).strip()
    if body:
        parts.append(body)
    meta = []
    if item["priority"]:
        meta.append(f"**Priority**: {item['priority']}")
    if item.get("owner"):
        meta.append(f"**Owner**: @{item['owner']}")
    if item["ref"]:
        meta.append(f"**Ref**: {item['ref']}")
    if meta:
        parts.append("\n".join(meta))
    parts.append(f"_Issue generated automatically from [`docs/backlog.md`]({backlog_url}) "
                 f"(id: `{item['id']}`). Do not edit the title here: edit the backlog._")
    parts.append(f"<!-- backlog-id: {item['id']} | hash: {item_hash(item)} -->")
    return "\n\n".join(parts)


def desired_labels(item, issue=None):
    """The label set to send to GitHub: the item's labels + `backlog-sync` + whatever is ALREADY on
    the issue. `PATCH /issues/:n` **replaces** the whole set (GitLab has `add_labels` instead), so
    without the union every sync would wipe the labels added by hand."""
    current = []
    if issue:
        current = [l["name"] if isinstance(l, dict) else l for l in (issue.get("labels") or [])]
    return sorted(set(current) | set(item["labels"]) | {SYNC_LABEL})


def is_issue(obj):
    """False for pull requests. `GET /issues` returns them alongside issues: without this filter a
    PR carrying the sync label would be a phantom item to CLOSE."""
    return "pull_request" not in obj


CHECKLIST_RE = re.compile(r"^[-*]\s*\[[ xX]\]")   # markdown checklist entry: - [ ] / - [x]


def close_note(item, max_len=700):
    """An excerpt of the item body to attach to the closing comment, so the issue carries the
    reason. Prefers the first *blockquote* (`> …`, the convention for a resolution note), otherwise
    the first block of prose (skipping checklists). None when the item was removed from the backlog
    (no body available) or the body is empty."""
    if not item:
        return None
    blocks, cur = [], []
    for ln in item.get("body", []):
        if ln.strip():
            cur.append(ln.strip())
        elif cur:
            blocks.append(cur); cur = []
    if cur:
        blocks.append(cur)
    if not blocks:
        return None
    chosen = next((b for b in blocks if all(l.startswith(">") for l in b)), None)   # 1) blockquote
    if chosen is None:
        chosen = next((b for b in blocks if not all(CHECKLIST_RE.match(l) for l in b)), None)  # 2) prosa
    if not chosen:
        return None
    text = " ".join(re.sub(r"^>\s*", "", l) for l in chosen).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip() + "…"
    return text or None


# ----------------------------------------------------------------------------- API
class GitHub:
    def __init__(self, base, token, repo):
        self.base = base.rstrip("/")
        self.token = token
        self.repo = repo
        self._milestone_cache = {}   # titolo → number

    def _req(self, method, path, params=None, data=None):
        url = f"{self.base}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(data).encode() if data is not None else None
        headers = {"Authorization": f"Bearer {self.token}",
                   "Accept": "application/vnd.github+json",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "User-Agent": "backlog-sync"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            if e.code == 410:
                sys.exit("ERROR 410: the issue tracker is disabled on this repository "
                         "(Settings ▸ General ▸ Features ▸ Issues). Enable it and retry.")
            if e.code == 403 and "issues" in path:
                sys.exit("ERROR 403 on issues: the token lacks write scope. "
                         "In Actions that means `permissions: issues: write`. "
                         f"Detail: {detail}")
            sys.exit(f"API ERROR {method} {path}: HTTP {e.code} — {detail}")

    def ensure_milestone(self, title):
        """Milestone title → number. Looked up on the repository; CREATED if missing
        (idempotent). Returns None when `title` is empty."""
        if not title:
            return None
        if title in self._milestone_cache:
            return self._milestone_cache[title]
        num, page = None, 1
        while num is None:
            data = self._req("GET", f"/repos/{self.repo}/milestones",
                             params={"state": "all", "per_page": 100, "page": page}) or []
            num = next((m["number"] for m in data if m.get("title") == title), None)
            if num is not None or len(data) < 100:
                break
            page += 1
        if num is None:
            print(f"      + GitHub milestone missing → CREATE «{title}»")
            res = self._req("POST", f"/repos/{self.repo}/milestones",
                            data={"title": title,
                                  "description": "Milestone managed from docs/backlog.md "
                                                 "(the items' `- **milestone**:` field)."})
            num = res["number"]
        self._milestone_cache[title] = num
        return num

    def list_sync_issues(self):
        """Issues (NOT pull requests) carrying the sync label, in any state."""
        out, page = [], 1
        while True:
            data = self._req("GET", f"/repos/{self.repo}/issues",
                             params={"labels": SYNC_LABEL, "state": "all",
                                     "per_page": 100, "page": page}) or []
            if not data:
                break
            out.extend(i for i in data if is_issue(i))
            if len(data) < 100:
                break
            page += 1
        return out

    def create_issue(self, title, body, labels, assignees=None, milestone=None):
        data = {"title": title, "body": body, "labels": labels}
        if assignees:
            data["assignees"] = assignees
        if milestone:
            data["milestone"] = milestone
        return self._req("POST", f"/repos/{self.repo}/issues", data=data)

    def update_issue(self, number, title, body, labels, assignees=None, milestone=None, state=None):
        # GitHub REPLACES the label set: `labels` must already be the desired union.
        data = {"title": title, "body": body, "labels": labels}
        if assignees:
            data["assignees"] = assignees
        if milestone:
            data["milestone"] = milestone
        if state:
            data["state"] = state
        return self._req("PATCH", f"/repos/{self.repo}/issues/{number}", data=data)

    def comment(self, number, body):
        return self._req("POST", f"/repos/{self.repo}/issues/{number}/comments",
                         data={"body": body})

    def set_state(self, number, state, reason=None):  # 'closed' | 'open'
        data = {"state": state}
        if reason:
            data["state_reason"] = reason
        return self._req("PATCH", f"/repos/{self.repo}/issues/{number}", data=data)


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser(description="Sync docs/backlog.md → GitHub issues (idempotent).")
    ap.add_argument("--backlog", default=os.path.join(HERE, "..", "backlog.md"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO,
                    help="owner/repo (default: $GITHUB_REPOSITORY or " + DEFAULT_REPO + ")")
    ap.add_argument("--token-file", help="file containing the token (alternative to $GITHUB_TOKEN)")
    ap.add_argument("--apply", action="store_true", help="actually run it (default: dry-run)")
    args = ap.parse_args()

    items = parse_backlog(os.path.normpath(args.backlog))
    desired = {it["id"]: it for it in items if it["status"].lower() != "done"}
    done_ids = {it["id"] for it in items if it["status"].lower() == "done"}
    items_by_id = {it["id"]: it for it in items}   # for the excerpt in the closing comment

    print(f"backlog: {len(items)} items total · {len(desired)} active (open) · {len(done_ids)} done")

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token and args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()

    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    backlog_url = f"{server}/{args.repo}/blob/main/docs/backlog.md"

    if not token:
        if args.apply:
            sys.exit("ERROR: --apply needs a token ($GITHUB_TOKEN or --token-file).")
        print("\nNo token → OFFLINE dry-run (no comparison with the existing issues).")
        print("  Items that would be guaranteed OPEN:")
        for it in desired.values():
            ms = f"  milestone=«{it['milestone']}»" if it.get("milestone") else ""
            print(f"      - [{it['id']}] {it['title']}  labels={sorted(set(it['labels'] + [SYNC_LABEL]))}{ms}")
        return 0

    gh = GitHub(base, token, args.repo)

    def milestone_for(it):
        """Resolve `- **milestone**:` → milestone number (creating it if missing). --apply only."""
        return gh.ensure_milestone(it.get("milestone", ""))

    def assignees_for(it):
        return [it["owner"]] if it.get("owner") else None

    existing = gh.list_sync_issues()
    by_fp = {}
    for iss in existing:
        m = FP_RE.search(iss.get("body") or "")
        if m:
            by_fp.setdefault(m.group(1), []).append(iss)

    to_create, to_update, to_reopen, to_close, skip = [], [], [], [], []
    for iid, it in desired.items():
        matches = by_fp.get(iid, [])
        opened = [i for i in matches if i["state"] == "open"]
        if opened:
            iss = opened[0]
            hm = HASH_RE.search(iss.get("body") or "")
            if (hm.group(1) if hm else None) != item_hash(it):   # content diverged → realign
                to_update.append((it, iss))
            else:
                skip.append((it, iss))
        elif matches:                       # exists but closed → reopen
            to_reopen.append((it, matches[0]))
        else:
            to_create.append(it)
    for iss in existing:
        m = FP_RE.search(iss.get("body") or "")
        fp = m.group(1) if m else None
        if iss["state"] == "open" and (fp is None or fp not in desired):
            to_close.append(iss)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n=== Sync plan ({mode}) on {args.repo} ===")
    print(f"  CREATE : {len(to_create)}")
    print(f"  UPDATE : {len(to_update)}")
    print(f"  REOPEN : {len(to_reopen)}"
          + ("   DRIFT: closed in the UI but still `status: open` in the backlog" if to_reopen else ""))
    print(f"  CLOSE  : {len(to_close)}")
    print(f"  SKIP   : {len(skip)} (already aligned)\n")

    def ms_tag(it):
        return f"  milestone=«{it['milestone']}»" if it.get("milestone") else ""

    for it in to_create:
        print(f"  + CREATE [{it['id']}] {it['title']}{ms_tag(it)}")
        if args.apply:
            res = gh.create_issue(it["title"], build_body(it, backlog_url), desired_labels(it),
                                  assignees=assignees_for(it), milestone=milestone_for(it))
            print(f"      → #{res['number']} {res['html_url']}")
    for it, iss in to_update:
        print(f"  ~ UPDATE #{iss['number']} [{it['id']}] {it['title']}{ms_tag(it)}")
        if args.apply:
            gh.update_issue(iss["number"], it["title"], build_body(it, backlog_url),
                            desired_labels(it, iss), assignees=assignees_for(it),
                            milestone=milestone_for(it))
    for it, iss in to_reopen:
        print(f"  ^ REOPEN #{iss['number']} [{it['id']}] {it['title']}"
              "   DRIFT: it was closed in the UI but `status: open` in the backlog → reopened "
              "(the backlog decides)")
        if args.apply:
            gh.update_issue(iss["number"], it["title"], build_body(it, backlog_url),
                            desired_labels(it, iss), assignees=assignees_for(it),
                            milestone=milestone_for(it), state="open")
            gh.comment(iss["number"],
                       f"Reopened: item `{it['id']}` is active again in `docs/backlog.md`. "
                       "If you really meant to close it, set `status: done` on the item "
                       "(do not just close it in the UI).")
    for iss in to_close:
        m = FP_RE.search(iss.get("body") or "")
        fp = m.group(1) if m else "?"
        note = close_note(items_by_id.get(fp))
        print(f"  - CLOSE  #{iss['number']} (backlog-id: {fp}) {iss['title']}")
        if note:
            print(f"      excerpt: {note if len(note) <= 120 else note[:120] + '…'}")
        if args.apply:
            body = ("Closed automatically: the item is no longer active "
                    "(removed or `status: done`) in `docs/backlog.md`.")
            if note:
                body += f"\n\n**State/reason from the backlog:**\n\n> {note}"
            gh.comment(iss["number"], body)
            gh.set_state(iss["number"], "closed", reason="completed")
    for it, iss in skip:
        print(f"  = SKIP   #{iss['number']} [{it['id']}]")

    if not args.apply:
        print("\n(DRY-RUN: nothing changed. Re-run with --apply to apply it.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

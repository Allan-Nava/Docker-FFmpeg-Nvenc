#!/usr/bin/env python3
"""
sync-backlog-to-issues.py — sincronizza docs/backlog.md → issue GitHub (IDEMPOTENTE).

Sorgente di verita UNICA: docs/backlog.md. Ogni item ha un `id` stabile. Per ogni item con
status != done lo script garantisce una issue aperta; gli item rimossi o `status: done` chiudono
la issue corrispondente. Re-run senza duplicati grazie al fingerprint nascosto nel corpo issue:
    <!-- backlog-id: <id> | hash: <sha> -->
+ label `backlog-sync` su tutte le issue gestite.

Matrice (idempotente):
  item open  + nessuna issue            → CREATE
  item open  + issue aperta, hash ==    → SKIP (gia allineata)
  item open  + issue aperta, hash !=    → UPDATE (titolo/labels/corpo/milestone divergenti)
  item open  + issue chiusa             → REOPEN (+ riallinea contenuto)
  item done/rimosso + issue aperta      → CLOSE (commento auto + estratto del corpo dal backlog)

Milestone: l'item puo avere `- **milestone**: <titolo>`; lo script cerca la milestone del repo
per titolo esatto e la CREA se manca (idempotente), poi assegna la issue. Il titolo milestone e
incluso nell'hash → cambiarlo/toglierlo riallinea la issue al prossimo sync. Non rimuove mai una
milestone assegnata a mano se l'item non ne dichiara una.

⚠️ GitHub sostituisce l'intero set di label su PATCH: lo script fa l'UNIONE con le label gia
presenti sulla issue, cosi le label aggiunte a mano non vengono perse.

⚠️ La lista `/issues` di GitHub include anche le pull request: vengono filtrate (chiave
`pull_request`), altrimenti una PR con la label del sync verrebbe "chiusa" come item fantasma.

Auth: token con scope `issues: write` sul repo.
  - $GITHUB_TOKEN (in Actions: `permissions: issues: write`) oppure $GH_TOKEN
  - oppure --token-file <path>

Default: --dry-run (mostra il piano, NON scrive). Usa --apply per eseguire davvero.
Senza token in --dry-run: mostra solo gli item parsati (non puo confrontare con le issue esistenti).

Requires: solo stdlib (urllib, json, re, argparse).
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
import backlog as B   # noqa: E402  — parsing/regole condivisi (fonte unica con backlog-lint.py)

DEFAULT_REPO = "Allan-Nava/Docker-FFmpeg-Nvenc"
SYNC_LABEL = "backlog-sync"

FP_RE = B.FP_RE
HASH_RE = B.HASH_RE
item_hash = B.item_hash


# ----------------------------------------------------------------------------- parsing
def parse_backlog(path):
    """Parsa il backlog (via lib/backlog.py) e rifiuta gli id duplicati (fatale per il sync)."""
    items = B.parse_backlog(path)
    counts = {}
    for it in items:
        counts[it["id"]] = counts.get(it["id"], 0) + 1
    dups = sorted(k for k, n in counts.items() if n > 1)
    if dups:
        sys.exit(f"ERRORE: id duplicati in backlog.md: {dups}")
    return items


def build_body(item, backlog_url):
    parts = []
    body = "\n".join(item["body"]).strip()
    if body:
        parts.append(body)
    meta = []
    if item["priority"]:
        meta.append(f"**Priorita**: {item['priority']}")
    if item.get("owner"):
        meta.append(f"**Owner**: @{item['owner']}")
    if item["ref"]:
        meta.append(f"**Ref**: {item['ref']}")
    if meta:
        parts.append("\n".join(meta))
    parts.append(f"_Issue generata automaticamente da [`docs/backlog.md`]({backlog_url}) "
                 f"(id: `{item['id']}`). Non editare il titolo a mano: modifica il backlog._")
    parts.append(f"<!-- backlog-id: {item['id']} | hash: {item_hash(item)} -->")
    return "\n\n".join(parts)


CHECKLIST_RE = re.compile(r"^[-*]\s*\[[ xX]\]")   # voce checklist markdown: - [ ] / - [x]


def close_note(item, max_len=700):
    """Estratto del corpo dell'item da allegare al commento di chiusura, per dare contesto/motivo.
    Preferisce il primo blocco *blockquote* (`> …`, per convenzione nota di risoluzione),
    altrimenti il primo blocco di prosa (saltando le checklist). None se l'item e stato rimosso
    dal backlog (nessun corpo disponibile) o il corpo e vuoto."""
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
                sys.exit("ERRORE 410: l'Issue Tracker e disabilitato sul repo "
                         "(Settings ▸ General ▸ Features ▸ Issues). Abilitalo e riprova.")
            if e.code == 403 and "issues" in path:
                sys.exit("ERRORE 403 sulle issue: al token manca lo scope di scrittura. "
                         "In Actions serve `permissions: issues: write`. "
                         f"Dettaglio: {detail}")
            sys.exit(f"ERRORE API {method} {path}: HTTP {e.code} — {detail}")

    def ensure_milestone(self, title):
        """Titolo milestone → number. La cerca sul repo; se non esiste la CREA (idempotente).
        Ritorna None se `title` e vuoto."""
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
            print(f"      + milestone GitHub mancante → CREATE «{title}»")
            res = self._req("POST", f"/repos/{self.repo}/milestones",
                            data={"title": title,
                                  "description": "Milestone gestita da docs/backlog.md "
                                                 "(campo `- **milestone**:` degli item)."})
            num = res["number"]
        self._milestone_cache[title] = num
        return num

    def list_sync_issues(self):
        """Issue (NON pull request) con la label del sync, in qualunque stato."""
        out, page = [], 1
        while True:
            data = self._req("GET", f"/repos/{self.repo}/issues",
                             params={"labels": SYNC_LABEL, "state": "all",
                                     "per_page": 100, "page": page}) or []
            if not data:
                break
            out.extend(i for i in data if "pull_request" not in i)
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
        # GitHub SOSTITUISCE il set di label: `labels` deve essere gia l'unione desiderata.
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
    ap = argparse.ArgumentParser(description="Sincronizza docs/backlog.md → issue GitHub (idempotente).")
    ap.add_argument("--backlog", default=os.path.join(HERE, "..", "backlog.md"))
    ap.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY") or DEFAULT_REPO,
                    help="owner/repo (default: $GITHUB_REPOSITORY o " + DEFAULT_REPO + ")")
    ap.add_argument("--token-file", help="file con il token (alternativa a $GITHUB_TOKEN)")
    ap.add_argument("--apply", action="store_true", help="esegue davvero (default: dry-run)")
    args = ap.parse_args()

    items = parse_backlog(os.path.normpath(args.backlog))
    desired = {it["id"]: it for it in items if it["status"].lower() != "done"}
    done_ids = {it["id"] for it in items if it["status"].lower() == "done"}
    items_by_id = {it["id"]: it for it in items}   # per l'estratto nel commento di chiusura

    print(f"backlog: {len(items)} item totali · {len(desired)} attivi (open) · {len(done_ids)} done")

    token = (os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or "").strip()
    if not token and args.token_file:
        with open(args.token_file) as f:
            token = f.read().strip()

    base = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    backlog_url = f"{server}/{args.repo}/blob/main/docs/backlog.md"

    if not token:
        if args.apply:
            sys.exit("ERRORE: --apply richiede un token ($GITHUB_TOKEN o --token-file).")
        print("\nNessun token → dry-run OFFLINE (non confronto con le issue esistenti).")
        print("  Item che verrebbero garantiti OPEN:")
        for it in desired.values():
            ms = f"  milestone=«{it['milestone']}»" if it.get("milestone") else ""
            print(f"      - [{it['id']}] {it['title']}  labels={sorted(set(it['labels'] + [SYNC_LABEL]))}{ms}")
        return 0

    gh = GitHub(base, token, args.repo)

    def milestone_for(it):
        """Risolve `- **milestone**:` → milestone number (creandola se manca). Solo in --apply."""
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
            if (hm.group(1) if hm else None) != item_hash(it):   # contenuto divergente → allinea
                to_update.append((it, iss))
            else:
                skip.append((it, iss))
        elif matches:                       # esiste ma chiusa → riapri
            to_reopen.append((it, matches[0]))
        else:
            to_create.append(it)
    for iss in existing:
        m = FP_RE.search(iss.get("body") or "")
        fp = m.group(1) if m else None
        if iss["state"] == "open" and (fp is None or fp not in desired):
            to_close.append(iss)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"\n=== Piano sync ({mode}) su {args.repo} ===")
    print(f"  CREATE : {len(to_create)}")
    print(f"  UPDATE : {len(to_update)}")
    print(f"  REOPEN : {len(to_reopen)}"
          + ("   DRIFT: chiuse in UI ma ancora `status: open` nel backlog" if to_reopen else ""))
    print(f"  CLOSE  : {len(to_close)}")
    print(f"  SKIP   : {len(skip)} (gia allineate)\n")

    def ms_tag(it):
        return f"  milestone=«{it['milestone']}»" if it.get("milestone") else ""

    def union_labels(it, iss=None):
        cur = [l["name"] if isinstance(l, dict) else l for l in (iss.get("labels") or [])] if iss else []
        return sorted(set(cur) | set(it["labels"]) | {SYNC_LABEL})

    for it in to_create:
        print(f"  + CREATE [{it['id']}] {it['title']}{ms_tag(it)}")
        if args.apply:
            res = gh.create_issue(it["title"], build_body(it, backlog_url), union_labels(it),
                                  assignees=assignees_for(it), milestone=milestone_for(it))
            print(f"      → #{res['number']} {res['html_url']}")
    for it, iss in to_update:
        print(f"  ~ UPDATE #{iss['number']} [{it['id']}] {it['title']}{ms_tag(it)}")
        if args.apply:
            gh.update_issue(iss["number"], it["title"], build_body(it, backlog_url),
                            union_labels(it, iss), assignees=assignees_for(it),
                            milestone=milestone_for(it))
    for it, iss in to_reopen:
        print(f"  ^ REOPEN #{iss['number']} [{it['id']}] {it['title']}"
              "   DRIFT: era chiusa in UI ma `status: open` nel backlog → riaperta (il backlog comanda)")
        if args.apply:
            gh.update_issue(iss["number"], it["title"], build_body(it, backlog_url),
                            union_labels(it, iss), assignees=assignees_for(it),
                            milestone=milestone_for(it), state="open")
            gh.comment(iss["number"],
                       f"Riaperta: l'item `{it['id']}` e di nuovo attivo in `docs/backlog.md`. "
                       "Se volevi chiuderla davvero, metti `status: done` sull'item "
                       "(non chiuderla solo in UI).")
    for iss in to_close:
        m = FP_RE.search(iss.get("body") or "")
        fp = m.group(1) if m else "?"
        note = close_note(items_by_id.get(fp))
        print(f"  - CLOSE  #{iss['number']} (backlog-id: {fp}) {iss['title']}")
        if note:
            print(f"      estratto: {note if len(note) <= 120 else note[:120] + '…'}")
        if args.apply:
            body = ("Chiusa automaticamente: l'item non e piu attivo "
                    "(rimosso o `status: done`) in `docs/backlog.md`.")
            if note:
                body += f"\n\n**Stato/motivo dal backlog:**\n\n> {note}"
            gh.comment(iss["number"], body)
            gh.set_state(iss["number"], "closed", reason="completed")
    for it, iss in skip:
        print(f"  = SKIP   #{iss['number']} [{it['id']}]")

    if not args.apply:
        print("\n(DRY-RUN: nessuna modifica. Rilancia con --apply per applicare.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

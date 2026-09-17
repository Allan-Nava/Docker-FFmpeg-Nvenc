#!/usr/bin/env python3
"""
backlog.py — parsing + regole di validazione condivise di docs/backlog.md.

FONTE UNICA delle regole strutturali del backlog: importata sia da
`sync-backlog-to-issues.py` (che apre/aggiorna le issue GitHub) sia da
`backlog-lint.py` (che valida in CI) sia da `generate-roadmap.py`. Niente
duplicazione di regex/convenzioni fra i tre.

Un item del backlog e:

    ### `id-stabile` — Titolo
    - **status**: open|done          (default: open)
    - **priority**: low|medium|high  (opzionale)
    - **labels**: a, b, c            (opzionale)
    - **milestone**: <titolo>        (opzionale)
    - **owner**: <username>          (opzionale)
    - **ref**: <link>                (opzionale)

    prosa … (diventa il corpo della issue)

`parse_backlog()` e PURA (nessun sys.exit): ritorna la lista degli item. Ogni item porta,
oltre ai campi usati dal sync, due chiavi tecniche per il linter:
  - `_line`      : numero di riga (1-based) dell'heading `### ...`
  - `_meta_seen` : lista di {key, line, value} dei bullet `- **k**: v` trovati nel
                   *blocco meta* (la sequenza di bullet subito sotto l'heading, prima della
                   prima riga di prosa) — serve a stanare chiavi sconosciute (refusi).
"""
import re

# --- regex strutturali (fonte unica) ---------------------------------------------------
# item: "### `id` — Titolo"  (id tra backtick; separatore — o - opzionale)
ITEM_RE = re.compile(r"^###\s+`([^`]+)`\s*[—\-]*\s*(.*)$")
META_RE = re.compile(r"^[-*]\s+\*\*(\w+)\*\*:\s*(.+)$")
FP_RE = re.compile(r"<!--\s*backlog-id:\s*([a-zA-Z0-9._-]+)")        # id (compat: con o senza | hash:)
HASH_RE = re.compile(r"backlog-id:\s*[\w.-]+\s*\|\s*hash:\s*([0-9a-f]+)")

# --- vocabolario ammesso ---------------------------------------------------------------
KNOWN_META = {"status", "priority", "labels", "milestone", "owner", "ref"}
VALID_STATUS = {"open", "done"}
VALID_PRIORITY = {"low", "medium", "high"}
ID_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")   # kebab-case minuscolo


def _new_item(item_id, title, line):
    return {"id": item_id, "title": title,
            "labels": [], "status": "open", "priority": "", "ref": "", "owner": "",
            "milestone": "", "body": [], "_line": line, "_meta_seen": []}


def parse_backlog(path):
    """Parsa docs/backlog.md → lista di item (PURA, nessun sys.exit).

    Un bullet `- **k**: v` con `k` noto imposta il campo; qualunque altra riga (blank,
    prosa, checklist, bullet con chiave non nota) finisce nel corpo. In piu registra in
    `_meta_seen` i bullet incontrati nel blocco meta iniziale (finche non parte la prosa)
    per permettere al linter di segnalare i refusi di chiave.
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
        if re.match(r"^#{1,3}\s", ln):   # nuova sezione (non-item) → chiude l'item corrente
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
                cur["body"].append(ln)   # chiave non nota → corpo
        else:
            if ln.strip():               # prima riga di prosa non-blank → fine blocco meta
                in_meta = False
            cur["body"].append(ln)
    if cur:
        items.append(cur)
    return items


def item_hash(item):
    """Hash stabile del contenuto sincronizzato (titolo/labels/priority/ref/owner/milestone/corpo).
    Embeddato nel fingerprint della issue: se cambia → la issue va aggiornata."""
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
    """Normalizza un titolo milestone per il match 'stessa milestone' (case + spazi collassati)."""
    return re.sub(r"\s+", " ", title).strip().casefold()


def lint(items):
    """Valida gli item parsati. Ritorna (errors, warnings): due liste di stringhe gia formattate
    (con numero di riga). `errors` non vuoto ⇒ il linter esce con status ≠0."""
    errors, warnings = [], []

    # 1) id duplicati (fatale: il sync stesso rifiuterebbe)
    by_id = {}
    for it in items:
        by_id.setdefault(it["id"], []).append(it["_line"])
    for iid, ls in by_id.items():
        if len(ls) > 1:
            errors.append(f"id duplicato `{iid}` (righe {', '.join(map(str, ls))})")

    for it in items:
        line, iid = it["_line"], it["id"]
        loc = f"riga {line} [{iid}]"

        # 2) formato id
        if not ID_RE.match(iid):
            errors.append(f"{loc}: id non valido (atteso kebab-case minuscolo `[a-z0-9._-]`)")

        # 3) titolo non vuoto
        if not it["title"].strip():
            errors.append(f"{loc}: titolo vuoto")

        # 4) status / priority nel vocabolario
        if it["status"] and it["status"].lower() not in VALID_STATUS:
            errors.append(f"{loc}: status `{it['status']}` non valido (atteso {sorted(VALID_STATUS)})")
        if it["priority"] and it["priority"].lower() not in VALID_PRIORITY:
            errors.append(f"{loc}: priority `{it['priority']}` non valida (attesa {sorted(VALID_PRIORITY)})")

        # 5) chiavi meta sconosciute nel blocco iniziale (refusi tipo `- **lables**:`)
        for meta in it["_meta_seen"]:
            if meta["key"].lower() not in KNOWN_META:
                errors.append(f"riga {meta['line']} [{iid}]: chiave meta sconosciuta "
                              f"`{meta['key']}` (note: {sorted(KNOWN_META)}) — refuso?")

        # 5b) stessa chiave meta ripetuta nell'item: vince l'ultima e la prima si perde in
        #     silenzio (copia-incolla di un item). Capitato scrivendo il primo backlog.
        seen_keys = {}
        for meta in it["_meta_seen"]:
            seen_keys.setdefault(meta["key"].lower(), []).append(meta["line"])
        for k, ls in seen_keys.items():
            if len(ls) > 1:
                errors.append(f"{loc}: chiave meta `{k}` ripetuta (righe "
                              f"{', '.join(map(str, ls))}) — vince l'ultima")

    # 6) coerenza titoli milestone: stessi caratteri ovunque (segnala varianti case/spazi)
    variants = {}
    for it in items:
        if it["milestone"]:
            variants.setdefault(_norm_milestone(it["milestone"]), set()).add(it["milestone"])
    for norm, raws in variants.items():
        if len(raws) > 1:
            warnings.append("milestone scritta in modi diversi (stessa milestone?): "
                            + " · ".join(f"«{r}»" for r in sorted(raws))
                            + " → uniformare il titolo (match esatto per carattere)")

    return errors, warnings

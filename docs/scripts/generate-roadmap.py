#!/usr/bin/env python3
"""
generate-roadmap.py — genera docs/roadmap.md raggruppando gli item del backlog per milestone.

Legge docs/backlog.md via lib/backlog.py (fonte unica di parsing) e produce una pagina di
overview che affianca le milestone GitHub: una sezione per milestone (con conteggi open/done
e tabella degli item) + una sezione "Non pianificati" per gli item open senza milestone.

La pagina e GENERATA e viene COMMITTATA: il gate `generated-pages` della CI la rigenera con
--check e fallisce se diverge. Non editarla a mano.

Uso:
  python3 docs/scripts/generate-roadmap.py            # scrive docs/roadmap.md
  python3 docs/scripts/generate-roadmap.py --check    # exit 1 se l'output diverge dal file in git
Requires: solo stdlib.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import backlog as B   # noqa: E402

OUT = os.path.normpath(os.path.join(HERE, "..", "roadmap.md"))
PRIO_ORDER = {"high": 0, "medium": 1, "low": 2, "": 3}
STATUS_GLYPH = {"done": "done", "open": "open"}


def _md_escape(s):
    return s.replace("|", "\\|")


def _sort_key(it):
    # open prima di done; poi priorita (high→low); poi id
    return (it["status"].lower() == "done", PRIO_ORDER.get(it["priority"].lower(), 3), it["id"])


def render(items):
    planned = [it for it in items if it["milestone"]]
    milestones = sorted({it["milestone"] for it in planned})

    L = []
    L.append("# Roadmap — milestone del backlog")
    L.append("")
    L.append("<!-- GENERATO da docs/scripts/generate-roadmap.py — NON editare a mano. -->")
    L.append("> Pagina **generata** da [`docs/scripts/generate-roadmap.py`](scripts/generate-roadmap.py) "
             "leggendo [`docs/backlog.md`](backlog.md) (unica sorgente). Affianca le "
             "[milestone GitHub](https://github.com/Allan-Nava/Docker-FFmpeg-Nvenc/milestones), "
             "create e popolate dal sync.")
    L.append("")
    tot_open = sum(1 for it in planned if it["status"].lower() != "done")
    tot_done = sum(1 for it in planned if it["status"].lower() == "done")
    L.append(f"_{len(milestones)} milestone · {len(planned)} item pianificati "
             f"({tot_open} open · {tot_done} done)._")
    L.append("")

    for ms in milestones:
        its = sorted((it for it in planned if it["milestone"] == ms), key=_sort_key)
        n_open = sum(1 for it in its if it["status"].lower() != "done")
        n_done = sum(1 for it in its if it["status"].lower() == "done")
        L.append(f"## {ms}")
        L.append("")
        L.append(f"_{n_open} open · {n_done} done_")
        L.append("")
        L.append("| id | Titolo | Priorita | Status |")
        L.append("|----|--------|----------|--------|")
        for it in its:
            st = STATUS_GLYPH.get(it["status"].lower(), it["status"])
            prio = it["priority"] or "—"
            L.append(f"| `{it['id']}` | {_md_escape(it['title'])} | {prio} | {st} |")
        L.append("")

    # non pianificati: solo open (i done senza milestone sono storia, stanno nel backlog)
    unplanned = sorted((it for it in items if not it["milestone"]
                        and it["status"].lower() != "done"), key=_sort_key)
    L.append("## Non pianificati (senza milestone)")
    L.append("")
    L.append(f"_{len(unplanned)} item open senza milestone. Assegnane una con "
             "`- **milestone**: <titolo>` in [`backlog.md`](backlog.md)._")
    L.append("")
    if unplanned:
        L.append("| id | Titolo | Priorita |")
        L.append("|----|--------|----------|")
        for it in unplanned:
            prio = it["priority"] or "—"
            L.append(f"| `{it['id']}` | {_md_escape(it['title'])} | {prio} |")
        L.append("")

    return "\n".join(L).rstrip() + "\n"


def main():
    ap = argparse.ArgumentParser(description="Genera docs/roadmap.md dalle milestone del backlog.")
    ap.add_argument("--backlog", default=os.path.join(HERE, "..", "backlog.md"))
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--check", action="store_true",
                    help="non scrive: exit 1 se l'output diverge dal file esistente (per CI)")
    args = ap.parse_args()

    items = B.parse_backlog(os.path.normpath(args.backlog))
    content = render(items)

    if args.check:
        existing = ""
        if os.path.isfile(args.out):
            existing = open(args.out, encoding="utf-8").read()
        if existing != content:
            print("roadmap.md non aggiornata: rilancia `python3 docs/scripts/generate-roadmap.py`")
            return 1
        print("roadmap.md aggiornata.")
        return 0

    open(args.out, "w", encoding="utf-8").write(content)
    n_ms = len({it["milestone"] for it in items if it["milestone"]})
    print(f"scritta {os.path.relpath(args.out)} · {n_ms} milestone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

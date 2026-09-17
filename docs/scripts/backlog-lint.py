#!/usr/bin/env python3
"""
backlog-lint.py — valida docs/backlog.md SENZA toccare GitHub (lint standalone per CI/PR).

Feedback immediato in PR/push: la validazione (id univoci, status/priority validi, chiavi meta
note, coerenza titoli milestone) non aspetta il run del sync. Regole centralizzate in
`lib/backlog.py` (fonte unica, usata anche da sync-backlog-to-issues.py e generate-roadmap.py).

Exit code:
  0 → nessun errore (eventuali warning stampati ma non bloccanti; con --strict i warning falliscono)
  1 → almeno un errore (o warning in --strict)
  2 → errore d'uso (file mancante, ecc.)

Requires: solo stdlib.
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "lib"))
import backlog as B   # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="Lint di docs/backlog.md (standalone, no GitHub).")
    ap.add_argument("--backlog", default=os.path.join(HERE, "..", "backlog.md"))
    ap.add_argument("--strict", action="store_true", help="tratta i warning come errori (exit 1)")
    args = ap.parse_args()

    path = os.path.normpath(args.backlog)
    if not os.path.isfile(path):
        print(f"ERRORE: backlog non trovato: {path}", file=sys.stderr)
        return 2

    items = B.parse_backlog(path)
    errors, warnings = B.lint(items)

    n_open = sum(1 for it in items if it["status"].lower() != "done")
    n_ms = len({it["milestone"] for it in items if it["milestone"]})
    print(f"backlog-lint: {len(items)} item ({n_open} open) · {n_ms} milestone distinte")

    for w in warnings:
        print(f"  WARN  {w}")
    for e in errors:
        print(f"  FAIL  {e}")

    fail = bool(errors) or (args.strict and bool(warnings))
    if fail:
        n = len(errors) + (len(warnings) if args.strict else 0)
        print(f"\nbacklog-lint: {n} problema/i bloccante/i.")
        return 1
    print("\nbacklog-lint OK" + (f" ({len(warnings)} warning non bloccanti)" if warnings else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

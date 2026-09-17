#!/usr/bin/env python3
"""
changelog.py — conventional-commit parsing and Keep a Changelog editing.

SINGLE SOURCE for two rules that are otherwise retyped in three places (the commit hook, the commit
helper, the release workflow):

  1. what a valid commit subject looks like — `next-version.py` reads the version bump out of it, so
     a subject nobody can parse is a release nobody can number;
  2. which `### section` of `## [Unreleased]` a given commit belongs in.

What is NOT automated: the prose. `feat: add the 9.0 variant` becomes the bullet only when nobody
writes a better one; the entries worth reading are hand-written and this module just files them in
the right place. `entries_from_commits()` exists as the fallback for a release where nobody wrote
anything at all — a thin changelog beats an empty one.
"""
import re

# Keep a Changelog's own order; subsections are kept in it when they are created.
SECTION_ORDER = ["Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"]

# Conventional-commit type → changelog section.
TYPE_SECTION = {
    "feat": "Added",
    "fix": "Fixed",
    "security": "Security",
    "remove": "Removed",
    "revert": "Removed",
    "deprecate": "Deprecated",
    "perf": "Changed",
    "refactor": "Changed",
    "docs": "Changed",
    "build": "Changed",
    "ci": "Changed",
    "chore": "Changed",
    "test": "Changed",
    "style": "Changed",
}

# Accepted as commit subjects but never turned into changelog entries.
BOOKKEEPING_RE = re.compile(r"^(release: v\d+\.\d+\.\d+|Merge |Revert \"|fixup! |squash! )")

SUBJECT_RE = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.+)$")
BREAKING_FOOTER_RE = re.compile(r"^BREAKING[ -]CHANGE:", re.M)
MAX_DESCRIPTION = 100

UNRELEASED_RE = re.compile(r"^##\s*\[Unreleased\]\s*$", re.M | re.I)
VERSION_RE = re.compile(r"^##\s*\[\d+\.\d+\.\d+\]", re.M)


class Commit:
    """A parsed conventional-commit subject."""

    def __init__(self, type, scope, breaking, description):
        self.type = type
        self.scope = scope
        self.breaking = breaking
        self.description = description

    def __repr__(self):  # pragma: no cover - debugging aid
        return f"Commit({self.type!r}, {self.scope!r}, breaking={self.breaking}, {self.description!r})"


def parse_subject(message):
    """Parse a commit message → Commit, or None when it is not a usable conventional commit.

    Rejects unknown types (a typo would silently become a `patch` bump), empty descriptions and
    subjects long enough to be a paragraph."""
    if not message:
        return None
    subject = message.strip().split("\n", 1)[0].strip()
    m = SUBJECT_RE.match(subject)
    if not m:
        return None
    type_ = m.group("type").lower()
    if type_ not in TYPE_SECTION:
        return None
    description = m.group("desc").strip()
    if not description or len(description) > MAX_DESCRIPTION:
        return None
    breaking = bool(m.group("bang")) or bool(BREAKING_FOOTER_RE.search(message))
    return Commit(type_, (m.group("scope") or "").strip(), breaking, description)


def is_acceptable(message):
    """True when a commit subject may exist in this repository: a conventional commit, or one of the
    bookkeeping shapes git itself produces (merge, revert, fixup) plus the release commit."""
    if not message:
        return False
    subject = message.strip().split("\n", 1)[0].strip()
    return bool(BOOKKEEPING_RE.match(subject)) or parse_subject(message) is not None


def section_for(commit):
    """Commit → the `### section` its entry belongs under."""
    return TYPE_SECTION.get(commit.type, "Changed")


def entry_for(commit):
    """Commit → the bullet text (no leading dash). Scope is kept, breaking changes are flagged:
    they are the ones a reader must not miss."""
    text = f"`{commit.scope}`: {commit.description}" if commit.scope else commit.description
    return f"**BREAKING** {text}" if commit.breaking else text


# --------------------------------------------------------------------------- editing
def _unreleased_bounds(text):
    """(start, end) of the `## [Unreleased]` block, or None."""
    m = UNRELEASED_RE.search(text)
    if not m:
        return None
    nxt = VERSION_RE.search(text, m.end())
    return m.start(), (nxt.start() if nxt else len(text))


def _ensure_unreleased(text):
    """Return text with an `## [Unreleased]` section, inserted above the newest release if missing."""
    if _unreleased_bounds(text):
        return text
    first = VERSION_RE.search(text)
    block = "## [Unreleased]\n\n"
    if first:
        return text[:first.start()] + block + text[first.start():]
    return text.rstrip("\n") + "\n\n" + block


def _tidy(text):
    return re.sub(r"\n{3,}", "\n\n", text).rstrip("\n") + "\n"


def add_entry(text, section, entry):
    """Add `- <entry>` under `## [Unreleased]` → `### <section>`, creating either if needed.

    Idempotent for an identical bullet: running the helper twice on the same commit does not double
    the line. Subsections are created in Keep a Changelog order rather than appended blindly."""
    text = _ensure_unreleased(text)
    start, end = _unreleased_bounds(text)
    block = text[start:end]
    bullet = f"- {entry}"

    if bullet in block:
        return _tidy(text)

    heading = f"### {section}"
    hm = re.search(rf"^{re.escape(heading)}\s*$", block, re.M)
    if hm:
        nxt = re.search(r"^(###\s|##\s)", block[hm.end():], re.M)
        insert_at = hm.end() + (nxt.start() if nxt else len(block) - hm.end())
        body = block[hm.end():insert_at].rstrip("\n")
        new_block = block[:hm.end()] + body + f"\n{bullet}\n\n" + block[insert_at:]
    else:
        # place the new subsection in canonical order among the ones already there
        existing = [(m.group(1), m.start()) for m in re.finditer(r"^###\s+(\w+)\s*$", block, re.M)]
        order = SECTION_ORDER.index(section) if section in SECTION_ORDER else len(SECTION_ORDER)
        after = None
        for name, pos in existing:
            name_order = SECTION_ORDER.index(name) if name in SECTION_ORDER else len(SECTION_ORDER)
            if name_order > order:
                after = pos
                break
        chunk = f"{heading}\n\n{bullet}\n\n"
        if after is None:
            new_block = block.rstrip("\n") + "\n\n" + chunk
        else:
            new_block = block[:after] + chunk + block[after:]

    return _tidy(text[:start] + new_block + ("\n" if not new_block.endswith("\n") else "") + text[end:])


def has_unreleased_entries(text):
    """True when `## [Unreleased]` exists and holds at least one bullet."""
    bounds = _unreleased_bounds(text)
    if not bounds:
        return False
    block = text[bounds[0]:bounds[1]]
    return any(line.startswith("- ") for line in block.split("\n"))


# --------------------------------------------------------------------------- fallback
def entries_from_commits(subjects):
    """Draft {section: [entry, …]} from commit subjects, skipping bookkeeping and unparseable ones."""
    drafted = {}
    for subject in subjects:
        first = subject.strip().split("\n", 1)[0].strip()
        if BOOKKEEPING_RE.match(first):
            continue
        commit = parse_subject(subject)
        if commit is None:
            continue
        drafted.setdefault(section_for(commit), []).append(entry_for(commit))
    return drafted


def apply_drafted(text, subjects):
    """Add every drafted entry to `## [Unreleased]`, in Keep a Changelog order."""
    drafted = entries_from_commits(subjects)
    for section in SECTION_ORDER:
        for entry in drafted.get(section, []):
            text = add_entry(text, section, entry)
    return text

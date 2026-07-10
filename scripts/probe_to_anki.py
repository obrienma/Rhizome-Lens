#!/usr/bin/env python3
"""
probe_to_anki.py — Import probe files into Anki via AnkiConnect.

Run from rhizome-lens repo root to sync all repos:
    python3 scripts/probe_to_anki.py

Or target a specific repo or file:
    python3 scripts/probe_to_anki.py --repo synapse-l4
    python3 scripts/probe_to_anki.py --file ../synapse-l4/docs/probes/phase-1.md
    python3 scripts/probe_to_anki.py --dry-run
    python3 scripts/probe_to_anki.py --query-flagged

Requires: Anki open with AnkiConnect plugin installed (default port 8765).
WSL2: AnkiConnect must bind to 0.0.0.0 (see JOURNAL_ANKI_PLAN.md §3.2).
"""

import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


# ---------------------------------------------------------------------------
# Repo registry
# ---------------------------------------------------------------------------

REPOS = [
    "synapse-l4",
    "sentinel-l7",
    "EventHorizon",
    "ledger-l5",
]

# Script lives in rhizome-lens/scripts/ — parent is the repo root,
# sibling repos are one level up from there.
SCRIPT_DIR = Path(__file__).resolve().parent
OBSERVABILITY_ROOT = SCRIPT_DIR.parent
DEV_ROOT = OBSERVABILITY_ROOT.parent


def repo_probes_dir(repo: str) -> Path:
    return DEV_ROOT / repo / "docs" / "probes"


# ---------------------------------------------------------------------------
# WSL2 networking
# ---------------------------------------------------------------------------

def _windows_host_ip() -> str:
    """In WSL2, the Windows host is the default route gateway."""
    import subprocess
    try:
        out = subprocess.check_output(["ip", "route"], text=True)
        for line in out.splitlines():
            if line.startswith("default"):
                return line.split()[2]
    except Exception:
        pass
    return "localhost"


_HOST = _windows_host_ip()
ANKI_URL = f"http://{_HOST}:8765"
ANKI_VERSION = 6


# ---------------------------------------------------------------------------
# AnkiConnect helpers
# ---------------------------------------------------------------------------

def anki(action: str, **params) -> object:
    payload = json.dumps({
        "action": action,
        "version": ANKI_VERSION,
        "params": params,
    }).encode()
    req = urllib.request.Request(
        ANKI_URL, data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    error = result.get("error")
    if error:
        raise RuntimeError(f"AnkiConnect error ({action}): {error}")
    return result["result"]


def ensure_deck(deck_name: str) -> None:
    anki("createDeck", deck=deck_name)


def add_notes_deduped(notes: list[dict]) -> tuple[int, int]:
    """
    Filter duplicates via canAddNotesWithErrorDetail before calling addNotes.
    Returns (added, skipped).
    """
    if not notes:
        return 0, 0
    checks = anki("canAddNotesWithErrorDetail", notes=notes)
    eligible = [n for n, c in zip(notes, checks) if c.get("canAdd")]
    skipped = len(notes) - len(eligible)
    added = 0
    if eligible:
        results = anki("addNotes", notes=eligible)
        added = sum(1 for r in results if r is not None)
    return added, skipped


def query_flagged(deck: str = "Rhizome") -> list[int]:
    """Return note IDs flagged blue (flag:4) in the given deck."""
    return anki("findNotes", query=f"flag:4 deck:{deck}")


def get_notes_info(note_ids: list[int]) -> list[dict]:
    return anki("notesInfo", notes=note_ids)


# ---------------------------------------------------------------------------
# Probe file parser
# ---------------------------------------------------------------------------

CARD_BLOCK_RE = re.compile(r"```markdown\n(.*?)```", re.DOTALL)
FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
TAGS_RE = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
DECK_RE = re.compile(r"^deck:\s*(.+)", re.MULTILINE)
TYPE_RE = re.compile(r"^type:\s*(.+)", re.MULTILINE)
EXTRA_RE = re.compile(r"\nExtra:\s*(.+?)$", re.DOTALL)


def parse_tags(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()]


def parse_card_block(block: str) -> dict | None:
    fm_match = FRONTMATTER_RE.match(block)
    if not fm_match:
        return None

    fm = fm_match.group(1)
    body = block[fm_match.end():]

    type_m = TYPE_RE.search(fm)
    deck_m = DECK_RE.search(fm)
    tags_m = TAGS_RE.search(fm)

    if not type_m or not deck_m:
        return None

    card_type = type_m.group(1).strip()
    deck = deck_m.group(1).strip()
    tags = parse_tags(tags_m.group(1)) if tags_m else []

    # Extract Extra from body
    extra = ""
    extra_m = EXTRA_RE.search(body)
    if extra_m:
        extra = extra_m.group(1).strip()
        body = body[: extra_m.start()].strip()
    else:
        body = body.strip()

    if card_type == "cloze":
        return {
            "type": "cloze",
            "deck": deck,
            "tags": tags,
            "fields": {"Text": body, "Back Extra": extra},
        }

    if card_type == "basic":
        qa_m = re.match(r"^Q:\s*(.*?)\n\nA:\s*(.*)$", body, re.DOTALL)
        if not qa_m:
            return None
        return {
            "type": "basic",
            "deck": deck,
            "tags": tags,
            "fields": {
                "Front": qa_m.group(1).strip(),
                "Back": qa_m.group(2).strip(),
                "Extra": extra,
            },
        }

    if card_type == "image-occlusion":
        return {
            "type": "image-occlusion",
            "deck": deck,
            "tags": tags,
            "raw": body,
            "extra": extra,
        }

    return None


def parse_probe_file(path: Path) -> list[dict]:
    content = path.read_text(encoding="utf-8")
    cards = []
    for block in CARD_BLOCK_RE.finditer(content):
        card = parse_card_block(block.group(1))
        if card:
            cards.append(card)
    return cards


# ---------------------------------------------------------------------------
# Build AnkiConnect note objects
# ---------------------------------------------------------------------------

MODEL_NAMES = {
    "basic": "Basic",
    "cloze": "Cloze",
}


def build_note(card: dict) -> dict:
    return {
        "deckName": card["deck"],
        "modelName": MODEL_NAMES[card["type"]],
        "fields": card["fields"],
        "tags": card["tags"],
        "options": {"allowDuplicate": False, "duplicateScope": "deck"},
    }


# ---------------------------------------------------------------------------
# Sync a single repo
# ---------------------------------------------------------------------------

def sync_repo(repo: str, dry_run: bool) -> tuple[int, int, int]:
    """
    Sync all probe files for a repo.
    Returns (added, skipped, io_pending).
    """
    probes_dir = repo_probes_dir(repo)
    if not probes_dir.exists():
        print(f"  [{repo}] docs/probes/ not found — skipping")
        return 0, 0, 0

    files = sorted(probes_dir.glob("*.md"))
    if not files:
        print(f"  [{repo}] no probe files found — skipping")
        return 0, 0, 0

    all_cards: list[dict] = []
    io_pending: list[dict] = []

    for f in files:
        cards = parse_probe_file(f)
        syncable = [c for c in cards if c["type"] in MODEL_NAMES]
        io_cards = [c for c in cards if c["type"] == "image-occlusion"]
        print(f"    {f.name}: {len(syncable)} syncable, {len(io_cards)} image-occlusion (manual)")
        all_cards.extend(syncable)
        io_pending.extend(io_cards)

    if dry_run:
        for c in all_cards:
            print(f"\n    [{c['type'].upper()}] {c['deck']} | tags: {c['tags']}")
            for k, v in c["fields"].items():
                if v:
                    print(f"      {k}: {v[:80]}{'...' if len(v) > 80 else ''}")
        return len(all_cards), 0, len(io_pending)

    decks = {c["deck"] for c in all_cards + io_pending}
    for deck in sorted(decks):
        ensure_deck(deck)

    notes = [build_note(c) for c in all_cards]
    added, skipped = add_notes_deduped(notes)

    return added, skipped, len(io_pending)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sync probe files from all Rhizome repos into Anki."
    )
    parser.add_argument(
        "--repo", metavar="NAME",
        help=f"Sync a single repo only. One of: {', '.join(REPOS)}",
    )
    parser.add_argument(
        "--file", metavar="PATH",
        help="Sync a single probe .md file",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Parse and print without adding to Anki",
    )
    parser.add_argument(
        "--query-flagged", action="store_true",
        help="Show blue-flagged cards (flag:4 deck:Rhizome) and exit",
    )
    args = parser.parse_args()

    # --- Flagged card review mode ---
    if args.query_flagged:
        print("Querying blue-flagged cards (flag:4 deck:Rhizome)...\n")
        note_ids = query_flagged()
        if not note_ids:
            print("No flagged cards found.")
            return
        notes_info = get_notes_info(note_ids)
        print(f"{len(notes_info)} flagged card(s) need review:\n")
        for i, note in enumerate(notes_info, 1):
            fields = note.get("fields", {})
            first_field = next(iter(fields.values()), {})
            preview = first_field.get("value", "")[:120]
            tags = " ".join(note.get("tags", []))
            print(f"  [{i}] {preview}")
            if tags:
                print(f"       tags: {tags}")
            print()
        return

    # --- Single file mode ---
    if args.file:
        path = Path(args.file)
        if not path.is_file():
            print(f"Error: {args.file} not found", file=sys.stderr)
            sys.exit(1)
        cards = parse_probe_file(path)
        syncable = [c for c in cards if c["type"] in MODEL_NAMES]
        io_pending = [c for c in cards if c["type"] == "image-occlusion"]
        print(f"{path.name}: {len(syncable)} syncable, {len(io_pending)} image-occlusion")
        if not args.dry_run:
            decks = {c["deck"] for c in syncable}
            for deck in sorted(decks):
                ensure_deck(deck)
            added, skipped = add_notes_deduped([build_note(c) for c in syncable])
            print(f"✓ Added {added}. {skipped} duplicate(s) skipped.")
        return

    # --- Repo sync mode ---
    target_repos = [args.repo] if args.repo else REPOS

    if args.dry_run:
        print("--- DRY RUN ---\n")

    total_added = 0
    total_skipped = 0
    total_io = 0

    for repo in target_repos:
        print(f"\n[{repo}]")
        added, skipped, io_pending = sync_repo(repo, args.dry_run)
        total_added += added
        total_skipped += skipped
        total_io += io_pending
        if not args.dry_run:
            print(f"  ✓ Added {added}. {skipped} duplicate(s) skipped.", end="")
            if io_pending:
                print(f" {io_pending} image-occlusion pending manual creation.", end="")
            print()

    if not args.dry_run:
        print(f"\n{'─' * 50}")
        print(f"Total: {total_added} added, {total_skipped} skipped, {total_io} image-occlusion pending")


if __name__ == "__main__":
    main()
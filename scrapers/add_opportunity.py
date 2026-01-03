#!/usr/bin/env python3
"""
Manually add an opportunity to the database.

Usage:
  python scrapers/add_opportunity.py

It will prompt you for the details interactively.
"""
from __future__ import annotations

import json
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "opportunities.json"


def generate_id(name: str, source: str) -> str:
    raw = f"{name.lower().strip()}|{source.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def parse_deadline(text: str) -> tuple[str | None, str | None]:
    """Parse deadline text into (iso_date, display_date)."""
    if not text:
        return None, None

    # Try to parse various formats
    text = text.strip()

    # Remove ordinal suffixes
    clean = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', text)

    formats = [
        '%B %d, %Y',      # March 15, 2026
        '%B %d %Y',       # March 15 2026
        '%b %d, %Y',      # Mar 15, 2026
        '%b %d %Y',       # Mar 15 2026
        '%m/%d/%Y',       # 03/15/2026
        '%Y-%m-%d',       # 2026-03-15
        '%m-%d-%Y',       # 03-15-2026
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(clean, fmt)
            return dt.strftime('%Y-%m-%d'), text
        except ValueError:
            continue

    # If we can't parse it, return as display only
    return None, text


def infer_tags(text: str) -> dict:
    """Infer tags from text."""
    t = text.lower()
    tags = {}

    # Level
    levels = []
    if any(w in t for w in ["undergraduate", "undergrad"]):
        levels.append("undergraduate")
    if any(w in t for w in ["graduate", "master", "doctoral", "phd", "ph.d"]):
        levels.append("graduate")
    if "postdoc" in t:
        levels.append("postdoc")
    if levels:
        tags["level"] = levels

    # Citizenship
    citizenship = []
    if any(w in t for w in ["u.s. citizen", "us citizen", "american citizen"]):
        citizenship.append("us_citizen")
    if "permanent resident" in t:
        citizenship.append("permanent_resident")
    if any(w in t for w in ["international", "non-u.s", "non-us"]):
        citizenship.append("international")
    if citizenship:
        tags["citizenship"] = citizenship

    # Type
    types = []
    if "fellowship" in t:
        types.append("fellowship")
    if "scholarship" in t:
        types.append("scholarship")
    if "grant" in t:
        types.append("grant")
    if "research" in t:
        types.append("research")
    if "internship" in t:
        types.append("internship")
    if "travel" in t:
        types.append("travel")
    if types:
        tags["type"] = types

    # Funding
    amounts = re.findall(r'\$[\d,]+', text)
    if amounts:
        tags["funding"] = amounts[:2]

    return tags


def main():
    print("\n=== Add New Opportunity ===\n")

    # Required fields
    name = input("Name: ").strip()
    if not name:
        print("Name is required.")
        return

    url = input("URL: ").strip()
    if not url:
        print("URL is required.")
        return

    # Optional fields
    description = input("Description (or paste info, press Enter twice to finish):\n")
    if description:
        while True:
            line = input()
            if not line:
                break
            description += "\n" + line

    source = input("Source [Manual]: ").strip() or "Manual"

    deadline_input = input("Deadline (e.g. 'March 15, 2026' or '2026-03-15'): ").strip()
    deadline_iso, deadline_display = parse_deadline(deadline_input)

    # Infer tags from name + description
    combined_text = f"{name} {description}"
    tags = infer_tags(combined_text)

    print(f"\nInferred tags: {tags}")
    edit_tags = input("Edit tags? (y/N): ").strip().lower()

    if edit_tags == 'y':
        print("\nEnter comma-separated values (or leave blank to skip):")

        level = input(f"  Level (undergraduate,graduate,postdoc) [{','.join(tags.get('level', []))}]: ").strip()
        if level:
            tags["level"] = [l.strip() for l in level.split(",")]

        citizenship = input(f"  Citizenship (us_citizen,permanent_resident,international) [{','.join(tags.get('citizenship', []))}]: ").strip()
        if citizenship:
            tags["citizenship"] = [c.strip() for c in citizenship.split(",")]

        opp_type = input(f"  Type (fellowship,grant,scholarship,research,internship,travel) [{','.join(tags.get('type', []))}]: ").strip()
        if opp_type:
            tags["type"] = [t.strip() for t in opp_type.split(",")]

        funding = input(f"  Funding amounts [{','.join(tags.get('funding', []))}]: ").strip()
        if funding:
            tags["funding"] = [f.strip() for f in funding.split(",")]

    # Remove empty tag categories
    tags = {k: v for k, v in tags.items() if v}

    # Build opportunity
    opp = {
        "id": generate_id(name, source),
        "name": name,
        "description": description[:800] if description else "",
        "url": url,
        "source": source,
        "source_url": url,
        "tags": tags,
        "deadline": deadline_iso,
        "deadline_display": deadline_display,
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }

    # Show preview
    print("\n--- Preview ---")
    print(json.dumps(opp, indent=2))

    confirm = input("\nSave this opportunity? (Y/n): ").strip().lower()
    if confirm == 'n':
        print("Cancelled.")
        return

    # Load existing and append
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    existing = []
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)

    # Check for duplicate
    if any(o["id"] == opp["id"] for o in existing):
        print(f"Warning: Opportunity with this name/source already exists.")
        overwrite = input("Overwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Cancelled.")
            return
        existing = [o for o in existing if o["id"] != opp["id"]]

    existing.append(opp)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    print(f"\nSaved! Total opportunities: {len(existing)}")
    print(f"Don't forget to copy to docs/: cp data/opportunities.json docs/")


if __name__ == "__main__":
    main()

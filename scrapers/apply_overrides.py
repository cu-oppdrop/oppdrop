#!/usr/bin/env python3
"""
Apply manual overrides to opportunities.json after scraping.

This preserves manual edits (deadlines, descriptions, etc.) that would
otherwise be lost when scrapers re-run.

Run after all scrapers:
  python scrapers/apply_overrides.py
"""
from __future__ import annotations

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
OPPORTUNITIES_FILE = DATA_DIR / "opportunities.json"
OVERRIDES_FILE = DATA_DIR / "overrides.json"


def main():
    print("=== Applying Overrides ===\n")

    # Load opportunities
    if not OPPORTUNITIES_FILE.exists():
        print("No opportunities.json found")
        return

    with open(OPPORTUNITIES_FILE) as f:
        opportunities = json.load(f)

    # Load overrides
    if not OVERRIDES_FILE.exists():
        print("No overrides.json found - nothing to apply")
        return

    with open(OVERRIDES_FILE) as f:
        data = json.load(f)

    overrides = data.get("overrides", {})
    blocked_sites = data.get("blocked_sites", [])

    if not overrides:
        print("No overrides defined")
        return

    # Apply overrides
    applied = 0
    for opp in opportunities:
        opp_id = opp.get("id")
        if opp_id in overrides:
            override = overrides[opp_id]
            for key, value in override.items():
                if key == "note":
                    continue  # Skip notes, they're just for documentation
                old_value = opp.get(key)
                opp[key] = value
                print(f"  {opp['name'][:40]}...")
                print(f"    {key}: {old_value} -> {value}")
            applied += 1

    # Save
    with open(OPPORTUNITIES_FILE, "w") as f:
        json.dump(opportunities, f, indent=2)

    print(f"\nApplied {applied} override(s)")

    # Remind about blocked sites
    if blocked_sites:
        print(f"\n--- Sites to check manually ({len(blocked_sites)}) ---")
        for site in blocked_sites:
            print(f"  • {site['domain']}: {site['reason']}")


if __name__ == "__main__":
    main()

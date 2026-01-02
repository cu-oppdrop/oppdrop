# https://www.mei.columbia.edu/
from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.mei.columbia.edu"
HEADERS = {"User-Agent": "Columbia Opportunity Finder (student project)"}
DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "opportunities.json"

def generate_id(name: str, source: str) -> str:
    """Generate stable ID from name + source."""
    raw = f"{name.lower().strip()}|{source.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]

def generate_tags(text: str) -> dict:
    t = text.lower()

    tags = {
        "level": [],
        "citizenship": [],
        "type": [],
        "field": [],
        "funding": [],
    }

    # Level - check for explicit eligibility statements
    has_undergrad = any(w in t for w in ["undergraduate", "undergrad"])

    # Only count as grad if explicitly mentioned (not as part of "undergraduate")
    # Use word boundary check to avoid "undergraduate" matching "graduate"
    grad_keywords = ["master's", "master ", "doctoral", "phd", "ph.d", "dissertation"]
    has_grad_keyword = any(w in t for w in grad_keywords)
    # Check for standalone "graduate" that's not part of "undergraduate"
    has_grad_student = bool(re.search(r'(?<!under)graduate student', t))

    has_grad = has_grad_keyword or has_grad_student

    if has_undergrad:
        tags["level"].append("undergraduate")
    if has_grad:
        tags["level"].append("graduate")
    if "postdoc" in t or "post-doc" in t:
        tags["level"].append("postdoc")

    # Citizenship - detect exclusions like "not US citizens"
    mentions_us = any(w in t for w in ["u.s. citizen", "us citizen", "american citizen"])
    mentions_pr = "permanent resident" in t
    mentions_intl = any(w in t for w in ["international", "non-u.s", "non-us", "foreign", "displaced"])

    # Check for "not US citizens" or "who are not US citizens" patterns
    excludes_us = any(phrase in t for phrase in [
        "not us citizen", "not u.s. citizen", "not american citizen",
        "are not us", "are not u.s.", "neither american citizen",
        "who are not us", "who are not u.s."
    ])
    excludes_pr = any(phrase in t for phrase in [
        "not permanent resident", "nor permanent resident",
        "neither american citizens or permanent",
        "not us citizens or permanent",
        "are not us citizens or permanent",
        "not american citizens or permanent"
    ])

    if mentions_intl or excludes_us:
        tags["citizenship"].append("international")
    if mentions_us and not excludes_us:
        tags["citizenship"].append("us_citizen")
    if mentions_pr and not excludes_pr:
        tags["citizenship"].append("permanent_resident")

    # Type
    if "fellowship" in t:
        tags["type"].append("fellowship")
    if "scholarship" in t:
        tags["type"].append("scholarship")
    if "grant" in t:
        tags["type"].append("grant")
    if "research" in t:
        tags["type"].append("research")
    if "travel" in t:
        tags["type"].append("travel")
    if any(w in t for w in ["language", "arabic", "hebrew", "persian", "turkish"]):
        tags["type"].append("language")

    # Field
    if any(w in t for w in ["middle east", "islamic", "muslim", "mena"]):
        tags["field"].append("middle_east_studies")
    if any(w in t for w in ["humanities", "humanistic"]):
        tags["field"].append("humanities")
    if any(w in t for w in ["social science"]):
        tags["field"].append("social_sciences")

    # Funding amounts
    amounts = re.findall(r'\$[\d,]+', text)
    if amounts:
        tags["funding"] = amounts[:2]

    return {k: v for k, v in tags.items() if v}

def deadline(text: str) -> str | None:
    """Extract deadline from text. Handles formats like 'March 6th, 2025' or 'March 6, 2025'."""
    patterns = [
        r'(?:deadline)[:\s]+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'(?:due)[:\s]+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'(?:by|before)\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\s+deadline',
    ]
    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None

def normalize_url(href: str) -> str:
    if not href:
        return ""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return BASE_URL + href
    return BASE_URL + "/" + href

def fetch(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None

def extract_funding(text: str) -> list[str]:
    """Extract funding amounts like $3,500 or $5,000."""
    amounts = re.findall(r'\$[\d,]+', text)
    return list(dict.fromkeys(amounts))[:3]  # Dedupe, keep first 3


def scrape_detail_page(url: str) -> dict | None:
    """Scrape a detail page for full description, deadline, eligibility."""
    soup = fetch(url)
    if not soup:
        return None

    # Get main content area
    main = soup.find("main") or soup.find("article") or soup.find("div", class_="content")
    if not main:
        main = soup

    # Extract all text from paragraphs
    paragraphs = main.find_all(["p", "li", "h2", "h3"])
    full_text = "\n".join(p.get_text(strip=True) for p in paragraphs)

    # Try to find deadline
    dl = deadline(full_text)

    # Extract funding amounts
    funding = extract_funding(full_text)

    return {
        "full_text": full_text,
        "deadline": dl,
        "funding": funding,
    }


def scrape() -> list[dict]:
    url = BASE_URL + "/fellowships-and-grants"
    print(f"Scraping {url}")

    soup = fetch(url)
    if not soup:
        return []

    opportunities = []
    seen_hrefs = set()

    for li in soup.find_all("li"):
        link = li.find("a")
        if not link or not link.get("href"):
            continue

        name = link.get_text(strip=True).rstrip(":")
        if not name or len(name) < 5:
            continue

        href = link.get("href", "")
        if any(skip in href for skip in ["/about", "/people", "/events", "/news", "/contact", "/academics"]):
            continue

        # Skip duplicates
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)

        full_url = normalize_url(href)
        brief_desc = li.get_text(strip=True).replace(name, "", 1).strip().lstrip(":").strip()

        # Follow link to get full details (only for internal MEI links)
        description = brief_desc
        dl = None
        funding = []

        if href.startswith("/") and "mei.columbia.edu" not in href:
            print(f"    Fetching detail: {full_url}")
            details = scrape_detail_page(full_url)
            if details:
                # Use full text as description (truncated)
                if details["full_text"]:
                    description = details["full_text"][:800]
                if details["deadline"]:
                    dl = details["deadline"]
                if details["funding"]:
                    funding = details["funding"]

        tags = generate_tags(name + " " + description)
        if funding:
            tags["funding"] = funding

        opp = {
            "id": generate_id(name, "MEI"),
            "name": name,
            "description": description,
            "url": full_url,
            "source": "Middle East Institute",
            "source_url": url,
            "tags": tags,
            "deadline": dl if dl else deadline(description),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        opportunities.append(opp)

    print(f"  Found {len(opportunities)} opportunities")
    return opportunities

def scrape_external_fellowships_page() -> list[dict]:
    url = BASE_URL + "/external-fellowships"
    print(f"Scraping {url}")
    
    soup = fetch(url)
    if not soup:
        return []
    
    opportunities = []
    current_section = "External"
    
    main = soup.find("main") or soup.find("article") or soup

    for element in main.find_all(["h2", "p"]):
        if element.name == "h2":
            text = element.get_text(strip=True)
            if text and len(text) > 3:
                current_section = text
            continue
        
        link = element.find("a")
        if not link:
            continue

        href = link.get("href", "")

        # Skip internal nav links
        if href.startswith("/") and not href.startswith("/external"):
            if any(skip in href for skip in ["/about", "/people", "/events", "/academics"]):
                continue

        name = link.get_text(strip=True).rstrip(":")
        if not name or len(name) < 5:
            continue

        full_text = element.get_text(strip=True)

        description = full_text
        if name in description:
            idx = description.find(name) + len(name)
            description = description[idx:].strip().lstrip(":").strip()

        if href.startswith("#") or href.startswith("mailto:"):
            continue

        if "columbia.edu" in href:
            source = "Columbia - " + current_section
        else:
            source = current_section

        opp = {
            "id": generate_id(name, source),
            "name": name,
            "description": description[:500],  # Cap length
            "url": normalize_url(href),
            "source": source,
            "source_url": url,
            "tags": generate_tags(name + " " + description),
            "deadline": deadline(description),
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        }
        opportunities.append(opp)
    
    print(f"  Found {len(opportunities)} opportunities")
    return opportunities


def dedupe(opportunities: list[dict]) -> list[dict]:
    """Remove duplicates by ID."""
    seen = {}
    for opp in opportunities:
        if opp["id"] not in seen:
            seen[opp["id"]] = opp
    return list(seen.values())

def main():
    print("=== MEI Scraper ===\n")
    
    all_opps = []
    all_opps.extend(scrape())
    all_opps.extend(scrape_external_fellowships_page())
    
    all_opps = dedupe(all_opps)
    print(f"\nTotal: {len(all_opps)} unique opportunities")
    
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    existing = []
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                existing = json.load(f)
        except:
            existing = []
    
    non_mei = [o for o in existing if "mei.columbia.edu" not in o.get("source_url", "")]
    
    combined = non_mei + all_opps
    combined = dedupe(combined)
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(combined, f, indent=2)
    
    print(f"Saved to {OUTPUT_FILE}")
    
    print("\n--- By Source ---")
    sources = {}
    for o in combined:
        s = o.get("source", "Unknown")
        sources[s] = sources.get(s, 0) + 1
    for s, c in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")


if __name__ == "__main__":
    main()


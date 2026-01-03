from __future__ import annotations

import json
import re
import hashlib
from datetime import datetime, timezone
from pathlib import Path
import requests
from bs4 import BeautifulSoup

BASE_URL = "https://urf.columbia.edu"
SEARCH_URL = BASE_URL + "/opportunity/search"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}

DATA_DIR = Path(__file__).parent.parent / "data"
OUTPUT_FILE = DATA_DIR / "opportunities.json"
COOKIES_FILE = Path(__file__).parent / "cookies.json"


def load_cookies() -> dict:
    """Load cookies from cookies.json file."""
    if not COOKIES_FILE.exists():
        print(f"ERROR: {COOKIES_FILE} not found.")
        print("To create it:")
        print("  1. Log into URF in your browser")
        print("  2. Open DevTools → Application → Cookies → urf.columbia.edu")
        print("  3. Create cookies.json with the cookie values")
        print("  See cookies.example.json for format.")
        return {}

    with open(COOKIES_FILE) as f:
        return json.load(f)


def generate_id(name: str, source: str) -> str:
    """Generate stable ID from name + source."""
    raw = f"{name.lower().strip()}|{source.lower().strip()}"
    return hashlib.md5(raw.encode()).hexdigest()[:12]


def parse_deadline(text: str) -> tuple[str | None, str | None]:
    """
    Extract deadline from text.
    Returns (iso_date, display_date) tuple.
    """
    patterns = [
        # URF format: "Friday, April 4, 2025" or "Application Deadline:Friday, April 4, 2025"
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        r'deadline[:\s]+(?:[A-Za-z]+,?\s+)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'due[:\s]+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'applications?\s+(?:due|close)[:\s]*([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'(?:by|before)\s+([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})\s+deadline',
        # Standalone date pattern (less reliable, use last)
        r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}',
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            display = match.group(1).strip()
            # Try to parse to ISO format
            iso = None
            try:
                # Remove ordinal suffixes
                clean = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', display)
                # Try parsing
                for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y']:
                    try:
                        dt = datetime.strptime(clean, fmt)
                        iso = dt.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
            return iso, display

    return None, None


def generate_tags(text: str) -> dict:
    """Infer tags from opportunity text."""
    t = text.lower()

    tags = {
        "level": [],
        "citizenship": [],
        "type": [],
        "field": [],
        "funding": [],
    }

    # Level
    if any(w in t for w in ["undergraduate", "undergrad"]):
        tags["level"].append("undergraduate")

    grad_keywords = ["master's", "master ", "doctoral", "phd", "ph.d", "dissertation"]
    has_grad_keyword = any(w in t for w in grad_keywords)
    has_grad_student = bool(re.search(r'(?<!under)graduate student', t))
    if has_grad_keyword or has_grad_student:
        tags["level"].append("graduate")

    if "postdoc" in t or "post-doc" in t:
        tags["level"].append("postdoc")

    # Citizenship - handle URF format like "U.S. Citizen, U.S. Permanent Resident, Not U.S. Citizen or Permanent Resident"
    mentions_us = any(w in t for w in ["u.s. citizen", "us citizen", "american citizen"])
    mentions_pr = "permanent resident" in t
    mentions_intl = any(w in t for w in ["international", "non-u.s", "non-us", "foreign"])
    # URF uses "Not U.S. Citizen or Permanent Resident" to mean international eligible
    mentions_not_us = "not u.s. citizen or permanent resident" in t

    excludes_us = any(phrase in t for phrase in [
        "not us citizen", "not u.s. citizen", "not american citizen",
        "are not us", "are not u.s.", "who are not us"
    ]) and "not u.s. citizen or permanent resident" not in t  # Don't count URF's eligibility tag as exclusion

    if mentions_intl or mentions_not_us:
        tags["citizenship"].append("international")
    if mentions_us and not excludes_us:
        tags["citizenship"].append("us_citizen")
    if mentions_pr and not excludes_us:
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
    if "internship" in t:
        tags["type"].append("internship")
    if any(w in t for w in ["language", "study abroad"]):
        tags["type"].append("language")

    # Funding amounts
    amounts = re.findall(r'\$[\d,]+', text)
    if amounts:
        tags["funding"] = list(dict.fromkeys(amounts))[:3]

    return {k: v for k, v in tags.items() if v}


def fetch(url: str, cookies: dict) -> BeautifulSoup | None:
    """Fetch a page with authentication cookies."""
    try:
        resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=30)

        # Check if we got redirected to login
        if "cas.columbia.edu" in resp.url or resp.status_code == 302:
            print(f"  ERROR: Session expired or invalid cookies. Got redirected to login.")
            return None

        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return None


def scrape_search_page(cookies: dict, page: int = 0) -> list[dict]:
    """
    Scrape a single page of URF opportunity search results.
    Returns list of basic opportunity info (name, url, discipline, eligibility).
    """
    url = SEARCH_URL if page == 0 else f"{SEARCH_URL}?page={page}"
    print(f"Scraping page {page + 1}: {url}")

    soup = fetch(url, cookies)
    if not soup:
        return []

    opportunities = []

    selectors = [
        ".views-row",
        ".view-content .views-row",
        ".opportunity-row",
        "table.views-table tbody tr",
        ".view-opportunity-search .views-row",
    ]

    items = []
    for selector in selectors:
        items = soup.select(selector)
        if items:
            print(f"  Found {len(items)} items with selector: {selector}")
            break

    if not items:
        # Fallback: look for any links to /fellowship/ or /opportunity/
        print("  No view rows found, trying link-based extraction...")
        links = soup.find_all("a", href=re.compile(r"/(fellowship|opportunity)/"))
        for link in links:
            href = link.get("href", "")
            name = link.get_text(strip=True)
            if name and len(name) > 5:
                opportunities.append({
                    "name": name,
                    "url": BASE_URL + href if href.startswith("/") else href,
                    "discipline": "",
                    "eligibility": "",
                })
        print(f"  Found {len(opportunities)} opportunity links")
        return opportunities

    for item in items:
        link = item.find("a", href=re.compile(r"/(fellowship|opportunity)/"))
        if not link:
            continue

        name = link.get_text(strip=True)
        href = link.get("href", "")

        if not name or len(name) < 5:
            continue

        eligibility_elem = item.find(class_=re.compile(r"field-program-eligibility|eligibility"))
        eligibility = eligibility_elem.get_text(strip=True) if eligibility_elem else ""

        discipline_elem = item.find(class_=re.compile(r"field-discipline"))
        discipline = discipline_elem.get_text(strip=True) if discipline_elem else ""

        opportunities.append({
            "name": name,
            "url": BASE_URL + href if href.startswith("/") else href,
            "discipline": discipline,
            "eligibility": eligibility,
        })

    print(f"  Found {len(opportunities)} opportunities")
    return opportunities


def scrape_all_pages(cookies: dict) -> list[dict]:
    """
    Scrape all pages of URF opportunity search.
    URF has 7 pages (0-6).
    """
    all_opportunities = []

    for page in range(7):
        page_opps = scrape_search_page(cookies, page)
        if not page_opps:
            print(f"  No opportunities on page {page + 1}, stopping pagination")
            break
        all_opportunities.extend(page_opps)

    print(f"\nTotal from all pages: {len(all_opportunities)} opportunities")
    return all_opportunities


def scrape_external_page(url: str) -> dict | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")

        body = soup.find("body")
        if not body:
            return None

        for tag in body.find_all(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        text = body.get_text(" ", strip=True)

        deadline_iso, deadline_display = parse_deadline(text)

        amounts = re.findall(r'\$[\d,]+', text)
        funding = list(dict.fromkeys(amounts))[:3]

        return {
            "deadline": deadline_iso,
            "deadline_display": deadline_display,
            "funding": funding,
        }
    except Exception as e:
        print(f"    Error scraping external: {e}")
        return None

def parse_date_field(text: str) -> tuple[str | None, str | None]:
    """
    Parse a date from field text. Simpler than parse_deadline since it's from a known field.
    Returns (iso_date, display_date) tuple.
    """
    # Match various date formats
    patterns = [
        r'(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
        r'([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{4}-\d{2}-\d{2})',
    ]

    for p in patterns:
        match = re.search(p, text, re.IGNORECASE)
        if match:
            display = match.group(1).strip()
            iso = None
            try:
                clean = re.sub(r'(\d+)(?:st|nd|rd|th)', r'\1', display)
                for fmt in ['%B %d, %Y', '%B %d %Y', '%b %d, %Y', '%b %d %Y', '%m/%d/%Y', '%Y-%m-%d']:
                    try:
                        dt = datetime.strptime(clean, fmt)
                        iso = dt.strftime('%Y-%m-%d')
                        break
                    except ValueError:
                        continue
            except Exception:
                pass
            return iso, display

    return None, None


def scrape_detail_page(url: str, cookies: dict) -> dict | None:
    soup = fetch(url, cookies)
    if not soup:
        return None

    body = soup.find("div", class_="field-name-body")
    if body:
        full_text = body.get_text(strip=True)
    else:
        main = soup.find("main") or soup.find("article") or soup.find(class_="node-content")
        if main:
            for nav in main.find_all(["nav", "header", "footer"]):
                nav.decompose()
            full_text = main.get_text(strip=True)
        else:
            full_text = ""

    # Look for "opens" date field
    opens_iso, opens_display = None, None
    opens_field = soup.find(class_=re.compile(r"field.*opens|field.*open-date|field.*start-date", re.I))
    if opens_field:
        field_text = opens_field.get_text(strip=True)
        opens_iso, opens_display = parse_date_field(field_text)

    # Also check for text patterns in full_text if no field found
    if not opens_display:
        opens_patterns = [
            r'applications?\s+open[s:]?\s*(?:on\s+)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
            r'open[s]?\s+(?:on\s+)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
            r'available\s+(?:starting\s+)?([A-Za-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
        ]
        for p in opens_patterns:
            match = re.search(p, full_text, re.IGNORECASE)
            if match:
                opens_iso, opens_display = parse_date_field(match.group(0))
                break

    deadline_iso, deadline_display = None, None
    deadline_field = soup.find(class_=re.compile(r"field-name-field-application-deadline|field.*deadline", re.I))
    if deadline_field:
        field_text = deadline_field.get_text(strip=True)
        deadline_iso, deadline_display = parse_deadline(field_text)

    if not deadline_display:
        deadline_iso, deadline_display = parse_deadline(full_text)

    amounts = re.findall(r'\$[\d,]+', full_text)
    funding = list(dict.fromkeys(amounts))[:3]

    external_url = None
    website_field = soup.find(class_=re.compile(r"field-fellowship-website|field-program-website"))
    if website_field:
        link = website_field.find("a", href=True)
        if link:
            external_url = link.get("href")

    if not external_url:
        for a in soup.find_all("a", href=True):
            if "visit" in a.get_text(strip=True).lower() and "website" in a.get_text(strip=True).lower():
                href = a.get("href")
                if href.startswith("http") and "columbia.edu" not in href:
                    external_url = href
                    break

    # If no deadline from URF and we have an external URL, try scraping it
    if not deadline_display and external_url:
        print(f"      Following external: {external_url[:60]}...")
        external_data = scrape_external_page(external_url)
        if external_data:
            if external_data.get("deadline_display"):
                deadline_iso = external_data["deadline"]
                deadline_display = external_data["deadline_display"]
            if external_data.get("funding") and not funding:
                funding = external_data["funding"]

    return {
        "full_text": full_text,
        "deadline": deadline_iso,
        "deadline_display": deadline_display,
        "opens": opens_iso,
        "opens_display": opens_display,
        "funding": funding,
        "external_url": external_url,
    }


def normalize_discipline(discipline: str) -> list[str]:
    """
    Normalize discipline text into consistent field tags.
    URF uses values like "Foreign Language Learning", "STEM", "Social Sciences", etc.
    """
    if not discipline:
        return []

    # Split on comma for multi-discipline entries
    # URF uses "Arts and Architecture, Foreign Language Learning, Humanities, Social Sciences, STEM"
    parts = [p.strip().lower() for p in discipline.split(",")]
    fields = []

    # Map URF disciplines to normalized field tags
    mappings = {
        "stem": "stem",
        "humanities": "humanities",
        "social sciences": "social_sciences",
        "arts and architecture": "arts",
        "foreign language learning": "language",
    }

    for part in parts:
        if part in mappings:
            fields.append(mappings[part])
        elif part:
            # Keep unknown disciplines with underscore formatting
            fields.append(part.replace(" ", "_"))

    # Dedupe while preserving order
    seen = set()
    result = []
    for f in fields:
        if f not in seen:
            seen.add(f)
            result.append(f)

    return result


def scrape(cookies: dict) -> list[dict]:
    """Main scrape function."""
    # Get opportunity list from all pages
    basic_opps = scrape_all_pages(cookies)
    if not basic_opps:
        return []

    opportunities = []

    for i, opp in enumerate(basic_opps):
        print(f"  [{i+1}/{len(basic_opps)}] Fetching: {opp['name'][:50]}...")

        details = scrape_detail_page(opp["url"], cookies)

        # Get discipline from search page
        discipline = opp.get("discipline", "")

        description = discipline  # Default to discipline if no full text
        deadline = None
        deadline_display = None
        opens = None
        opens_display = None
        funding = []

        if details:
            if details["full_text"]:
                description = details["full_text"][:800]
            deadline = details["deadline"]
            deadline_display = details["deadline_display"]
            opens = details.get("opens")
            opens_display = details.get("opens_display")
            funding = details["funding"]

        # Use eligibility from table + description for tag inference
        eligibility = opp.get("eligibility", "")
        tags = generate_tags(opp["name"] + " " + description + " " + eligibility)

        # Add discipline as field tags
        field_tags = normalize_discipline(discipline)
        if field_tags:
            existing_fields = tags.get("field", [])
            # Merge without duplicates
            for f in field_tags:
                if f not in existing_fields:
                    existing_fields.append(f)
            if existing_fields:
                tags["field"] = existing_fields

        if funding:
            tags["funding"] = funding

        opportunities.append({
            "id": generate_id(opp["name"], "URF"),
            "name": opp["name"],
            "description": description,
            "discipline": discipline,  # Keep raw discipline for display
            "url": opp["url"],
            "source": "URF",
            "source_url": SEARCH_URL,
            "tags": tags,
            "deadline": deadline,
            "deadline_display": deadline_display,
            "opens": opens,
            "opens_display": opens_display,
            "scraped_at": datetime.now(timezone.utc).isoformat(),
        })

    return opportunities


def dedupe(opportunities: list[dict]) -> list[dict]:
    """Remove duplicates by ID."""
    seen = {}
    for opp in opportunities:
        if opp["id"] not in seen:
            seen[opp["id"]] = opp
    return list(seen.values())


def main():
    print("=== URF Scraper ===\n")

    cookies = load_cookies()
    if not cookies:
        return

    opps = scrape(cookies)
    if not opps:
        print("No opportunities found. Check if cookies are valid.")
        return

    opps = dedupe(opps)
    print(f"\nTotal: {len(opps)} unique opportunities")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing data (from other scrapers)
    existing = []
    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE) as f:
                existing = json.load(f)
        except:
            existing = []

    # Keep non-URF opportunities
    non_urf = [o for o in existing if o.get("source") != "URF"]

    # Combine
    combined = non_urf + opps
    combined = dedupe(combined)

    with open(OUTPUT_FILE, "w") as f:
        json.dump(combined, f, indent=2)

    print(f"Saved to {OUTPUT_FILE}")

    # Stats
    print("\n--- By Source ---")
    sources = {}
    for o in combined:
        s = o.get("source", "Unknown")
        sources[s] = sources.get(s, 0) + 1
    for s, c in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {s}: {c}")

    # Deadline stats
    with_deadline = sum(1 for o in opps if o.get("deadline"))
    print(f"\n--- Deadlines ---")
    print(f"  With deadline: {with_deadline}/{len(opps)}")


if __name__ == "__main__":
    main()

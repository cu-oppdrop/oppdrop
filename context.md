# Prowl - Columbia Opportunity Finder

## The Problem

URF (Undergraduate Research & Fellowships) already has most Columbia opportunities in one place. But students don't use it because:

1. **Deadlines are hidden** — You have to click into each opportunity to see when it's due
2. **No urgency sorting** — Can't see "closing soon" at a glance
3. **Too many clicks** — Browse → click → scroll → find deadline → back → repeat
4. **Doesn't reach students** — You have to know to go there

Students find opportunities through group chats and word of mouth instead.

## The Solution

**Prowl = URF, but usable.**

Same data. Better interface:
- Scrape URF → follow each link → extract deadlines
- Display with deadlines visible on list view
- Sort by "closing soon" by default
- Filter by level, citizenship, type
- One glance = know what's urgent

Behind Columbia login is fine. This is for Columbia students.

## Architecture

```
prowl/
├── scrapers/
│   ├── urf_scraper.py           # Scrape URF opportunity list
│   ├── deadline_extractor.py    # Follow links, extract deadlines
│   └── hub_scraper.py           # Department hubs (secondary)
├── data/
│   └── opportunities.json       # Combined output with deadlines
├── docs/                        # GitHub Pages frontend
│   ├── index.html
│   └── opportunities.json
├── .github/workflows/
│   └── scrape.yml               # Daily GitHub Action
└── README.md
```

**Hosting:** GitHub Pages (free)  
**Automation:** GitHub Actions (daily scrape)  
**Database:** None — JSON files in repo  

## Scraping Flow

```
1. Scrape URF search page
   └── Get list of opportunities (name, description, link)
   
2. Follow each opportunity link
   └── Extract deadline from the actual page (regex patterns)
   └── Extract funding amount if present
   
3. (Optional) Scrape department hubs
   └── MEI, IIJS, GSAS, etc. for opportunities not on URF
   
4. Merge, dedupe, output
   └── opportunities.json with deadlines included
```

## URF Auth Strategy

URF requires Columbia login (Shibboleth).

**For development:**
1. Log in to URF in browser
2. Export cookies (browser extension)
3. Use cookies in scraper requests
4. Refresh when expired

**For production (later):**
- Playwright to automate login, or
- Contact URF for API access

## Deadline Extraction

Opportunity pages have inconsistent formats. Use regex patterns:

```python
DEADLINE_PATTERNS = [
    r'deadline[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
    r'due[:\s]+([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
    r'applications?\s+(?:due|close)[:\s]*([A-Za-z]+\s+\d{1,2},?\s+\d{4})',
    r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}',
]
```

If no deadline found → `"deadline": null` or `"Rolling"`

## Data Schema

```json
{
  "id": "unique_stable_id",
  "name": "Summer Research Fellowship",
  "description": "Funding for undergraduate research...",
  "url": "https://urf.columbia.edu/opportunity/123",
  "source": "URF",
  "source_url": "https://urf.columbia.edu/opportunity/search",
  "tags": {
    "level": ["undergraduate"],
    "citizenship": ["us_citizen", "international"],
    "type": ["fellowship", "research"],
    "funding": ["$5,000"]
  },
  "deadline": "2026-03-15",
  "deadline_display": "March 15, 2026",
  "scraped_at": "2026-01-02T12:00:00Z"
}
```

## Tag Inference

Infer from opportunity text:

- **Level:** "undergraduate", "graduate", "doctoral", "PhD", "postdoc"
- **Citizenship:** "U.S. citizen", "permanent resident", "international"
- **Type:** "fellowship", "scholarship", "grant", "research", "travel", "language"
- **Funding:** Extract with regex `\$[\d,]+`

## Frontend Requirements

Static HTML/CSS/JS. No framework.

**Core features:**
1. **Deadline-first display** — Visible on card, not hidden
2. **Sort by deadline** — Soonest first (default)
3. **Urgency badges** — Red (<7 days), Yellow (<30 days)
4. **Filters** — Level, citizenship, type (toggle buttons)
5. **Search** — Name and description
6. **Stats** — "X of Y opportunities"

**Design:** Clean, minimal. Like Linear or Apple.

## GitHub Actions Workflow

```yaml
name: Scrape Opportunities

on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6am UTC
  workflow_dispatch:      # Manual trigger

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install requests beautifulsoup4 playwright
      - run: python scrapers/urf_scraper.py
      - run: python scrapers/deadline_extractor.py
      - run: cp data/opportunities.json docs/
      - name: Commit changes
        run: |
          git config user.email "action@github.com"
          git config user.name "GitHub Action"
          git add data/ docs/
          git diff --staged --quiet || git commit -m "Update $(date -u +%Y-%m-%d)"
          git push
```

## Secondary Sources (Add Later)

Department hubs for opportunities not on URF:

1. MEI — https://www.mei.columbia.edu/fellowships-and-grants
2. IIJS — https://www.iijs.columbia.edu/funding
3. GSAS — https://gsas.columbia.edu/content/internal-fellowships
4. Global Programs — https://globalcenters.columbia.edu
5. CCE — https://www.careereducation.columbia.edu

## Build Order

1. [ ] Inspect URF page structure (HTML or JS-rendered?)
2. [ ] Get auth cookies working
3. [ ] Scrape URF opportunity list
4. [ ] Follow links, extract deadlines
5. [ ] Build frontend with deadline-first UI
6. [ ] Deploy to GitHub Pages
7. [ ] Test with 10 students
8. [ ] Add department hubs if needed

## Phase 2 (Later)

- Weekly newsletter: "5 opportunities closing this week"
- Calendar export (.ics with all deadlines)
- Deadline notifications
- "Submit an opportunity" form

## Success Metrics

- Deadlines visible without extra clicks
- Students find relevant opportunities in <30 seconds
- "Closing soon" opportunities are obvious
- Used weekly by 100+ students

## Resume Framing

```
Prowl — Columbia Opportunity Finder
Creator & Lead Developer

• Built web scraping pipeline that extracts deadlines from 200+ 
  opportunities across URF and department hubs
• Designed deadline-first UI — default sort by "closing soon," 
  urgency badges for approaching deadlines
• Reduced opportunity discovery time from 10+ clicks to 1
• Deployed to 500+ Columbia students
```

## Next Step

Open https://urf.columbia.edu/opportunity/search in browser. View page source. Is the opportunity list in the HTML, or does it load via JavaScript? That determines `requests` vs `playwright`.
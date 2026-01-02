Columbia Opportunity Finder - Build Instructions
Project Overview
Build a web app that aggregates funded opportunities (fellowships, grants, research positions, etc.) from across Columbia departments into a single searchable interface.
The problem: Opportunities are scattered across department newsletters and niche pages. Students (especially first-gen/low-income) miss out because they don't know these exist.
The solution: Web scrapers pull opportunities from department sites → normalized JSON → static frontend with filtering → hosted free on GitHub Pages.
Architecture
opportunity-finder/
├── scrapers/                    # Python scrapers (one per source)
│   ├── mei_scraper.py
│   ├── urf_scraper.py
│   └── ... 
├── data/
│   └── opportunities.json       # Combined scraped data
├── docs/                        # GitHub Pages serves from here
│   ├── index.html               # Frontend
│   └── opportunities.json       # Copy of data for frontend
├── .github/workflows/
│   └── scrape.yml               # GitHub Actions cron job (daily)
└── README.md
Hosting: GitHub Pages (free)
Automation: GitHub Actions runs scrapers daily (free for public repos)
Database: None needed - just JSON files committed to repo
Data Schema
Each opportunity should have this structure:
json{
  "id": "unique_stable_id",
  "name": "Fellowship/Grant Name",
  "description": "What it is, who it's for, what you get",
  "url": "https://link-to-apply-or-learn-more",
  "source": "Department or Institute Name",
  "source_url": "https://page-we-scraped-from",
  "tags": {
    "level": ["undergraduate", "graduate", "postdoc"],
    "citizenship": ["us_citizen", "permanent_resident", "international"],
    "type": ["fellowship", "scholarship", "grant", "research", "travel", "language"],
    "field": ["middle_east_studies", "humanities", "stem", "social_sciences"],
    "funding": ["$5,000"]
  },
  "deadline": "February 1, 2026",
  "scraped_at": "2026-01-02T12:00:00Z"
}
Tag Inference Rules
When scraping, infer tags from the text:

Level: Look for "undergraduate", "graduate", "doctoral", "PhD", "postdoc"
Citizenship: Look for "U.S. citizen", "permanent resident", "international", "non-US"
Type: Look for "fellowship", "scholarship", "grant", "travel", "research", "language"
Funding: Extract dollar amounts with regex like \$[\d,]+

Frontend Requirements
Simple, fast, static HTML/CSS/JS (no framework needed):

Search box - filters by name/description
Filter buttons - toggle tags (OR within category, AND across categories)
Opportunity cards showing:

Name (linked to URL)
Source
Description (truncated)
Tags (color-coded by category)
Deadline (highlighted if present)


Stats - "X of Y opportunities"
Last updated timestamp

Design inspiration: Clean, minimal, like Apple or Linear. Not cluttered.
First Scraper: Middle East Institute
Base URL: https://www.mei.columbia.edu
Pages to scrape:

/fellowships-and-grants - Main fellowships page
/external-fellowships - Curated external opportunities
/flas-fellowships - FLAS fellowship details

Structure notes:

Squarespace site, clean HTML
Opportunities are in <li> elements with <a> links
Descriptions follow the link text
External fellowships page has <h2> section headers

GitHub Actions Workflow
yamlname: Scrape Opportunities

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
      - run: pip install requests beautifulsoup4
      - run: python scrapers/mei_scraper.py
      - run: cp data/opportunities.json docs/
      - name: Commit changes
        run: |
          git config user.email "action@github.com"
          git config user.name "GitHub Action"
          git add data/ docs/
          git diff --staged --quiet || git commit -m "Update $(date -u +%Y-%m-%d)"
          git push
Future Scrapers to Add
Priority order:

URF (Undergraduate Research & Fellowships) - https://urf.columbia.edu
Global Programs - https://globalcenters.columbia.edu
GSAS Fellowships - https://gsas.columbia.edu/content/internal-fellowships
Center for Career Education - https://www.careereducation.columbia.edu
Individual department pages (CS, Econ, etc.)

Commands to Run
bash# Initialize project
mkdir opportunity-finder && cd opportunity-finder
mkdir -p scrapers data docs .github/workflows

# Install dependencies
pip install requests beautifulsoup4

# Run scraper locally
python scrapers/mei_scraper.py

# Test frontend locally
python -m http.server 8000 -d docs
# Then open http://localhost:8000

# Deploy
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/USERNAME/opportunity-finder.git
git push -u origin main
# Then enable GitHub Pages in repo settings (source: main, folder: /docs)
Key Design Decisions

No database - JSON committed to repo. Simple, free, version-controlled.
No backend - Static site, scrapers run via GitHub Actions.
Tags inferred automatically - Can be manually corrected in JSON if wrong.
One scraper per source - Easy to maintain, fix one without breaking others.
Deduplication by ID - ID generated from name + source, stable across scrapes.

Success Metrics

Students can find relevant opportunities in < 30 seconds
Filters actually narrow results usefully
Site loads fast (< 1s)
Data stays fresh (daily updates)

Resume Framing
When this is live with real users:
Columbia Opportunity Finder
Creator & Developer

- Built web scraping pipeline aggregating 100+ funded opportunities 
  from 10+ Columbia departments into searchable interface
- Implemented automated daily data refresh via GitHub Actions
- Designed filtering system by eligibility (citizenship, level, type)
- Onboarded 200+ student users in first semester

Start Here

Create the project structure
Build the MEI scraper first
Create the frontend with sample data
Test locally
Deploy to GitHub Pages
Add more scrapers incrementally
# CS Bet Scanner

Automated football odds scanner for the Crypto Sensei ORDER betting system.
Runs every 4 hours via GitHub Actions and writes `results/latest.json` — the Cowork "CS Bet Scanner" skill reads that file and delivers a formatted report.

## How it works

1. GitHub Actions triggers `scanner.py` every 4 hours (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
2. The script queries [The Odds API](https://the-odds-api.com) for all active soccer leagues
3. It checks every upcoming match (next 24 hours) against Methods 1, 2, and 3 of the CS ORDER system
4. Results are committed to `results/latest.json` in this repo
5. The Cowork skill fetches that file and delivers the report to you

## Setup (one time)

### Step 1 — Get a free API key
1. Go to [the-odds-api.com](https://the-odds-api.com) and sign up for a free account
2. Copy your API key from the dashboard
3. Free tier: 500 requests/month (well within the ~180 scans/month this runs)

### Step 2 — Create this repo on GitHub
1. Go to [github.com/new](https://github.com/new)
2. Name it `cs-bet-scanner`
3. Set it to **Public** (required for the raw JSON URL to be accessible without auth)
4. Do NOT initialize with README (you already have one)
5. Copy the remote URL shown

### Step 3 — Push this repo
Open GitHub Desktop, click "Add" → "Add Existing Repository", point to this folder, then publish.

Or via terminal:
```bash
git remote add origin https://github.com/YOUR_USERNAME/cs-bet-scanner.git
git push -u origin main
```

### Step 4 — Add the API key as a secret
1. On GitHub: go to your repo → Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: `ODDS_API_KEY`
4. Value: your API key from Step 1
5. Click "Add secret"

### Step 5 — Enable Actions
GitHub Actions may need to be manually enabled on a new repo.
Go to the "Actions" tab in your repo and click "I understand my workflows, go ahead and enable them."

### Step 6 — Update the Cowork skill
In the CS Bet Scanner skill, replace `GITHUB_USERNAME` in the raw JSON URL with your actual GitHub username:
```
https://raw.githubusercontent.com/YOUR_USERNAME/cs-bet-scanner/main/results/latest.json
```

## Running manually
```bash
export ODDS_API_KEY=your_key_here
pip install requests
python scanner.py
```

## Betting system summary

| Method | Bet | Criteria |
|--------|-----|----------|
| 2 (SAFER) | Over 1.5 Goals | Over 1.5 @ 1.25–1.28 AND Under 1.5 @ 3.00+ |
| 1 (Standard) | Home Win | Home/Away must match a bracket row (see scanner.py) |
| 3 (Experimental) | 3 simultaneous tickets | Home ≥ 8.00; verify Away-by-1 @ 3.00+ on your book |

Ticket rules: 2–3 picks, combined odds 2.00–2.30. Never force below 2.00.

Bankroll sequence (consecutive losses → stake multiplier): 1× → 3× → 5× → 10× → 20× → 40× → 80×. Reset to 1× after any win. Recommended bankroll: 160× base stake.

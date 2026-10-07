# CreatorScout

Finds and scores regional gaming micro-influencers across YouTube, TikTok and Instagram, so a small team can build an outreach list in minutes instead of days.

**[Live demo](https://samir-bk-prompt-hackathon-app-ho7jn7.streamlit.app/)** · Built for [Prenew](https://prenew.com)'s European refurbished gaming PC marketplace · [Hackathon name, date, solo/team, result]

![CreatorScout dashboard](docs/screenshot.png)

## The problem

Prenew wants to partner with small, local creators in markets like Finland and Germany. Two things make that hard:

- **Language.** Local creators title videos in their own language (`halpa pelikone`, `günstiger gaming pc`), so English searches miss most of them.
- **Manual work.** Checking each creator's reach, activity and fit by hand doesn't scale.

## What it does

1. **Translates** a search brief ("budget pc build") into 8+ European languages.
2. **Collects** public creator data from YouTube, TikTok and Instagram.
3. **Calculates** average views over 30 and 90 days, so one viral video doesn't make a creator look better than they are.
4. **Scores** each creator 0-100 with an LLM that reads their transcripts, spots their niche, and flags risks.
5. **Exports** a CSV (metrics, bio email, country, fit score) ready for outreach.

## How it works

```
Search brief -> Translate to 8+ languages -> Collect public data (YT / TikTok / IG)
-> Clean + 30d/90d view averages -> LLM scoring (with fallback models) -> Dashboard + CSV
```

- **Scoring with fallback:** requests go to a primary Groq model and automatically fall back to smaller ones if it fails or is rate-limited.
- **Why windowed averages:** a creator with one 2M-view video and nothing else looks great on a total, but not on a 30-day average.

## Tech stack

| Tool | What it does here |
|---|---|
| Streamlit | Dashboard and deployment (Streamlit Cloud) |
| ytscrape | YouTube channel data, view counts and transcripts |
| requests + BeautifulSoup | TikTok page data |
| ddgs (DuckDuckGo search) | Finds public Instagram profiles and Reels |
| pandas | Cleaning, 30/90-day view averages, CSV export |
| Groq API | LLM fit scoring with model fallback |
| Cursor, Gemini, Claude | AI tools used while building |

## Run it locally

```bash
git clone https://github.com/Samir-BK/CreatorScout.git
cd CreatorScout
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
echo 'GROQ_API_KEY="your-key"' > .env
streamlit run app.py
```

## Limitations

- Collection relies on public pages and search indexes, so it can break when a platform changes its layout. A production version should use the official platform APIs.
- LLM scores are a first-pass ranking, not a verdict. A human should review the shortlist.
- [Anything else you noticed: accuracy, speed, missing data.]

## Next steps

- Send outreach emails directly from the app (Gmail/Outlook).
- Track which creators convert, to improve the scoring.

# CreatorScout

Finds and scores regional gaming micro-influencers across YouTube, TikTok, and Instagram, enabling small teams to build targeted outreach lists in minutes instead of days.

[![Live Demo](https://img.shields.io/badge/Live_Demo-Streamlit-FF4B4B?style=for-the-badge&logo=streamlit&logoColor=white)](https://samir-bk-prompt-hackathon-app-ho7jn7.streamlit.app/)

---

## Screenshots

<p align="center">
  <img width="1440" alt="CreatorScout Dashboard Overview" src="https://github.com/user-attachments/assets/c5ff8758-6650-479c-9740-2f6a79c1daaa" />
</p>

<p align="center">
  <img width="1440" alt="CreatorScout Influencer Scoring Details" src="https://github.com/user-attachments/assets/a54febcb-fe93-4265-a875-82d08efe8b5e" />
</p>

---

## The Problem

Partnering with regional micro-creators in local European markets (e.g., Finland, Germany) presents two major challenges:

- **Language Barriers:** Local creators title videos in their native language (`halpa pelikone`, `günstiger gaming pc`), rendering English searches ineffective.
- **Manual Overhead:** Vetting individual creator metrics, engagement, and content alignment by hand does not scale.

---

## What It Does

1. **Multi-Language Search:** Translates a search brief (e.g., *"budget PC build"*) into 8+ European languages automatically.
2. **Multi-Platform Scraping:** Collects public creator data across YouTube, TikTok, and Instagram.
3. **Rolling Averages:** Calculates 30-day and 90-day average view counts to filter out creators inflated by single viral hits.
4. **AI-Powered Fit Scoring:** Analyzes video transcripts, content niches, and risk factors using LLMs to score creators from 0–100.
5. **CSV Export:** Generates an actionable CSV containing metrics, bio/contact emails, country data, and AI fit scores.

---

## Workflow Architecture

```text
Search Brief
   │
   ▼
Translate Brief (8+ Languages)
   │
   ▼
Data Collection (YouTube / TikTok / Instagram)
   │
   ▼
Data Cleaning & Windowed Averages (30d / 90d Views)
   │
   ▼
LLM Scoring & Risk Analysis (With Model Fallbacks)
   │
   ▼
Streamlit Dashboard ──► Export CSV
```

### Key Technical Decisions

- **LLM Model Fallback System:** Requests target a primary Groq model and automatically cascade to secondary models during rate limits or API outages.
- **Windowed Metrics over Total Counts:** Evaluates sustained viewer engagement rather than vanity totals to accurately assess audience quality.

---

## Tech Stack

| Tool / Library | Usage |
| --- | --- |
| Streamlit | Web application dashboard and cloud deployment |
| ytscrape | Fetches YouTube channel metadata, view counts, and transcripts |
| requests + BeautifulSoup | Scrapes public TikTok metadata |
| ddgs | Discovers public Instagram profiles and Reels via DuckDuckGo Search |
| pandas | Data manipulation, rolling 30/90-day view metrics, and CSV generation |
| Groq API | High-speed LLM inference for fit scoring and transcript analysis |
| Cursor / Claude / Gemini | AI development tools utilized during development |

---

## Local Setup

### 1. Clone the repository

```bash
git clone https://github.com/Samir-BK/Prompt-Hackathon.git
cd Prompt-Hackathon
```

### 2. Set up a virtual environment

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```bash
echo 'GROQ_API_KEY="your_groq_api_key_here"' > .env
```

### 5. Launch the application

```bash
streamlit run app.py
```

---

## Current Limitations

- **Web Scraping Dependency:** Relies on public HTML structures and search indexes, which are vulnerable to layout updates. Official APIs should be integrated for production use.
- **LLM Ranking Nature:** AI scores serve as an automated preliminary filter; manual review of shortlisted candidates remains recommended.
- **Rate Limits:** Rapid sequential searches may hit rate limits on search engine scraping modules.

---

## Roadmap

- [ ] Direct email outreach integration via Gmail / Outlook API
- [ ] Conversion tracking pipeline to refine LLM scoring prompts over time
- [ ] Extended support for Twitch and X (Twitter) profile discovery

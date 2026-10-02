# Prenew Creator Discovery & Outreach Engine

> **Unblockable, real-time multi-platform influencer harvesting and AI scoring engine for Prenew's European refurbished gaming PC marketplace.**

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://samir-bk-prompt-hackathon-app-ho7jn7.streamlit.app/)
![Python Version](https://img.shields.io/badge/Python-3.12-blue)
![Groq Multi-Model](https://img.shields.io/badge/Groq-Multi--Model-orange)

---

## 📌 Overview

Expanding **Prenew** across Europe requires finding hyper-relevant regional micro-influencers in target EU markets (e.g., Finland, Germany). Traditional creator discovery tools fail due to two core bottlenecks:
1. **Language Fragmentation:** Searching in English misses ~80% of local creators who title videos in native languages (e.g., Finnish `halpa pelikone` or German `günstiger gaming pc`).
2. **Security & Platform Walls:** TikTok and Instagram aggressively block standard web automation (Playwright/Selenium) with captchas and 302 login redirects.

**Prenew Creator Discovery Engine** solves this by combining a **Native Multilingual Matrix**, **zero-overhead unblockable search index harvesting**, **30d/90d view windowing**, and a **Groq Multi-Model LLM Tuple** to find, score, and output CRM-ready CSV campaigns in seconds.

---

## 🚀 Key Features

* **🌐 Native Multilingual Translation Matrix:** Automatically translates core hardware search briefs (e.g., "budget pc build") into 8+ European languages prior to executing platform searches.
* **⚡ Zero-Overhead Unblockable Scrapers:**
  * **YouTube (`ytscrape`):** Direct HTTP request extraction for channel metadata, view metrics, and video transcripts without headless browser overhead.
  * **TikTok (`__UNIVERSAL_DATA_FOR_REHYDRATION__`):** Extracts server-rendered background scope data directly from HTML, bypassing login walls and captchas.
  * **Instagram (`ddgs`):** Harvests public DuckDuckGo search indexes to retrieve live Reel handles, metrics, and bio contact details without account session bans.
* **📊 Smart Engagement Windowing:** Calculates normalized 30-day (active) and 90-day (less active) view averages to filter out one-hit viral anomalies.
* **🤖 Multi-Model AI Scoring Tuple:** Uses a resilient Groq LLM routing architecture (`openai/gpt-oss-120b` → `qwen/qwen3.8-27b` → `allam-2-7b`) with automatic fallback to evaluate creator transcripts, detect sub-niches, perform risk analysis, and output a 0–100 match score.
* **📁 1-Click CRM CSV Export:** Aggregates scraped metrics, parsed business bio emails, country origins, and AI fit scores into a downloadable CSV for immediate sales outreach.

---

## 🏗️ Architecture

```
[ Search Brief ]
       │
       ▼
[ 1. Query Translation Matrix ] ──► (Translates query into 8+ EU languages)
       │
       ▼
[ 2. Unblockable Multi-Platform Harvest ]
       ├── YouTube (`ytscrape` direct HTTP & transcripts)
       ├── TikTok (Server-rendered JSON scope parsing)
       └── Instagram (`ddgs` DuckDuckGo index harvesting)
       │
       ▼
[ 3. Metric Engine & Cleaning ] ──► (Calculates 30d/90d view averages & parses bio emails)
       │
       ▼
[ 4. Groq Multi-Model AI Scorer ]
       └── Primary: `openai/gpt-oss-120b`
       └── Fallback 1: `qwen/qwen3.8-27b`
       └── Fallback 2: `allam-2-7b`
       │
       ▼
[ 5. Dashboard & CSV Export ] ──► (Instant CSV download for CRM import)
```

---

## 🛠️ Tech Stack

* **Frontend / UI:** Streamlit
* **Language:** Python 3.12
* **Scraping Architecture:** `ytscrape`, `duckduckgo_search` (`ddgs`), `requests`, `BeautifulSoup4`
* **AI & LLM Orchestration:** Groq API SDK (`openai/gpt-oss-120b`, `qwen/qwen3.8-27b`, `allam-2-7b`)
* **Data Processing:** Pandas

---

## 💻 Local Installation & Setup

1. **Clone the Repository:**
   ```bash
   git clone https://github.com/Samir-BK/Prompt-Hackathon.git
   cd Prompt-Hackathon
   ```

2. **Create and Activate a Virtual Environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install Dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Environment Variables:**
   Create a `.env` file or configure Streamlit secrets (`.streamlit/secrets.toml`):
   ```env
   GROQ_API_KEY="your-groq-api-key"
   ```

5. **Run the Application:**
   ```bash
   streamlit run app.py
   ```

---

## 🔮 Roadmap

- [ ] Direct Gmail & Outlook API integration for 1-click email sending.
- [ ] Enterprise proxy rotation for high-volume multi-market batch processing.
- [ ] Storefront conversion tracking hooks to measure promo code ROI across Prenew's marketplace.

---

## 🔗 Live Deployment

The application is deployed live on Streamlit Cloud:  
👉 **[Launch App](https://samir-bk-prompt-hackathon-app-ho7jn7.streamlit.app/)**

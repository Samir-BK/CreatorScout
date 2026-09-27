import csv
import io
from datetime import date

import streamlit as st

from modules.discovery import (
    search_micro_influencers,
    EUROPEAN_COUNTRIES,
    EU_COUNTRIES,
    EU_SWEEP_REGIONS,
)
from modules.tiktok_discovery import search_tiktok_micro_influencers
from modules.insta_discovery import search_instagram_micro_influencers
from modules.scorer import score_creator_fit

CSV_FIELDS = [
    "platform", "channel_name", "channel_handle", "channel_url",
    "country", "country_code", "country_verified", "in_eu",
    "subscribers", "avg_views", "avg_views_window_days", "avg_views_sample_size",
    "activity_level", "uploads_per_month", "trend", "views_to_subs_ratio",
    "video_title", "video_url", "recent_video_views",
    "niche_hints", "games_detected", "detected_niche",
    "contact_email", "contact_links",
    "risk_flags", "risk_factors", "trend_factor", "fit_reasoning", "relevance_score",
    "channel_description", "transcript_sample",
]


def utf8_text(value: object) -> str:
    """Text that can be encoded as UTF-8.

    Scraped titles and transcripts sometimes contain lone UTF-16 surrogates.
    Those cannot be encoded for the CSV download. Valid surrogate pairs are
    restored to characters; anything still invalid is replaced.
    """
    text = "" if value is None else str(value)
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        text = text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")
    return text


def clean_creator(creator: dict) -> dict:
    cleaned: dict = {}
    for key, value in creator.items():
        if isinstance(value, str):
            cleaned[key] = utf8_text(value)
        elif isinstance(value, list):
            cleaned[key] = [utf8_text(item) if isinstance(item, str) else item for item in value]
        elif isinstance(value, dict):
            cleaned[key] = {
                utf8_text(item_key) if isinstance(item_key, str) else item_key: (
                    utf8_text(item) if isinstance(item, str) else item
                )
                for item_key, item in value.items()
            }
        else:
            cleaned[key] = value
    return cleaned


def creators_to_csv(creators: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    for creator in creators:
        row = {}
        for field in CSV_FIELDS:
            value = creator.get(field)
            if isinstance(value, list):
                value = "; ".join(utf8_text(item) for item in value)
            elif isinstance(value, dict):
                value = "; ".join(f"{utf8_text(key)}: {utf8_text(item)}" for key, item in value.items())
            elif isinstance(value, bool):
                value = "yes" if value else "no"
            elif isinstance(value, str):
                value = utf8_text(value)
            row[field] = "" if value is None else value
        writer.writerow(row)
    return buffer.getvalue()

# Page Setup
st.set_page_config(page_title="Prenew | Creator Discovery Engine", layout="wide", page_icon="🎮")

st.title("🎮 Prenew: Automated Micro-Influencer Engine")
st.caption("Automated creator discovery and transcript relevance scoring across Europe.")

# Sidebar Controls
st.sidebar.header("🔍 Discovery Parameters")

LIVE_SCRAPERS = {
    "YouTube (Live Scraper)": (search_micro_influencers, "Searching YouTube & extracting transcripts via ytscrape..."),
    "TikTok (Live Scraper)": (search_tiktok_micro_influencers, "Harvesting TikTok creators via search index & public profile pages..."),
    "Instagram (Live Scraper)": (search_instagram_micro_influencers, "Harvesting Instagram creators via search index & public profile pages..."),
}
platform = st.sidebar.selectbox("Target Platform", list(LIVE_SCRAPERS))
keyword = st.sidebar.text_input("Target Keyword / Niche", value="budget gaming pc build")

st.sidebar.subheader("Filter Settings")
if "candidate_count" not in st.session_state:
    st.session_state["candidate_count"] = 3


def _remember_candidate_count() -> None:
    """Keep the slider and the typed count on the same number."""
    if st.session_state.get("any_candidate_count"):
        st.session_state["candidate_count"] = int(st.session_state["candidate_count_input"])
    else:
        st.session_state["candidate_count"] = int(st.session_state["candidate_count_slider"])


def _switch_candidate_mode() -> None:
    """Copy the current count into whichever control is about to be shown."""
    count = int(st.session_state["candidate_count"])
    if st.session_state.get("any_candidate_count"):
        st.session_state["candidate_count_input"] = max(1, count)
    else:
        shown = min(10, max(1, count))
        st.session_state["candidate_count_slider"] = shown
        st.session_state["candidate_count"] = shown


any_candidate_count = st.sidebar.checkbox(
    "Any number of candidates",
    key="any_candidate_count",
    on_change=_switch_candidate_mode,
    help="Turn this on to type any number of creators. The typed number and the slider stay on the same count.",
)
if any_candidate_count:
    st.session_state["candidate_count_input"] = max(1, int(st.session_state["candidate_count"]))
    max_results = int(st.sidebar.number_input(
        "Max Candidates",
        min_value=1,
        step=1,
        key="candidate_count_input",
        on_change=_remember_candidate_count,
        help="Type how many creators to fetch. Turn the option off to use the 1–10 slider.",
    ))
else:
    st.session_state["candidate_count_slider"] = min(10, max(1, int(st.session_state["candidate_count"])))
    max_results = int(st.sidebar.slider(
        "Max Candidates",
        min_value=1,
        max_value=10,
        key="candidate_count_slider",
        on_change=_remember_candidate_count,
    ))
st.session_state["candidate_count"] = int(max_results)
max_views = st.sidebar.number_input("Max Avg Views / Video", value=150000, step=10000)
min_views = st.sidebar.number_input("Min Avg Views / Video", value=1000, step=1000)
min_subscribers = st.sidebar.number_input("Min Subscribers", value=1000, step=1000)
max_subscribers = st.sidebar.number_input("Max Subscribers", value=250000, step=10000)

def countries_to_search(selected: list[str]) -> list[str] | None:
    """Country codes to sweep. None keeps the default main-market list.

    Specific countries replace the broad EU option, so a Germany selection
    searches Germany even if "All main EU markets" is still highlighted.
    """
    specific = [code for code in selected if code != "EU"]
    if specific:
        return specific
    return None


def reconcile_regions(current: list[str], previous: list[str]) -> list[str]:
    """Keep "all EU markets" from sitting alongside a specific country."""
    added = [code for code in current if code not in previous]
    if "EU" in added and len(current) > 1:
        return ["EU"]
    if any(code != "EU" for code in added) and "EU" in current:
        return [code for code in current if code != "EU"]
    return current


def region_file_slug(selected: list[str]) -> str:
    sweep = countries_to_search(selected)
    if sweep is None:
        return "eu"
    return "-".join(code.lower() for code in sweep)


region_options = ["EU"] + sorted(EUROPEAN_COUNTRIES)
if "target_regions" not in st.session_state:
    st.session_state["target_regions"] = ["EU"]
    st.session_state["_regions_prev"] = ["EU"]


def _sync_regions() -> None:
    current = list(st.session_state["target_regions"])
    previous = list(st.session_state.get("_regions_prev") or [])
    st.session_state["target_regions"] = reconcile_regions(current, previous)
    st.session_state["_regions_prev"] = list(st.session_state["target_regions"])


selected_regions = st.sidebar.multiselect(
    "Target regions",
    region_options,
    format_func=lambda c: "All main EU markets" if c == "EU"
    else f"{c} — {EUROPEAN_COUNTRIES[c]}" + ("" if c in EU_COUNTRIES else " (non-EU)"),
    placeholder="Choose one or more countries",
    help="Choose one or more countries. All main EU markets searches Germany, France, the Netherlands, Poland, Sweden, Finland, Spain, Italy, Denmark, and Austria. Picking a country searches only that country.",
    key="target_regions",
    on_change=_sync_regions,
)
require_verified_country = st.sidebar.checkbox("Only channels with a verified European country", value=False)

# Main Action Button
if st.button("🚀 Run Discovery & Scoring Engine"):
    if not selected_regions:
        st.error("Select at least one target region.")
    else:
        scraper, spinner_text = LIVE_SCRAPERS[platform]
        with st.spinner(spinner_text):
            raw_candidates = scraper(
                keyword=keyword,
                max_results=max_results,
                max_views=max_views,
                min_views=min_views,
                region="EU",
                sweep_regions=countries_to_search(selected_regions),
                min_subscribers=min_subscribers,
                max_subscribers=max_subscribers,
                require_verified_country=require_verified_country,
            )
            
        if not raw_candidates:
            st.error("No creators found within the specified view filters.")
        else:
            st.success(f"Fetched {len(raw_candidates)} creators. Scoring brand fit using Groq LLM...")
            
            scored_candidates = []
            progress_bar = st.progress(0)
            
            for idx, creator in enumerate(raw_candidates):
                score_data = score_creator_fit(creator)
                creator.update(score_data)
                scored_candidates.append(creator)
                progress_bar.progress((idx + 1) / len(raw_candidates))
                
            # Sort by relevance score descending
            scored_candidates = sorted(scored_candidates, key=lambda x: x.get("relevance_score", 0), reverse=True)
            st.session_state["results"] = scored_candidates
            st.session_state["results_meta"] = {
                "platform": platform.split(" ")[0].lower(),
                "region": region_file_slug(selected_regions),
                "keyword": keyword,
            }

# Render Results
if "results" in st.session_state and st.session_state["results"]:
    results = [clean_creator(creator) for creator in st.session_state["results"]]
    st.divider()
    heading, save_col = st.columns([3, 1])
    heading.subheader("Scored creator candidates")
    meta = st.session_state.get("results_meta") or {}
    filename = f"prenew_{meta.get('platform', 'creators')}_{meta.get('region', 'eu')}_{date.today().isoformat()}.csv"
    save_col.download_button(
        "Save as CSV",
        data=creators_to_csv(results),
        file_name=filename,
        mime="text/csv",
        icon=":material/download:",
        width="stretch",
    )

    for idx, creator in enumerate(results):
        score = creator.get("relevance_score", 0)
        
        # Color badge based on score
        badge_color = "🟢" if score >= 75 else "🟡" if score >= 50 else "🔴"
        
        country_label = creator.get('country') or creator.get('target_region', 'Unknown')
        if creator.get('country_verified') is False:
            country_label += " (unverified)"

        with st.expander(f"{badge_color} #{idx+1} {creator.get('channel_name')} | {country_label} | Score: {score}/100 | Niche: {creator.get('detected_niche')}"):
            subs = creator.get('subscribers')
            avg_views = creator.get('avg_views')
            window = creator.get('avg_views_window_days')
            m1, m2, m3 = st.columns(3)
            m1.metric("Subscribers", f"{subs:,}" if isinstance(subs, int) else (creator.get('subscribers_text') or "Hidden"))
            m2.metric(f"Avg views ({window}d)" if window else "Avg views (last uploads)",
                      f"{avg_views:,}" if isinstance(avg_views, int) else "N/A")
            m3.metric("Uploads / month", creator.get('uploads_per_month', "N/A"))

            channel_url = creator.get('channel_url')
            if channel_url:
                st.write(f"**Channel:** [{creator.get('channel_handle') or creator.get('channel_name')}]({channel_url})")
            st.write(f"**Matched Video:** [{creator.get('video_title')}]({creator.get('video_url')})")
            views = creator.get('views') or creator.get('recent_video_views')
            if isinstance(views, int):
                st.write(f"**Matched Video Views:** {views:,}")
            st.write(f"**Activity:** {creator.get('activity_level', 'N/A')} | **Trend:** {creator.get('trend', 'N/A')}")
            if creator.get('games_detected'):
                st.write(f"**Games:** {', '.join(creator['games_detected'])}")
            if creator.get('niche_hints'):
                st.write(f"**Topics:** {', '.join(creator['niche_hints'])}")

            st.write(f"**Contact:** `{creator.get('contact_email', 'N/A')}`")
            links = creator.get('contact_links') or {}
            if links:
                st.write(" | ".join(f"[{name}]({url})" for name, url in links.items()))

            if creator.get('risk_factors'):
                st.warning(f"**Risks:** {creator.get('risk_factors')}")
            elif creator.get('risk_flags'):
                st.warning(f"**Risks:** {', '.join(creator['risk_flags'])}")
            if creator.get('trend_factor'):
                st.write(f"**Trend analysis:** {creator.get('trend_factor')}")
            st.info(f"**AI Reason:** {creator.get('fit_reasoning')}")
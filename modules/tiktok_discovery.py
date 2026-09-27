"""
TikTok micro-influencer discovery for Prenew's European market.

TikTok blocks Playwright/msToken sessions, so this module never touches
TikTok's signed APIs. Instead it:

1. Finds creators through the DuckDuckGo/Bing search index (site:tiktok.com),
   using the same per-country localized queries as the YouTube scraper.
2. Reads each creator's public profile page, matched video page and creator
   embed page. All three server-render JSON that a plain HTTP request can parse:
     - profile  -> followers, hearts, video count, bio, bio link, region
     - video    -> play count, timestamp, duration, hashtags, locationCreated
     - embed    -> the ~13 most recent videos with play counts
3. Derives upload dates from video IDs (TikTok IDs are Snowflake-style; the
   upper 32 bits are unix seconds), which allows 30d / 90d view averages
   without extra requests.

The returned dictionaries use exactly the same keys as
``modules.discovery.search_micro_influencers`` so the scorer, outreach and UI
layers treat both platforms identically.
"""

import json
import re
import time
from typing import Any, Dict, Iterable, List, Optional

import requests
from ddgs import DDGS

from modules.discovery import (
    EU_COUNTRIES,
    EU_SWEEP_REGIONS,
    EUROPEAN_COUNTRIES,
    GAME_KEYWORDS,
    LOCAL_SEARCH_LANGUAGE,
    TOPIC_KEYWORDS,
    accepts_search_country,
    build_risk_flags,
    compute_view_stats,
    detect_terms,
    extract_email,
    localize_keyword,
    region_room,
)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml",
}
_REQUEST_PAUSE_SECONDS = 0.6

_HANDLE_RE = re.compile(r"tiktok\.com/@([\w.-]+)")
_VIDEO_ID_RE = re.compile(r"/video/(\d{15,})")
_REHYDRATION_RE = re.compile(
    r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__" type="application/json">(.*?)</script>', re.S
)
_FRONTITY_RE = re.compile(r'<script id="__FRONTITY_CONNECT_STATE__"[^>]*>(.*?)</script>', re.S)

# DuckDuckGo region codes are "<country>-<language>"; a few don't follow the ISO code.
_DDGS_REGION_OVERRIDES = {"GB": "uk-en", "SE": "se-sv", "DK": "dk-da", "CZ": "cz-cs",
                          "GR": "gr-el", "SI": "si-sl", "EE": "ee-et", "NO": "no-no"}


# ---------------------------------------------------------------------------
# Low-level fetchers
# ---------------------------------------------------------------------------

def _ddgs_region(code: str) -> str:
    if code in _DDGS_REGION_OVERRIDES:
        return _DDGS_REGION_OVERRIDES[code]
    return f"{code.lower()}-{LOCAL_SEARCH_LANGUAGE.get(code, 'en')}"


def _get(session: requests.Session, url: str) -> Optional[str]:
    try:
        response = session.get(url, headers=_HEADERS, timeout=20)
        time.sleep(_REQUEST_PAUSE_SECONDS)
        if response.status_code != 200:
            return None
        return response.text
    except requests.RequestException:
        return None


def _rehydration_scope(html: Optional[str]) -> Dict[str, Any]:
    if not html:
        return {}
    match = _REHYDRATION_RE.search(html)
    if not match:
        return {}
    try:
        return json.loads(match.group(1)).get("__DEFAULT_SCOPE__", {})
    except json.JSONDecodeError:
        return {}


def _find(node: Any, key: str) -> Any:
    if isinstance(node, dict):
        if key in node:
            return node[key]
        for value in node.values():
            found = _find(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find(item, key)
            if found is not None:
                return found
    return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def video_id_to_unix(video_id: str) -> Optional[int]:
    """TikTok video IDs are Snowflake-style: upper 32 bits = creation unix time."""
    vid = _to_int(video_id)
    return vid >> 32 if vid else None


def fetch_profile(session: requests.Session, handle: str) -> Optional[Dict]:
    scope = _rehydration_scope(_get(session, f"https://www.tiktok.com/@{handle}"))
    detail = scope.get("webapp.user-detail", {})
    info = detail.get("userInfo") if detail.get("statusCode") == 0 else None
    if not info:
        return None
    user, stats = info.get("user", {}), info.get("stats", {})
    return {
        "handle": user.get("uniqueId") or handle,
        "nickname": user.get("nickname"),
        "sec_uid": user.get("secUid"),
        "bio": user.get("signature") or "",
        "bio_link": (user.get("bioLink") or {}).get("link"),
        "region": user.get("region"),
        "verified": bool(user.get("verified")),
        "created_unix": _to_int(user.get("createTime")),
        "followers": _to_int(stats.get("followerCount")),
        "hearts": _to_int(stats.get("heartCount") or stats.get("heart")),
        "video_count": _to_int(stats.get("videoCount")),
    }


def fetch_video(session: requests.Session, handle: str, video_id: str) -> Optional[Dict]:
    scope = _rehydration_scope(_get(session, f"https://www.tiktok.com/@{handle}/video/{video_id}"))
    detail = scope.get("webapp.video-detail", {})
    item = detail.get("itemInfo", {}).get("itemStruct") if detail.get("statusCode") == 0 else None
    if not item:
        return None
    stats = item.get("statsV2") or item.get("stats") or {}
    return {
        "video_id": item.get("id") or video_id,
        "desc": item.get("desc") or "",
        "created_unix": _to_int(item.get("createTime")),
        "views": _to_int(stats.get("playCount")) or 0,
        "likes": _to_int(stats.get("diggCount")) or 0,
        "comments": _to_int(stats.get("commentCount")) or 0,
        "duration": _to_int((item.get("video") or {}).get("duration")),
        "location_created": item.get("locationCreated"),
        "hashtags": [t.get("hashtagName") for t in item.get("textExtra", []) if t.get("hashtagName")],
    }


def fetch_recent_videos(session: requests.Session, handle: str, limit: int = 30) -> List[Dict]:
    """
    Reads the creator embed page, which lists the newest videos with play
    counts. Returns [{video_id, title, views, age_days}] compatible with
    ``compute_view_stats``.
    """
    html = _get(session, f"https://www.tiktok.com/embed/@{handle}")
    if not html:
        return []
    match = _FRONTITY_RE.search(html)
    if not match:
        return []
    try:
        state = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []

    video_list = _find(state, "videoList") or []
    now = time.time()
    uploads: List[Dict] = []
    for item in video_list:
        created = video_id_to_unix(item.get("id"))
        views = _to_int(item.get("playCount"))
        if created is None or views is None:
            continue
        uploads.append({
            "video_id": item.get("id"),
            "title": item.get("desc") or "",
            "views": views,
            "age_days": max(0, int((now - created) // 86400)),
        })
        if len(uploads) >= limit:
            break
    uploads.sort(key=lambda u: u["age_days"])
    return uploads


# ---------------------------------------------------------------------------
# Search index harvesting
# ---------------------------------------------------------------------------

_SEARCH_BACKENDS = ("auto", "duckduckgo", "bing")


def _query_variants(keyword: str, code: str) -> List[str]:
    """
    Ordered search phrases: full local translation, a shorter local phrase
    (long exact phrases rarely exist in the index), then English with and
    without the country name. Never quoted; exact-phrase matching is too strict.
    """
    lang = LOCAL_SEARCH_LANGUAGE.get(code, "en")
    local = localize_keyword(keyword, lang)
    variants = []
    if local:
        variants.append(local)
        short = " ".join(local.split()[:3])
        if short != local:
            variants.append(short)
    variants.append(f"{keyword} {EUROPEAN_COUNTRIES[code]}")
    variants.append(keyword)
    return list(dict.fromkeys(variants))


def search_index(keyword: str, code: str, max_results: int) -> List[Dict]:
    """
    Queries the search index for TikTok pages, trying local-language phrases
    first and cycling through backends/regions until enough TikTok URLs are
    found. Returns [{handle, video_id, url, title, snippet}].
    """
    hits: List[Dict] = []
    seen_urls: set = set()

    def collect(results: Iterable[Dict]) -> None:
        for item in results or []:
            url = item.get("href", "")
            handle_match = _HANDLE_RE.search(url)
            if not handle_match or url in seen_urls:
                continue
            seen_urls.add(url)
            video_match = _VIDEO_ID_RE.search(url)
            hits.append({
                "handle": handle_match.group(1),
                "video_id": video_match.group(1) if video_match else None,
                "url": url.split("?")[0],
                "title": (item.get("title") or "").replace(" | TikTok", "").replace(" - TikTok", "").strip(),
                "snippet": item.get("body") or "",
            })

    for query in _query_variants(keyword, code):
        for region in (_ddgs_region(code), "wt-wt"):
            for backend in _SEARCH_BACKENDS:
                try:
                    results = DDGS().text(f"site:tiktok.com {query}", region=region,
                                          max_results=max_results, backend=backend)
                except Exception:
                    results = []
                time.sleep(0.5)
                if results:
                    collect(results)
                    break  # this backend answered; no need to try the others
            if len(hits) >= max_results:
                return hits
    return hits


# ---------------------------------------------------------------------------
# Public entry point (mirrors modules.discovery.search_micro_influencers)
# ---------------------------------------------------------------------------

def search_tiktok_micro_influencers(
    keyword: str,
    max_results: int = 5,
    max_views: int = 150_000,
    min_views: int = 1_000,
    region: str = "EU",
    language: Optional[str] = None,
    min_subscribers: int = 1_000,
    max_subscribers: int = 250_000,
    require_verified_country: bool = False,
    sweep_regions: Optional[Iterable[str]] = None,
    include_transcripts: bool = True,
) -> List[Dict]:
    """
    Discovers European TikTok micro-influencers with the same parameters and
    output schema as the YouTube scraper. ``subscribers`` holds the follower
    count; ``transcript_sample`` holds the matched video's caption plus recent
    captions, since TikTok exposes no transcripts.
    """
    region = region.upper()
    if region == "EU":
        regions = list(sweep_regions or EU_SWEEP_REGIONS)
    elif region in EUROPEAN_COUNTRIES:
        regions = [region]
    else:
        raise ValueError(
            f"Region {region!r} is outside the European target market. "
            f"Use 'EU' or one of: {', '.join(sorted(EUROPEAN_COUNTRIES))}"
        )

    per_region_limit = min(30, max(10, (max_results * 8) // len(regions)))
    target_pool = max_results * 2

    session = requests.Session()
    seen_handles: set = set()
    profiles: List[Dict] = []
    share_regions = len(regions) if sweep_regions is not None and len(regions) > 1 else 1

    for index, code in enumerate(regions):
        room = region_room(index, len(profiles), target_pool, share_regions)
        if room <= 0:
            break
        country_name = EUROPEAN_COUNTRIES[code]
        added = 0

        for hit in search_index(keyword, code, per_region_limit):
            handle = hit["handle"].lower()
            if handle in seen_handles:
                continue
            seen_handles.add(handle)

            account = fetch_profile(session, handle)
            if not account:
                continue

            followers = account["followers"]
            if followers is not None and not (min_subscribers <= followers <= max_subscribers):
                continue

            # Country: profile region first, then the matched video's locationCreated.
            video = fetch_video(session, handle, hit["video_id"]) if hit["video_id"] else None
            detected = account["region"] or (video or {}).get("location_created")
            detected = detected.upper() if detected else None
            if detected and detected not in EUROPEAN_COUNTRIES:
                continue  # creator explicitly outside Europe
            country_verified = detected is not None
            if require_verified_country and not country_verified:
                continue
            if not accepts_search_country(detected, code):
                continue
            country_code = detected or code

            uploads = fetch_recent_videos(session, handle)
            stats = compute_view_stats(uploads)
            if stats["avg_views"] is not None and not (min_views <= stats["avg_views"] <= max_views):
                continue

            recent_captions = [u["title"] for u in uploads[:15] if u["title"]]
            hashtags = sorted({
                tag.lower()
                for text in [account["bio"], (video or {}).get("desc", ""), *recent_captions]
                for tag in re.findall(r"#(\w+)", text)
            } | set((video or {}).get("hashtags", [])))
            niche_text = " ".join(filter(None, [
                account["nickname"], account["bio"], hit["title"], hit["snippet"],
                (video or {}).get("desc", ""), *recent_captions, " ".join(hashtags),
            ]))

            links: Dict[str, str] = {}
            if account["bio_link"]:
                link = account["bio_link"]
                key = "website"
                for name in ("instagram", "discord", "linktr", "youtube", "twitch", "x.com", "twitter"):
                    if name in link.lower():
                        key = {"linktr": "linktree", "x.com": "x", "twitter": "x"}.get(name, name)
                        break
                links[key] = link

            matched_video_id = (video or {}).get("video_id") or hit["video_id"]
            matched_url = hit["url"] if hit["video_id"] else (
                f"https://www.tiktok.com/@{handle}/video/{matched_video_id}" if matched_video_id else f"https://www.tiktok.com/@{handle}"
            )
            joined = account["created_unix"]

            profile = {
                "platform": "TikTok",
                # Identity
                "channel_name": account["nickname"] or f"@{handle}",
                "channel_handle": f"@{handle}",
                "channel_url": f"https://www.tiktok.com/@{handle}",
                "channel_id": account["sec_uid"] or handle,
                # Geography
                "country": EUROPEAN_COUNTRIES.get(country_code),
                "country_code": country_code,
                "country_verified": country_verified,
                "in_eu": country_code in EU_COUNTRIES,
                "search_region": f"{code} ({country_name})",
                # Audience size
                "subscribers": followers,
                "subscribers_text": f"{followers:,} followers" if followers is not None else None,
                "total_channel_views": None,
                "total_likes": account["hearts"],
                "video_count": account["video_count"],
                "channel_joined": time.strftime("Joined %b %d, %Y", time.gmtime(joined)) if joined else None,
                # Performance
                **stats,
                "views_to_subs_ratio": (
                    round(stats["avg_views"] / followers, 3)
                    if stats["avg_views"] is not None and followers else None
                ),
                # Niche hints (refined by the LLM scorer)
                "niche_hints": detect_terms(niche_text, TOPIC_KEYWORDS),
                "games_detected": detect_terms(niche_text, GAME_KEYWORDS),
                "channel_keywords": hashtags[:15],
                # Contact
                "contact_email": extract_email(account["bio"], (video or {}).get("desc")),
                "contact_links": links,
                # Matched video
                "video_id": matched_video_id,
                "video_title": (video or {}).get("desc") or hit["title"] or f"TikTok by @{handle}",
                "video_url": matched_url,
                "channel_description": account["bio"][:600],
                "recent_video_views": (video or {}).get("views", 0),
                "views": (video or {}).get("views", 0),
                "length_seconds": (video or {}).get("duration"),
                "video_published": (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((video or {})["created_unix"]))
                    if (video or {}).get("created_unix") else None
                ),
            }
            profile["risk_flags"] = build_risk_flags(profile, max_subscribers)

            if include_transcripts:
                caption_block = "\n".join(filter(None, [(video or {}).get("desc", ""), *recent_captions]))
                profile["transcript_sample"] = (caption_block or account["bio"])[:1200]
            else:
                profile["transcript_sample"] = ""
            if not profile["contact_email"]:
                profile["contact_email"] = "N/A (check bio link / TikTok business email button)"

            profiles.append(profile)
            added += 1
            if added >= room or len(profiles) >= target_pool:
                break

    profiles.sort(key=lambda p: (
        not p["country_verified"],
        not p["in_eu"],
        -(p["avg_views"] or 0),
    ))
    return profiles[:max_results]


def get_live_tiktok_creators(keyword: str = "budget gaming pc", max_results: int = 5, **kwargs) -> List[Dict]:
    """Backwards-compatible wrapper used by the Streamlit app."""
    try:
        return search_tiktok_micro_influencers(keyword, max_results=max_results, **kwargs)
    except Exception as e:
        print(f"[TikTok Discovery Warning]: {e}")
        return []

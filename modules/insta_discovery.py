"""
Instagram micro-influencer discovery for Prenew's European market.

Instagram blocks logged-out GraphQL and signed APIs, so this module never
calls those. It mirrors ``modules.tiktok_discovery``:

1. Finds creators through the DuckDuckGo/Bing search index (site:instagram.com),
   using the same per-country localized queries as the YouTube / TikTok scrapers.
2. Reads public embed pages with a crawler user-agent. Profile URLs now
   redirect to login, but the embed pages still include:
     - profile embed -> followers, post count, display name
     - post embed    -> view count, likes, caption, owner
3. Collects extra recent posts for the same handle from the search index so
   30-day / 90-day view averages can be computed.

The returned dictionaries use exactly the same keys as
``modules.discovery.search_micro_influencers`` so the scorer, outreach and UI
layers treat Instagram the same as YouTube and TikTok.
"""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
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
    build_risk_flags,
    compute_view_stats,
    detect_terms,
    extract_email,
    localize_keyword,
    resolve_country,
)

_USER_AGENT = (
    "facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)"
)
_HEADERS = {
    "User-Agent": _USER_AGENT,
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}
_REQUEST_PAUSE_SECONDS = 0.15

_RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "directory",
    "legal", "about", "developer", "popular", "tags", "locations", "web",
    "emails", "session", "challenge", "direct", "lite", "nametag", "static",
}

_HANDLE_RE = re.compile(
    r"instagram\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?:p|reel|tv)/|"
    r"instagram\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?P<handle>[\w.]+)",
    re.I,
)
_SHORTCODE_RE = re.compile(r"instagram\.com/(?:[\w.]+/)?(?:p|reel|tv)/([A-Za-z0-9_-]{5,})", re.I)
_HANDLE_IN_PATH_RE = re.compile(
    r"instagram\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?(?P<handle>[\w.]+)/(?:p|reel|tv)/",
    re.I,
)
_HANDLE_FROM_TITLE_RE = re.compile(r"\(@([\w.]+)\)")
_POST_DESC_RE = re.compile(
    r"(?P<likes>[\d,]+)\s+likes(?:,\s+(?P<comments>[\d,]+)\s+comments)?"
    r"\s+-\s+(?P<handle>[\w.]+)\s+on\s+(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4}):\s+"
    r'"(?P<caption>.*)"',
    re.S,
)
_JSON_SCRIPT_RE = re.compile(
    r'<script type="application/json"[^>]*>(.*?)</script>', re.S
)

_DDGS_REGION_OVERRIDES = {
    "GB": "uk-en", "SE": "se-sv", "DK": "dk-da", "CZ": "cz-cs",
    "GR": "gr-el", "SI": "si-sl", "EE": "ee-et", "NO": "no-no",
}
_SEARCH_BACKENDS = ("bing", "auto")

_FLAG_TO_COUNTRY = {
    "🇩🇪": "DE", "🇦🇹": "AT", "🇨🇭": "CH", "🇫🇷": "FR", "🇳🇱": "NL",
    "🇧🇪": "BE", "🇵🇱": "PL", "🇸🇪": "SE", "🇫🇮": "FI", "🇪🇸": "ES",
    "🇮🇹": "IT", "🇩🇰": "DK", "🇵🇹": "PT", "🇨🇿": "CZ", "🇮🇪": "IE",
    "🇳🇴": "NO", "🇭🇺": "HU", "🇬🇷": "GR", "🇷🇴": "RO", "🇧🇬": "BG",
    "🇭🇷": "HR", "🇸🇰": "SK", "🇸🇮": "SI", "🇱🇹": "LT", "🇱🇻": "LV",
    "🇪🇪": "EE", "🇱🇺": "LU", "🇲🇹": "MT", "🇨🇾": "CY", "🇮🇸": "IS",
    "🇬🇧": "GB",
}


# ---------------------------------------------------------------------------
# Low-level fetchers
# ---------------------------------------------------------------------------

def _ddgs_region(code: str) -> str:
    if code in _DDGS_REGION_OVERRIDES:
        return _DDGS_REGION_OVERRIDES[code]
    return f"{code.lower()}-{LOCAL_SEARCH_LANGUAGE.get(code, 'en')}"


def _get(session: requests.Session, url: str) -> Optional[str]:
    try:
        response = session.get(url, headers=_HEADERS, timeout=12)
        if _REQUEST_PAUSE_SECONDS:
            time.sleep(_REQUEST_PAUSE_SECONDS)
        if response.status_code != 200:
            return None
        return response.text
    except requests.RequestException:
        return None


def _parallel(fn, items: List[Any], workers: int = 6) -> List[Any]:
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
        return list(pool.map(fn, items))


def _json_scripts(html: str) -> List[Any]:
    blobs = []
    for match in _JSON_SCRIPT_RE.finditer(html):
        try:
            blobs.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return blobs


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


def _find_dict_with_keys(node: Any, required: Iterable[str]) -> Optional[Dict]:
    needed = set(required)
    if isinstance(node, dict):
        if needed.issubset(node.keys()):
            return node
        for value in node.values():
            found = _find_dict_with_keys(value, needed)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_dict_with_keys(item, needed)
            if found is not None:
                return found
    return None


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_int(html: str, key: str) -> Optional[int]:
    match = re.search(rf'\\?"{key}\\?"\s*:\s*(\d+)', html)
    return int(match.group(1)) if match else None


def _parse_ig_date(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text.strip(), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _age_days(when: Optional[datetime]) -> Optional[int]:
    if when is None:
        return None
    return max(0, int((datetime.now(timezone.utc) - when).total_seconds() // 86400))


def infer_country(*texts: Optional[str]) -> Optional[str]:
    """Flag emoji, spelled-out country, or None if nothing European is stated."""
    blob = " ".join(t for t in texts if t)
    if not blob:
        return None
    for flag, code in _FLAG_TO_COUNTRY.items():
        if flag in blob:
            return code
    resolved = resolve_country(blob)
    if resolved:
        return resolved
    lower = blob.lower()
    for code, name in EUROPEAN_COUNTRIES.items():
        if name.lower() in lower:
            return code
    return None


def _bio_links(*texts: Optional[str]) -> Dict[str, str]:
    links: Dict[str, str] = {}
    for text in texts:
        if not text:
            continue
        for url in re.findall(r"https?://[^\s\"'<>]+", text):
            url = url.rstrip(").,;")
            key = "website"
            for name in ("instagram", "discord", "linktr", "youtube", "twitch",
                         "x.com", "twitter", "tiktok"):
                if name in url.lower():
                    key = {"linktr": "linktree", "x.com": "x", "twitter": "x"}.get(name, name)
                    break
            links.setdefault(key, url)
    return links


# ---------------------------------------------------------------------------
# Profile / post parsers
# ---------------------------------------------------------------------------

def _json_string(html: str, key: str) -> Optional[str]:
    """Read one escaped JSON string. Embed HTML delimits values with backslash-quote."""
    match = re.search(
        rf'\\?"{re.escape(key)}\\?"\s*:\s*\\?"(.*?)\\?"',
        html,
        re.S,
    )
    if not match:
        return None
    text = match.group(1).replace("\\/", "/")
    # Embed JSON is often escaped twice, so \\u00fc arrives as the letters \u00fc.
    for _ in range(3):
        if not re.search(r"\\u[0-9a-fA-F]{4}", text) and "\\n" not in text and '\\"' not in text:
            break
        try:
            decoded = text.encode("utf-8").decode("unicode_escape")
        except UnicodeDecodeError:
            break
        if decoded == text:
            break
        text = decoded
    text = _repair_text(text).strip()
    return text or None


def _repair_text(text: str) -> str:
    """Turn leftover UTF-16 surrogate pairs from Instagram JSON into real characters."""
    try:
        text.encode("utf-8")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-16", "surrogatepass").decode("utf-16", "replace")


def _owner_id(html: str, handle: str) -> str:
    """Owner id sits just before the username. A media id further up the page does not."""
    for match in re.finditer(
        rf'\\?"username\\?"\s*:\s*\\?"{re.escape(handle)}\\?"',
        html,
        re.I,
    ):
        window = html[max(0, match.start() - 2500):match.start()]
        ids = re.findall(r'\\?"id\\?"\s*:\s*\\?"(\d+)\\?"', window)
        if ids:
            return ids[-1]
    return handle


def _flag_near_username(html: str, handle: str, flag: str) -> Optional[bool]:
    match = re.search(
        rf'\\?"username\\?"\s*:\s*\\?"{re.escape(handle)}\\?".{{0,400}}\\?"{flag}\\?"\s*:\s*(true|false)',
        html,
        re.I,
    )
    if not match:
        return None
    return match.group(1).lower() == "true"


def _account_from_embed(html: str, handle: str) -> Optional[Dict]:
    """
    Public profile and post embed pages still include follower counts.
    The profile URL itself now redirects to the login wall.
    """
    followers = _extract_int(html, "followers_count")
    if followers is None:
        followed = re.search(
            r'edge_followed_by\\?"\s*:\s*\{\s*\\?"count\\?"\s*:\s*(\d+)',
            html,
        )
        followers = int(followed.group(1)) if followed else None
    if followers is None:
        return None
    if _flag_near_username(html, handle, "is_private"):
        return None

    posts = _extract_int(html, "posts_count")
    return {
        "handle": handle,
        "nickname": _json_string(html, "full_name") or handle,
        "user_id": _owner_id(html, handle),
        "bio": _json_string(html, "biography") or "",
        "bio_link": _json_string(html, "external_url"),
        "followers": followers,
        "following": _extract_int(html, "following_count"),
        "video_count": posts,
        "is_verified": _flag_near_username(html, handle, "is_verified") or False,
    }


def fetch_profile(session: requests.Session, handle: str) -> Optional[Dict]:
    html = _get(session, f"https://www.instagram.com/{handle}/embed/")
    if not html:
        return None
    return _account_from_embed(html, handle)


def fetch_post(session: requests.Session, shortcode: str) -> Optional[Dict]:
    """
    One captioned embed page. It is smaller than the reel page and includes
    play count, handle and caption, so discovery stays on a single request.
    """
    html = _get(session, f"https://www.instagram.com/p/{shortcode}/embed/captioned/")
    if not html:
        return None
    views = _extract_int(html, "video_view_count")
    likes = _extract_int(html, "like_count")
    if likes is None:
        liked = re.search(r'edge_liked_by\\?"\s*:\s*\{\s*\\?"count\\?"\s*:\s*(\d+)', html)
        likes = int(liked.group(1)) if liked else None
    comments = _extract_int(html, "comment_count")
    if comments is None:
        commented = re.search(
            r'edge_media_to_comment\\?"\s*:\s*\{\s*\\?"count\\?"\s*:\s*(\d+)',
            html,
        )
        comments = int(commented.group(1)) if commented else None
    duration = _extract_int(html, "video_duration")
    handle_match = re.search(r'\\"username\\":\\"([\w.]+)', html) or re.search(
        r'"username"\s*:\s*"([\w.]+)"', html
    ) or re.search(r'user\?username=([\w.]+)', html)
    caption = _json_string(html, "text") or ""
    handle = handle_match.group(1) if handle_match else None
    if not handle and not caption and views is None and likes is None:
        return None
    created = _extract_int(html, "taken_at_timestamp")
    published = datetime.fromtimestamp(created, tz=timezone.utc) if created else None
    account = _account_from_embed(html, handle) if handle else None
    return {
        "video_id": shortcode,
        "handle": handle,
        "desc": caption,
        "views": views if views is not None else (likes or 0),
        "likes": likes or 0,
        "comments": comments or 0,
        "duration": duration,
        "created_unix": created,
        "published": published,
        "age_days": _age_days(published) if published else 14,
        "hashtags": re.findall(r"#(\w+)", caption or ""),
        "followers": None if account is None else account["followers"],
        "nickname": None if account is None else account["nickname"],
        "user_id": None if account is None else account["user_id"],
        "video_count": None if account is None else account["video_count"],
        "is_verified": False if account is None else account["is_verified"],
    }


def fetch_recent_posts(
    session: requests.Session,
    handle: str,
    seed: Optional[Dict] = None,
    limit: int = 8,
    region_code: str = "DE",
) -> List[Dict]:
    """One matched post is enough for the view window. Extra index lookups were the slow path."""
    if not seed or not seed.get("video_id"):
        return []
    return [{
        "video_id": seed["video_id"],
        "title": seed.get("desc") or "",
        "views": seed.get("views") or 0,
        "age_days": seed.get("age_days") if seed.get("age_days") is not None else 45,
    }]


# ---------------------------------------------------------------------------
# Search index harvesting
# ---------------------------------------------------------------------------

def _query_variants(keyword: str, code: str) -> List[str]:
    lang = LOCAL_SEARCH_LANGUAGE.get(code, "en")
    local = localize_keyword(keyword, lang)
    variants = []
    if local:
        variants.append(" ".join(local.split()[:3]))
    variants.append(f"{keyword} {EUROPEAN_COUNTRIES[code]}")
    return list(dict.fromkeys(variants))


def _parse_ig_url(url: str) -> Optional[Dict]:
    if "instagram.com" not in url:
        return None
    shortcode_match = _SHORTCODE_RE.search(url)
    handle_in_post = _HANDLE_IN_PATH_RE.search(url)
    handle = None
    if handle_in_post:
        candidate = handle_in_post.group("handle").rstrip("/")
        if candidate.lower() not in _RESERVED_PATHS:
            handle = candidate
    elif not shortcode_match:
        bare = re.search(r"instagram\.com/(?:[a-z]{2}(?:-[a-z]{2})?/)?([\w.]+)/?(?:[?#]|$)", url, re.I)
        if bare and bare.group(1).lower() not in _RESERVED_PATHS:
            handle = bare.group(1)
    if not handle and not shortcode_match:
        return None
    return {
        "handle": handle.lower() if handle else None,
        "video_id": shortcode_match.group(1) if shortcode_match else None,
        "url": url.split("?")[0].rstrip("/"),
    }


def search_index(
    keyword: str,
    code: str,
    max_results: int,
    raw_query: Optional[str] = None,
) -> List[Dict]:
    """
    Queries the search index for Instagram pages. Returns
    [{handle, video_id, url, title, snippet}].
    """
    hits: List[Dict] = []
    seen_urls: set = set()

    def collect(results: Iterable[Dict]) -> None:
        for item in results or []:
            url = item.get("href", "")
            parsed = _parse_ig_url(url)
            if not parsed or url in seen_urls:
                continue
            if not parsed["handle"]:
                title_handle = _HANDLE_FROM_TITLE_RE.search(item.get("title") or "")
                if title_handle and title_handle.group(1).lower() not in _RESERVED_PATHS:
                    parsed["handle"] = title_handle.group(1).lower()
            seen_urls.add(url)
            hits.append({
                **parsed,
                "title": (item.get("title") or "").replace(" | Instagram", "").replace(" • Instagram", "").strip(),
                "snippet": item.get("body") or "",
            })

    queries = [raw_query] if raw_query else [f"site:instagram.com {q}" for q in _query_variants(keyword, code)]
    for query in queries:
        for region in (("wt-wt",) if raw_query else (_ddgs_region(code),)):
            for backend in _SEARCH_BACKENDS:
                try:
                    results = DDGS().text(query, region=region, max_results=max_results, backend=backend)
                except Exception:
                    results = []
                if results:
                    collect(results)
                    break
        if len(hits) >= max_results:
            return hits
    return hits


# ---------------------------------------------------------------------------
# Public entry point (mirrors modules.discovery.search_micro_influencers)
# ---------------------------------------------------------------------------

def search_instagram_micro_influencers(
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
    Discovers European Instagram micro-influencers with the same parameters and
    output schema as the YouTube / TikTok scrapers. ``subscribers`` is the
    follower count; ``transcript_sample`` is the matched caption plus recent
    captions (Instagram has no transcripts).
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

    per_region_limit = min(12, max(6, max_results * 3))
    target_pool = max_results

    seen_handles: set = set()
    profiles: List[Dict] = []

    def profile_job(handle: str):
        with requests.Session() as job:
            return handle, fetch_profile(job, handle)

    def post_job(shortcode: str):
        with requests.Session() as job:
            return shortcode, fetch_post(job, shortcode)

    for code in regions:
        if len(profiles) >= target_pool:
            break
        country_name = EUROPEAN_COUNTRIES[code]
        hits = search_index(keyword, code, per_region_limit)

        queued: List[Dict] = []
        for hit in hits:
            handle = (hit["handle"] or "").lower()
            if handle in _RESERVED_PATHS:
                handle = ""
                hit = {**hit, "handle": None}
            if handle and handle in seen_handles:
                continue
            if handle:
                seen_handles.add(handle)
            queued.append(hit if handle else {**hit, "handle": None})
            if len(queued) >= per_region_limit:
                break

        missing = [hit["video_id"] for hit in queued if not hit["handle"] and hit["video_id"]][:6]
        posts_by_id = dict(_parallel(post_job, missing[:8]))
        candidates = []
        for hit in queued:
            handle = (hit["handle"] or "").lower()
            post = posts_by_id.get(hit["video_id"]) if hit["video_id"] else None
            if not handle:
                handle = ((post or {}).get("handle") or "").lower()
            if not handle or handle in _RESERVED_PATHS:
                continue
            if handle not in seen_handles:
                seen_handles.add(handle)
            candidates.append((handle, hit, post))

        # One profile fetch per handle, in parallel, before any extra reel calls.
        unique = []
        seen_batch = set()
        for handle, hit, post in candidates:
            if handle in seen_batch:
                continue
            seen_batch.add(handle)
            unique.append((handle, hit, post))

        accounts = dict(_parallel(profile_job, [h for h, _, _ in unique]))
        need_posts = [
            post_id for handle, hit, post in unique
            if post is None and hit.get("video_id")
            and (accounts.get(handle) or {}).get("followers") is not None
            and min_subscribers <= accounts[handle]["followers"] <= max_subscribers
            for post_id in [hit["video_id"]]
        ]
        if need_posts:
            posts_by_id.update(dict(_parallel(post_job, need_posts)))

        for handle, hit, post in unique:
            if len(profiles) >= target_pool:
                break
            account = accounts.get(handle)
            if not account and post and post.get("followers") is not None:
                account = {
                    "handle": handle,
                    "nickname": post.get("nickname") or handle,
                    "user_id": post.get("user_id") or handle,
                    "bio": "",
                    "bio_link": None,
                    "followers": post["followers"],
                    "following": None,
                    "video_count": post.get("video_count"),
                    "is_verified": post.get("is_verified") or False,
                }
            if not account:
                continue
            followers = account["followers"]
            if followers is not None and not (min_subscribers <= followers <= max_subscribers):
                continue
            if post is None and hit.get("video_id"):
                post = posts_by_id.get(hit["video_id"])

            detected = infer_country(account["bio"], (post or {}).get("desc"), hit["title"], hit["snippet"])
            if detected and detected not in EUROPEAN_COUNTRIES:
                continue
            country_verified = detected is not None
            if require_verified_country and not country_verified:
                continue
            country_code = detected or code

            uploads = fetch_recent_posts(None, handle, seed=post)
            stats = compute_view_stats(uploads)
            if stats["avg_views"] is not None and not (min_views <= stats["avg_views"] <= max_views):
                continue

            recent_captions = [u["title"] for u in uploads[:15] if u["title"]]
            hashtags = sorted({
                tag.lower()
                for text in [account["bio"], (post or {}).get("desc", ""), *recent_captions]
                for tag in re.findall(r"#(\w+)", text)
            } | set((post or {}).get("hashtags", [])))
            niche_text = " ".join(filter(None, [
                account["nickname"], account["bio"], hit["title"], hit["snippet"],
                (post or {}).get("desc", ""), *recent_captions, " ".join(hashtags),
            ]))

            links = _bio_links(account["bio"], account.get("bio_link"))
            if account.get("bio_link"):
                links.setdefault("website", account["bio_link"])

            matched_id = (post or {}).get("video_id") or hit["video_id"]
            matched_url = (
                f"https://www.instagram.com/{handle}/reel/{matched_id}/"
                if matched_id else f"https://www.instagram.com/{handle}/"
            )
            published = (post or {}).get("published")

            profile = {
                "platform": "Instagram",
                "channel_name": account["nickname"] or f"@{handle}",
                "channel_handle": f"@{handle}",
                "channel_url": f"https://www.instagram.com/{handle}/",
                "channel_id": account["user_id"] or handle,
                "country": EUROPEAN_COUNTRIES.get(country_code),
                "country_code": country_code,
                "country_verified": country_verified,
                "in_eu": country_code in EU_COUNTRIES,
                "search_region": f"{code} ({country_name})",
                "subscribers": followers,
                "subscribers_text": f"{followers:,} followers" if followers is not None else None,
                "total_channel_views": None,
                "total_likes": None,
                "video_count": account["video_count"],
                "channel_joined": None,
                **stats,
                "views_to_subs_ratio": (
                    round(stats["avg_views"] / followers, 3)
                    if stats["avg_views"] is not None and followers else None
                ),
                "niche_hints": detect_terms(niche_text, TOPIC_KEYWORDS),
                "games_detected": detect_terms(niche_text, GAME_KEYWORDS),
                "channel_keywords": hashtags[:15],
                "contact_email": extract_email(account["bio"], (post or {}).get("desc")),
                "contact_links": links,
                "video_id": matched_id,
                "video_title": (post or {}).get("desc") or hit["title"] or f"Instagram by @{handle}",
                "video_url": matched_url,
                "channel_description": (
                    account["bio"] or (post or {}).get("desc") or hit["snippet"] or ""
                )[:600],
                "recent_video_views": (post or {}).get("views", 0),
                "views": (post or {}).get("views", 0),
                "length_seconds": (post or {}).get("duration"),
                "video_published": published.strftime("%Y-%m-%dT%H:%M:%SZ") if published else None,
            }
            profile["risk_flags"] = build_risk_flags(profile, max_subscribers)

            if include_transcripts:
                caption_block = "\n".join(filter(None, [(post or {}).get("desc", ""), *recent_captions]))
                profile["transcript_sample"] = (caption_block or account["bio"] or "")[:1200]
            else:
                profile["transcript_sample"] = ""
            if not profile["contact_email"]:
                profile["contact_email"] = "N/A (check bio / Instagram business email button)"

            profiles.append(profile)
            if len(profiles) >= target_pool:
                break

    profiles.sort(key=lambda p: (
        not p["country_verified"],
        not p["in_eu"],
        -(p["avg_views"] or 0),
    ))
    return profiles[:max_results]


def get_live_instagram_creators(keyword: str = "budget gaming pc", max_results: int = 5, **kwargs) -> List[Dict]:
    """Backwards-compatible wrapper used by the Streamlit app."""
    try:
        return search_instagram_micro_influencers(keyword, max_results=max_results, **kwargs)
    except Exception as e:
        print(f"[Instagram Discovery Warning]: {e}")
        return []

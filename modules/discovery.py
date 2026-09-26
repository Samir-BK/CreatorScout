import re
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional

from ytscrape import YouTube, SearchFilter

# ---------------------------------------------------------------------------
# Geography: Prenew sells across Europe, so the EU-27 is the primary market.
# A few non-EU European markets are kept as secondary targets.
# ---------------------------------------------------------------------------

EU_COUNTRIES: Dict[str, str] = {
    "AT": "Austria", "BE": "Belgium", "BG": "Bulgaria", "HR": "Croatia",
    "CY": "Cyprus", "CZ": "Czechia", "DK": "Denmark", "EE": "Estonia",
    "FI": "Finland", "FR": "France", "DE": "Germany", "GR": "Greece",
    "HU": "Hungary", "IE": "Ireland", "IT": "Italy", "LV": "Latvia",
    "LT": "Lithuania", "LU": "Luxembourg", "MT": "Malta", "NL": "Netherlands",
    "PL": "Poland", "PT": "Portugal", "RO": "Romania", "SK": "Slovakia",
    "SI": "Slovenia", "ES": "Spain", "SE": "Sweden",
}

EUROPE_NON_EU: Dict[str, str] = {
    "GB": "United Kingdom", "NO": "Norway", "CH": "Switzerland", "IS": "Iceland",
}

EUROPEAN_COUNTRIES: Dict[str, str] = {**EU_COUNTRIES, **EUROPE_NON_EU}

# Markets swept when region="EU" (largest PC-gaming audiences first).
EU_SWEEP_REGIONS: List[str] = ["DE", "FR", "NL", "PL", "SE", "FI", "ES", "IT", "DK", "AT"]

# Interface language used for *searching*, so local-language creators surface.
# Metadata is always fetched with hl=en so numbers and dates parse reliably.
LOCAL_SEARCH_LANGUAGE: Dict[str, str] = {
    "AT": "de", "BE": "nl", "BG": "bg", "HR": "hr", "CY": "el", "CZ": "cs",
    "DK": "da", "EE": "et", "FI": "fi", "FR": "fr", "DE": "de", "GR": "el",
    "HU": "hu", "IE": "en", "IT": "it", "LV": "lv", "LT": "lt", "LU": "fr",
    "MT": "en", "NL": "nl", "PL": "pl", "PT": "pt", "RO": "ro", "SK": "sk",
    "SI": "sl", "ES": "es", "SE": "sv", "GB": "en", "NO": "no", "CH": "de",
    "IS": "is",
}

# Local-language equivalents of common PC-gaming search terms. Local creators
# title their videos in their own language, so an English query alone mostly
# surfaces US channels. Longest phrases are substituted first.
TERM_TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "de": {"budget gaming pc": "günstiger gaming pc", "gaming pc build": "gaming pc zusammenbauen",
           "pc build": "pc zusammenbauen", "gaming pc": "gaming pc", "budget": "günstig",
           "cheap": "billig", "build": "zusammenbauen", "review": "test", "best": "beste",
           "laptop": "laptop", "used": "gebraucht", "refurbished": "generalüberholt", "setup": "setup"},
    "fr": {"budget gaming pc": "pc gamer pas cher", "gaming pc build": "montage pc gamer",
           "pc build": "montage pc", "gaming pc": "pc gamer", "budget": "pas cher",
           "cheap": "pas cher", "build": "montage", "review": "test", "best": "meilleur",
           "laptop": "pc portable", "used": "occasion", "refurbished": "reconditionné", "setup": "setup"},
    "nl": {"budget gaming pc": "goedkope game pc", "gaming pc build": "game pc bouwen",
           "pc build": "pc bouwen", "gaming pc": "game pc", "budget": "goedkoop",
           "cheap": "goedkoop", "build": "bouwen", "review": "review", "best": "beste",
           "laptop": "laptop", "used": "tweedehands", "refurbished": "refurbished", "setup": "setup"},
    "pl": {"budget gaming pc": "tani komputer do gier", "gaming pc build": "składanie komputera do gier",
           "pc build": "składanie komputera", "gaming pc": "komputer do gier", "budget": "tani",
           "cheap": "tani", "build": "składanie", "review": "recenzja", "best": "najlepszy",
           "laptop": "laptop", "used": "używany", "refurbished": "odnowiony", "setup": "setup"},
    "sv": {"budget gaming pc": "billig gaming dator", "gaming pc build": "bygga gaming dator",
           "pc build": "bygga dator", "gaming pc": "gaming dator", "budget": "billig",
           "cheap": "billig", "build": "bygga", "review": "recension", "best": "bästa",
           "laptop": "laptop", "used": "begagnad", "refurbished": "renoverad", "setup": "setup"},
    "fi": {"budget gaming pc": "halpa pelikone", "gaming pc build": "pelikoneen kokoaminen",
           "pc build": "tietokoneen kokoaminen", "gaming pc": "pelikone", "budget": "halpa",
           "cheap": "halpa", "build": "kokoaminen", "review": "testi", "best": "paras",
           "laptop": "pelikannettava", "used": "käytetty", "refurbished": "kunnostettu", "setup": "setup"},
    "es": {"budget gaming pc": "pc gaming barato", "gaming pc build": "montar pc gaming",
           "pc build": "montar pc", "gaming pc": "pc gaming", "budget": "barato",
           "cheap": "barato", "build": "montar", "review": "análisis", "best": "mejor",
           "laptop": "portátil", "used": "segunda mano", "refurbished": "reacondicionado", "setup": "setup"},
    "it": {"budget gaming pc": "pc gaming economico", "gaming pc build": "assemblare pc gaming",
           "pc build": "assemblare pc", "gaming pc": "pc gaming", "budget": "economico",
           "cheap": "economico", "build": "assemblare", "review": "recensione", "best": "migliore",
           "laptop": "notebook", "used": "usato", "refurbished": "ricondizionato", "setup": "setup"},
    "da": {"budget gaming pc": "billig gaming pc", "gaming pc build": "byg gaming pc",
           "pc build": "byg pc", "gaming pc": "gaming pc", "budget": "billig",
           "cheap": "billig", "build": "byg", "review": "test", "best": "bedste",
           "laptop": "laptop", "used": "brugt", "refurbished": "renoveret", "setup": "setup"},
    "pt": {"budget gaming pc": "pc gamer barato", "gaming pc build": "montar pc gamer",
           "pc build": "montar pc", "gaming pc": "pc gamer", "budget": "barato",
           "cheap": "barato", "build": "montar", "review": "análise", "best": "melhor",
           "laptop": "portátil", "used": "usado", "refurbished": "recondicionado", "setup": "setup"},
    "cs": {"budget gaming pc": "levný herní pc", "gaming pc build": "stavba herního pc",
           "pc build": "stavba pc", "gaming pc": "herní pc", "budget": "levný",
           "cheap": "levný", "build": "stavba", "review": "recenze", "best": "nejlepší",
           "laptop": "notebook", "used": "použitý", "refurbished": "repasovaný", "setup": "setup"},
}

# How YouTube's About panel spells countries (hl=en) -> ISO code.
_COUNTRY_ALIASES: Dict[str, str] = {name.lower(): code for code, name in EUROPEAN_COUNTRIES.items()}
_COUNTRY_ALIASES.update({
    "czech republic": "CZ", "the netherlands": "NL", "holland": "NL",
    "uk": "GB", "great britain": "GB", "england": "GB", "scotland": "GB",
    "wales": "GB", "northern ireland": "GB", "republic of ireland": "IE",
})

# InnerTube "Videos" tab parameter for a channel browse request.
_VIDEOS_TAB_PARAMS = "EgZ2aWRlb3PyBgQKAjoA"

# ---------------------------------------------------------------------------
# Niche detection vocab (matched against titles, channel keywords, descriptions)
# ---------------------------------------------------------------------------

GAME_KEYWORDS: Dict[str, List[str]] = {
    "Fortnite": ["fortnite"],
    "Counter-Strike 2": ["cs2", "counter-strike", "counter strike", "csgo"],
    "Valorant": ["valorant"],
    "Minecraft": ["minecraft"],
    "GTA V / RP": ["gta", "grand theft auto"],
    "Call of Duty / Warzone": ["call of duty", "warzone", "cod ", "black ops"],
    "Apex Legends": ["apex legends", "apex"],
    "League of Legends": ["league of legends", " lol "],
    "Cyberpunk 2077": ["cyberpunk"],
    "Elden Ring": ["elden ring"],
    "Battlefield": ["battlefield"],
    "EA FC / FIFA": ["ea fc", "fifa", "fc 25", "fc 26"],
    "Roblox": ["roblox"],
    "Rust": [" rust "],
    "Escape from Tarkov": ["tarkov"],
    "PUBG": ["pubg"],
    "Overwatch": ["overwatch"],
    "Rocket League": ["rocket league"],
    "Helldivers": ["helldivers"],
    "Marvel Rivals": ["marvel rivals"],
    "Starfield / Bethesda": ["starfield", "skyrim", "fallout"],
    "Red Dead Redemption": ["red dead"],
    "Sim / Racing": ["forza", "assetto", "iracing", "f1 2", "gran turismo"],
    "Flight Sim": ["flight simulator", "msfs"],
    "Baldur's Gate 3": ["baldur"],
    "Hogwarts Legacy": ["hogwarts"],
}

TOPIC_KEYWORDS: Dict[str, List[str]] = {
    "Budget PC builds": ["budget", "cheap", "günstig", "guenstig", "billig", "goedkoop",
                         "pas cher", "barato", "economico", "tani", "halpa", "billigt"],
    "PC building": ["build", "zusammenbauen", "zusammenstellen", "bouwen", "montage",
                    "montar", "assemblare", "składam", "kokoaminen", "bygga"],
    "Refurbished / used hardware": ["refurbished", "used", "second hand", "gebraucht",
                                    "tweedehands", "occasion", "segunda mano", "usato",
                                    "używany", "käytetty", "begagnad", "renoveret"],
    "Hardware reviews": ["review", "test", "unboxing", "vs", "vergleich", "recensione",
                         "análisis", "porównanie"],
    "Benchmarks / FPS": ["benchmark", "fps", "1080p", "1440p", "4k", "performance"],
    "GPU / CPU": ["gpu", "rtx", "radeon", "geforce", "cpu", "ryzen", "intel", "nvidia", "amd"],
    "Gaming laptops": ["laptop", "notebook"],
    "Desk setups": ["setup", "desk", "schreibtisch", "gaming room"],
    "Prebuilt PCs": ["prebuilt", "fertig pc", "fertig-pc", "komplett pc", "kant-en-klaar"],
    "Deals / price tracking": ["deal", "angebot", "sale", "black friday", "prime day"],
}

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_COUNT_RE = re.compile(r"(\d[\d.,]*)\s*([KMB])?", re.IGNORECASE)
_RELATIVE_RE = re.compile(r"(\d+)\s+(second|minute|hour|day|week|month|year)s?\s+ago", re.IGNORECASE)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

_UNIT_DAYS = {"second": 0, "minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}


def parse_count(text: Optional[str]) -> Optional[int]:
    """'866K subscribers' -> 866000, '203,596,900 views' -> 203596900, 'No views' -> 0."""
    if not text:
        return None
    lowered = text.lower()
    if lowered.startswith("no "):
        return 0
    match = _COUNT_RE.search(text)
    if not match:
        return None
    number, suffix = match.group(1), (match.group(2) or "").upper()
    # YouTube (hl=en) uses ',' as thousands separator and '.' as decimal.
    number = number.replace(",", "")
    try:
        value = float(number)
    except ValueError:
        return None
    value *= {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suffix, 1)
    return int(value)


def parse_age_days(text: Optional[str]) -> Optional[int]:
    """'2 weeks ago' -> 14, 'Streamed 3 days ago' -> 3, '5 hours ago' -> 0."""
    if not text:
        return None
    match = _RELATIVE_RE.search(text)
    if not match:
        return None
    amount, unit = int(match.group(1)), match.group(2).lower()
    return amount * _UNIT_DAYS[unit]


def extract_email(*texts: Optional[str]) -> Optional[str]:
    for text in texts:
        if not text:
            continue
        match = _EMAIL_RE.search(text)
        if match:
            return match.group(0).rstrip(".")
    return None


def resolve_country(about_country: Optional[str]) -> Optional[str]:
    """Map the About-panel country string to an ISO code, or None if unknown."""
    if not about_country:
        return None
    key = about_country.strip().lower()
    return _COUNTRY_ALIASES.get(key)


def localize_keyword(keyword: str, lang: str) -> Optional[str]:
    """
    Best-effort translation of an English niche query into the local language
    using the term table. Returns None when nothing could be translated.
    """
    table = TERM_TRANSLATIONS.get(lang)
    if not table:
        return None
    localized = f" {keyword.lower()} "
    for phrase in sorted(table, key=len, reverse=True):
        localized = localized.replace(f" {phrase} ", f" {table[phrase]} ")
    localized = " ".join(localized.split())
    return localized if localized != keyword.lower() else None


def _walk(node: Any, key: str, acc: List[Any]) -> List[Any]:
    if isinstance(node, dict):
        if key in node:
            acc.append(node[key])
        for value in node.values():
            _walk(value, key, acc)
    elif isinstance(node, list):
        for item in node:
            _walk(item, key, acc)
    return acc


def detect_terms(text: str, vocab: Dict[str, List[str]]) -> List[str]:
    haystack = f" {text.lower()} "
    return [label for label, needles in vocab.items() if any(n in haystack for n in needles)]


_detect = detect_terms


# ---------------------------------------------------------------------------
# Channel-level data collection
# ---------------------------------------------------------------------------

def fetch_channel_uploads(yt: YouTube, channel_id: str, limit: int = 30) -> List[Dict]:
    """
    Reads the channel's Videos tab (newest first) and returns
    [{video_id, title, views, age_days}, ...]. Uses the InnerTube browse
    endpoint directly because ytscrape has no channel-listing helper.
    """
    try:
        response = yt.client.browse(channel_id, params=_VIDEOS_TAB_PARAMS)
    except Exception:
        return []

    uploads: List[Dict] = []
    for lockup in _walk(response, "lockupViewModel", []):
        if lockup.get("contentType") != "LOCKUP_CONTENT_TYPE_VIDEO":
            continue
        meta = lockup.get("metadata", {}).get("lockupMetadataViewModel", {})
        title = (meta.get("title") or {}).get("content")
        rows = meta.get("metadata", {}).get("contentMetadataViewModel", {}).get("metadataRows", [])
        parts = [
            part.get("text", {}).get("content", "")
            for row in rows
            for part in row.get("metadataParts", [])
        ]
        views = next((parse_count(p) for p in parts if "view" in p.lower()), None)
        age = next((parse_age_days(p) for p in parts if "ago" in p.lower()), None)
        if views is None or age is None:
            continue
        uploads.append({
            "video_id": lockup.get("contentId"),
            "title": title,
            "views": views,
            "age_days": age,
        })
        if len(uploads) >= limit:
            break
    return uploads


def compute_view_stats(uploads: List[Dict]) -> Dict:
    """
    Average views over a 30-day window for active channels, widened to
    90 days for less active channels, with a last-uploads fallback.
    Also derives upload cadence and a growth trend.
    """
    if not uploads:
        return {
            "avg_views": None, "avg_views_window_days": None, "avg_views_sample_size": 0,
            "activity_level": "Unknown", "uploads_last_30d": 0, "uploads_last_90d": 0,
            "uploads_per_month": 0.0, "latest_upload_days_ago": None,
            "trend": "Unknown", "trend_ratio": None,
        }

    last_30 = [u for u in uploads if u["age_days"] <= 30]
    last_90 = [u for u in uploads if u["age_days"] <= 90]

    if len(last_30) >= 3:
        window, sample, activity = 30, last_30, "Active (3+ uploads / 30d)"
    elif last_90:
        window, sample, activity = 90, last_90, "Less active (<3 uploads / 30d)"
    else:
        window, sample, activity = None, uploads[:10], "Dormant (no uploads in 90d)"

    avg_views = int(mean(u["views"] for u in sample))

    # Trend: current window vs. the uploads immediately before it.
    older = [u for u in uploads if u not in sample][:10]
    trend, ratio = "Insufficient data", None
    if window is None:
        trend = "Inactive"
    elif older and avg_views:
        older_avg = mean(u["views"] for u in older) or 1
        ratio = round(avg_views / older_avg, 2)
        trend = "Growing" if ratio >= 1.25 else "Declining" if ratio <= 0.75 else "Stable"

    return {
        "avg_views": avg_views,
        "avg_views_window_days": window,
        "avg_views_sample_size": len(sample),
        "activity_level": activity,
        "uploads_last_30d": len(last_30),
        "uploads_last_90d": len(last_90),
        "uploads_per_month": round(len(last_90) / 3, 1),
        "latest_upload_days_ago": min(u["age_days"] for u in uploads),
        "trend": trend,
        "trend_ratio": ratio,
    }


def build_risk_flags(profile: Dict, max_subscribers: int) -> List[str]:
    flags: List[str] = []
    if not profile["country_verified"]:
        flags.append("Country not published on channel; inferred from search region")
    if profile["subscribers"] is None:
        flags.append("Subscriber count hidden")
    elif max_subscribers and profile["subscribers"] > max_subscribers:
        flags.append("Above micro-influencer subscriber ceiling")
    if profile["activity_level"].startswith("Dormant"):
        flags.append("No uploads in the last 90 days")
    elif profile["activity_level"].startswith("Less active"):
        flags.append("Low upload cadence")
    if profile["trend"] == "Declining":
        flags.append("View counts trending down")
    if profile["avg_views_sample_size"] and profile["avg_views_sample_size"] < 3:
        flags.append("View average based on fewer than 3 videos")
    if not profile["contact_email"] and not profile["contact_links"]:
        flags.append("No public contact details found")
    ratio = profile.get("views_to_subs_ratio")
    if ratio is not None and ratio < 0.05:
        flags.append("Avg views under 5% of subscribers (low engagement)")
    return flags or ["Low Risk"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def search_micro_influencers(
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
    Discovers European micro-influencers on YouTube for Prenew.

    region: an ISO code from EUROPEAN_COUNTRIES, or "EU" to sweep the main
            EU markets (EU_SWEEP_REGIONS / sweep_regions).
    language: override the local search language (default: per-country).
    min_views / max_views: applied to the *average* views per video, not a
            single video, so a lucky viral upload doesn't disqualify a creator.
    require_verified_country: drop channels that don't publish a European
            country on their About page (otherwise they're kept and flagged).

    Each result contains: country, subscribers, avg views (30d window for active
    channels, 90d for less active), niche hints, contact details, and risk/trend
    signals. The LLM scorer refines niche / risk / trend on top of these.
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

    # Most search hits fail the micro-tier filters, so over-fetch; the loop
    # stops early once the candidate pool is full.
    per_region_limit = min(40, max(8, (max_results * 8) // len(regions)))
    target_pool = max_results * 2

    seen_channels: set = set()
    profiles: List[Dict] = []

    for code in regions:
        if len(profiles) >= target_pool:
            break

        country_name = EUROPEAN_COUNTRIES[code]
        search_lang = language or LOCAL_SEARCH_LANGUAGE.get(code, "en")

        with YouTube(language=search_lang, region=code) as search_yt, \
             YouTube(language="en", region=code) as meta_yt:

            # Local-language query first (surfaces native creators), then the
            # English query anchored to the country name.
            queries = [q for q in (localize_keyword(keyword, search_lang), f"{keyword} {country_name}") if q]
            hits: List[Any] = []
            seen_videos: set = set()
            for query in queries:
                try:
                    for hit in search_yt.search(query, filter=SearchFilter.VIDEOS, max_results=per_region_limit):
                        if hit.video_id not in seen_videos:
                            seen_videos.add(hit.video_id)
                            hits.append(hit)
                except Exception:
                    continue

            for hit in hits:
                if not hit.channel_id or hit.channel_id in seen_channels:
                    continue
                seen_channels.add(hit.channel_id)

                try:
                    channel = meta_yt.channel(hit.channel_id)
                except Exception:
                    continue

                country_code = resolve_country(channel.country)
                country_verified = country_code is not None
                if channel.country and not country_verified:
                    # Channel explicitly lists a non-European country.
                    continue
                if require_verified_country and not country_verified:
                    continue

                subscribers = parse_count(channel.subscribers)
                if subscribers is not None and not (min_subscribers <= subscribers <= max_subscribers):
                    continue

                uploads = fetch_channel_uploads(meta_yt, hit.channel_id)
                stats = compute_view_stats(uploads)
                if stats["avg_views"] is not None and not (min_views <= stats["avg_views"] <= max_views):
                    continue

                niche_text = " ".join(filter(None, [
                    channel.title, channel.description, " ".join(channel.keywords),
                    hit.title, *[u["title"] or "" for u in uploads[:15]],
                ]))
                links = {k: v for k, v in (channel.links or {}).items() if k != "youtube"}

                profile = {
                    "platform": "YouTube",
                    # Identity
                    "channel_name": channel.title or hit.channel,
                    "channel_handle": channel.handle,
                    "channel_url": channel.vanity_url or channel.url,
                    "channel_id": hit.channel_id,
                    # Geography
                    "country": EUROPEAN_COUNTRIES.get(country_code or code),
                    "country_code": country_code or code,
                    "country_verified": country_verified,
                    "in_eu": (country_code or code) in EU_COUNTRIES,
                    "search_region": f"{code} ({country_name})",
                    # Audience size
                    "subscribers": subscribers,
                    "subscribers_text": channel.subscribers,
                    "total_channel_views": parse_count(channel.view_count),
                    "video_count": parse_count(channel.video_count),
                    "channel_joined": channel.joined_date,
                    # Performance
                    **stats,
                    "views_to_subs_ratio": (
                        round(stats["avg_views"] / subscribers, 3)
                        if stats["avg_views"] is not None and subscribers else None
                    ),
                    # Niche hints (refined by the LLM scorer)
                    "niche_hints": _detect(niche_text, TOPIC_KEYWORDS),
                    "games_detected": _detect(niche_text, GAME_KEYWORDS),
                    "channel_keywords": list(channel.keywords)[:15],
                    # Contact
                    "contact_email": extract_email(channel.description),
                    "contact_links": links,
                    # Matched video (filled in below)
                    "video_id": hit.video_id,
                    "video_title": hit.title,
                    "video_url": hit.url,
                    "channel_description": (channel.description or "")[:600],
                }
                profile["risk_flags"] = build_risk_flags(profile, max_subscribers)
                profiles.append(profile)

                if len(profiles) >= target_pool:
                    break

    # Verified EU creators first, then by how well avg views sit inside the micro band.
    profiles.sort(key=lambda p: (
        not p["country_verified"],
        not p["in_eu"],
        -(p["avg_views"] or 0),
    ))
    selected = profiles[:max_results]

    # Enrich only the shortlist with video details + transcript (expensive calls).
    for profile in selected:
        try:
            with YouTube(language="en", region=profile["country_code"]) as yt:
                details = yt.video(profile["video_id"])
                profile["recent_video_views"] = details.views or 0
                profile["views"] = profile["recent_video_views"]
                profile["length_seconds"] = details.length_seconds
                profile["video_published"] = details.published
                if not profile["contact_email"]:
                    profile["contact_email"] = extract_email(details.description)

                transcript_text = ""
                if include_transcripts:
                    try:
                        transcript = yt.transcript(
                            profile["video_id"],
                            languages=(LOCAL_SEARCH_LANGUAGE.get(profile["country_code"], "en"), "en"),
                        )
                        transcript_text = transcript.text
                    except Exception:
                        transcript_text = ""
                profile["transcript_sample"] = (transcript_text or details.description or "")[:1200]
        except Exception:
            profile.setdefault("recent_video_views", 0)
            profile.setdefault("views", 0)
            profile.setdefault("transcript_sample", profile.get("channel_description", ""))

        if not profile["contact_email"]:
            profile["contact_email"] = "N/A (use 'View email address' on channel About page)"

    return selected

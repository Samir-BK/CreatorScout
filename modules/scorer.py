import json
import os

from dotenv import load_dotenv
from groq import Groq, RateLimitError

load_dotenv()

# Each model has its own daily token bucket. gpt-oss-20b is capped at 200k
# tokens/day on the free tier, so scoring falls through to the next bucket.
_MODELS = (
    "openai/gpt-oss-120b",
    "qwen/qwen3.8-27b",
    "allam-2-7b",
)


def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing in .env file.")
    return Groq(api_key=api_key)


def _clip(value, limit: int) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return text[:limit]


def _heuristic_score(creator_data: dict) -> dict:
    """Used only when every Groq model is out of daily tokens."""
    score = 55
    ratio = creator_data.get("views_to_subs_ratio")
    if isinstance(ratio, (int, float)):
        score += 15 if ratio >= 0.2 else -15 if ratio < 0.05 else 0
    trend = creator_data.get("trend")
    if trend == "Growing":
        score += 10
    elif trend == "Declining":
        score -= 10
    if creator_data.get("country_verified"):
        score += 5
    flags = creator_data.get("risk_flags") or []
    if flags == ["Low Risk"]:
        score += 5
    else:
        score -= min(15, 5 * len(flags))

    niche = ", ".join(creator_data.get("niche_hints") or []) or "PC gaming"
    games = ", ".join(creator_data.get("games_detected") or [])
    if games:
        niche = f"{niche} ({games})"
    return {
        "relevance_score": max(0, min(100, score)),
        "detected_niche": niche,
        "risk_factors": ", ".join(flags) if flags else "Low Risk",
        "trend_factor": str(trend or "Unknown"),
        "fit_reasoning": (
            "Estimated from channel stats because the Groq daily token limit was reached. "
            "Run scoring again later for an AI judgment."
        ),
    }


def _prompt(creator_data: dict) -> str:
    return f"""You are an influencer partnerships lead at Prenew, a European marketplace for refurbished gaming PCs.
Score this creator for a sponsorship. Reply with JSON only:
{{"relevance_score":0-100,"detected_niche":"...","risk_factors":"...","trend_factor":"...","fit_reasoning":"1-2 sentences"}}

Name: {_clip(creator_data.get('channel_name'), 80)} ({_clip(creator_data.get('channel_handle'), 40)})
Country: {_clip(creator_data.get('country'), 40)} verified={creator_data.get('country_verified')}
Subscribers: {creator_data.get('subscribers_text') or creator_data.get('subscribers')}
Avg views: {creator_data.get('avg_views')} over {creator_data.get('avg_views_window_days')}d ({creator_data.get('avg_views_sample_size')} videos)
Activity: {_clip(creator_data.get('activity_level'), 60)}, {creator_data.get('uploads_per_month')} uploads/month
Trend: {creator_data.get('trend')} ratio={creator_data.get('trend_ratio')} views/subs={creator_data.get('views_to_subs_ratio')}
Niche hints: {_clip(creator_data.get('niche_hints'), 160)}
Games: {_clip(creator_data.get('games_detected'), 160)}
Risk flags: {_clip(creator_data.get('risk_flags'), 200)}
Video: {_clip(creator_data.get('video_title'), 140)} ({creator_data.get('recent_video_views')} views)
Description: {_clip(creator_data.get('channel_description'), 280)}
Transcript: {_clip(creator_data.get('transcript_sample'), 400)}
"""


def _parse_score(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    data = json.loads(text)
    data["relevance_score"] = max(0, min(100, int(data["relevance_score"])))
    return data


def score_creator_fit(creator_data: dict) -> dict:
    """
    Evaluates creator fit against Prenew criteria (Niche, Risks, Trends).
    """
    client = get_groq_client()
    prompt = _prompt(creator_data)
    last_error = None

    for model in _MODELS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
                max_tokens=220,
                temperature=0.2,
            )
            return _parse_score(response.choices[0].message.content)
        except RateLimitError as exc:
            last_error = exc
            continue
        except Exception as exc:
            last_error = exc
            continue

    if isinstance(last_error, RateLimitError):
        return _heuristic_score(creator_data)
    return {
        "relevance_score": 0,
        "detected_niche": "Unknown",
        "risk_factors": "Error during analysis",
        "trend_factor": "Unknown",
        "fit_reasoning": "Scoring failed. Try the run again in a few minutes.",
    }
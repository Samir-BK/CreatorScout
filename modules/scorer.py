import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing in .env file.")
    return Groq(api_key=api_key)

def score_creator_fit(creator_data: dict) -> dict:
    """
    Evaluates creator fit against Prenew criteria (Niche, Risks, Trends).
    """
    client = get_groq_client()
    
    prompt = f"""
    You are an Influencer Marketing Lead for Prenew (European marketplace for refurbished gaming PCs).
    Evaluate this creator profile against our partnership criteria:

    Candidate Info:
    - Channel Name: {creator_data.get('channel_name')} ({creator_data.get('channel_handle')})
    - Country: {creator_data.get('country')} (verified on channel: {creator_data.get('country_verified')})
    - Subscribers: {creator_data.get('subscribers_text') or creator_data.get('subscribers')}
    - Avg views per video: {creator_data.get('avg_views')} over last {creator_data.get('avg_views_window_days')} days ({creator_data.get('avg_views_sample_size')} videos)
    - Activity: {creator_data.get('activity_level')}, {creator_data.get('uploads_per_month')} uploads/month, last upload {creator_data.get('latest_upload_days_ago')} days ago
    - Measured trend: {creator_data.get('trend')} (recent/older view ratio {creator_data.get('trend_ratio')})
    - Views-to-subscribers ratio: {creator_data.get('views_to_subs_ratio')}
    - Keyword niche hints: {creator_data.get('niche_hints')}
    - Games detected in titles: {creator_data.get('games_detected')}
    - Heuristic risk flags: {creator_data.get('risk_flags')}
    - Matched video: {creator_data.get('video_title')} ({creator_data.get('recent_video_views')} views)
    - Channel description: {creator_data.get('channel_description')}
    - Transcript Sample: {creator_data.get('transcript_sample')}

    Respond ONLY in raw, valid JSON matching this exact schema:
    {{
      "relevance_score": <integer 0-100>,
      "detected_niche": "<string: content type + specific games, e.g. 'Budget PC builds / PC gaming (Fortnite, CS2)'>",
      "risk_factors": "<string: brand safety, dormant channel, declining views, unverified country, etc. or 'Low Risk'>",
      "trend_factor": "<string: growth trajectory and content trends, grounded in the measured numbers above>",
      "fit_reasoning": "<1-2 sentence explanation for Prenew partnership fit>"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return {
            "relevance_score": 0,
            "detected_niche": "Unknown",
            "risk_factors": "Error during analysis",
            "trend_factor": "Unknown",
            "fit_reasoning": f"Scoring failed: {str(e)}"
        }
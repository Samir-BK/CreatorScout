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
    Evaluates creator fit for Prenew's refurbished gaming PC brand using Groq LLM analysis.
    """
    client = get_groq_client()

    prompt = f"""
    You are an Influencer Marketing Specialist for Prenew, a European marketplace for refurbished gaming PCs.
    Your goal is to evaluate if a YouTube creator is a good match for sponsored partnerships.

    Target Criteria:
    - Focuses on PC gaming, hardware, budget builds, desk setups, or gaming performance benchmarks.
    - Avoids irrelevant tech (e.g., enterprise IT, smartphone-only reviews, non-gaming hardware).

    Candidate Data:
    - Channel Name: {creator_data.get('channel_name')}
    - Video Title: {creator_data.get('video_title')}
    - Views: {creator_data.get('views')}
    - Transcript / Description Sample: {creator_data.get('transcript_sample')}

    Respond ONLY in valid JSON with this exact structure:
    {{
        "relevance_score": <integer 0-100>,
        "is_hardware_focused": <true or false>,
        "detected_niche": "<short string describing niche>",
        "fit_reasoning": "<one or two sentence explanation>"
    }}
    """

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-20b",
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )

        content = response.choices[0].message.content
        return json.loads(content)

    except Exception as e:
        return {
            "relevance_score": 0,
            "is_hardware_focused": False,
            "detected_niche": "Unknown",
            "fit_reasoning": f"Scoring failed due to error: {str(e)}"
        }
import os
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

def get_groq_client():
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY environment variable is missing in .env file.")
    return Groq(api_key=api_key)

def generate_pitch_email(
    channel_name: str, 
    video_title: str, 
    detected_niche: str, 
    fit_reasoning: str
) -> str:
    """
    Generates a personalized sponsorship outreach email for a creator based on their video metadata.
    """
    client = get_groq_client()

    prompt = f"""
    You are an Influencer Partnerships Lead at Prenew (a European marketplace for high-performance refurbished gaming PCs with 2-year warranties).
    
    Write a short, professional, yet gaming-native outreach email to the YouTube creator '{channel_name}'.

    Context:
    - Recent Video Title: "{video_title}"
    - Creator Niche: {detected_niche}
    - Reason We Selected Them: {fit_reasoning}

    Guidelines:
    - Briefly mention that you enjoyed their video "{video_title}".
    - Pitch a collaboration: Prenew sending them a free refurbished gaming PC build or sponsoring a video.
    - Highlight Prenew's value prop: sustainability, high performance, 2-year warranty, affordable pricing in Europe.
    - Keep it under 130 words, casual, direct, and no corporate fluff.
    - Include a clear, low-friction Call to Action (e.g., asking if they're open to reviewing a unit).
    """

    try:
        response = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating email pitch: {str(e)}"
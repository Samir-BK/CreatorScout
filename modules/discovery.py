from ytscrape import YouTube, SearchFilter
from typing import List, Dict

def search_micro_influencers(keyword: str, max_results: int = 10) -> List[Dict]:
    """
    Searches YouTube for videos matching a niche keyword and extracts 
    channel metadata and transcript samples for AI evaluation.
    """
    found_creators = []
    
    with YouTube(language="en", region="US") as yt:
        for video in yt.search(keyword, filter=SearchFilter.VIDEOS, max_results=max_results):
            details = yt.video(video.url)
            
            transcript_text = ""
            try:
                transcripts = yt.transcript(details.video_id)
                if transcripts:
                    transcript_text = " ".join([t.text for t in transcripts[:25]])
            except Exception:
                transcript_text = details.description or ""

            found_creators.append({
                "video_title": details.title,
                "video_url": details.url,
                "channel_name": details.channel,
                "views": details.views,
                "length_seconds": details.length_seconds,
                "transcript_sample": transcript_text[:1200]
            })
            
    return found_creators
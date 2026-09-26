from ytscrape import YouTube, SearchFilter
from typing import List, Dict

def search_micro_influencers(
    keyword: str, 
    max_results: int = 5, 
    max_views: int = 100000,
    min_views: int = 1000,
    region: str = "US",
    language: str = "en"
) -> List[Dict]:
    """
    Searches YouTube for micro-influencers with full control over filters:
    - max_views & min_views: isolate micro-creators and filter out noise
    - region & language: multi-market support (e.g. FI, DE, SE)
    """
    candidates = []
    
    with YouTube(language=language, region=region) as yt:
        # Search a wider pool to filter from
        search_limit = max(max_results * 4, 15)
        
        for video in yt.search(keyword, filter=SearchFilter.VIDEOS, max_results=search_limit):
            details = yt.video(video.url)
            views = details.views or 0
            
            # Extract transcript sample for downstream LLM evaluation
            transcript_text = ""
            try:
                transcripts = yt.transcript(details.video_id)
                if transcripts:
                    transcript_text = " ".join([t.text for t in transcripts[:25]])
            except Exception:
                transcript_text = details.description or ""

            candidates.append({
                "video_title": details.title,
                "video_url": details.url,
                "channel_name": details.channel,
                "views": views,
                "length_seconds": details.length_seconds,
                "transcript_sample": transcript_text[:1200]
            })

    # Sort candidates by view count (ascending to prioritize smaller creators)
    candidates = sorted(candidates, key=lambda x: x["views"])
    
    # Apply strict view threshold filtering
    filtered = [c for c in candidates if min_views <= c["views"] <= max_views]
    
    # Return filtered list if matches exist; otherwise fallback to the lowest-viewed candidates
    if filtered:
        return filtered[:max_results]
    
    return candidates[:max_results]
"""
YouTube Transcript Tool
Extracts transcripts from YouTube videos and generates comprehensive summaries.
"""

import re
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from langchain_core.tools import tool
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# Simple in-memory cache for video transcripts
# Format: {video_id: (result_string, timestamp)}
_transcript_cache = {}
CACHE_TTL_HOURS = 24


def extract_youtube_video_id(url: str) -> Optional[str]:
    """
    Extract YouTube video ID from various URL formats.

    Supports:
    - https://www.youtube.com/watch?v=VIDEO_ID
    - https://youtu.be/VIDEO_ID
    - https://www.youtube.com/embed/VIDEO_ID
    - https://www.youtube.com/v/VIDEO_ID
    """
    patterns = [
        r'(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/embed\/|youtube\.com\/v\/)([a-zA-Z0-9_-]{11})',
        r'youtube\.com\/watch\?.*v=([a-zA-Z0-9_-]{11})',
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)

    return None


def detect_youtube_urls(text: str) -> List[str]:
    """
    Detect all YouTube URLs in text.

    Supports various YouTube URL formats and returns deduplicated list of URLs found.

    Args:
        text: Text content to search for YouTube URLs

    Returns:
        List of YouTube URLs found (deduplicated)

    Example:
        >>> text = "Check out https://www.youtube.com/watch?v=abc123 and https://youtu.be/def456"
        >>> urls = detect_youtube_urls(text)
        >>> len(urls)
        2
    """
    patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?[^\s]*v=[a-zA-Z0-9_-]{11}[^\s]*',
        r'https?://youtu\.be/[a-zA-Z0-9_-]{11}(?:\?[^\s]*)?',
        r'https?://(?:www\.)?youtube\.com/embed/[a-zA-Z0-9_-]{11}(?:\?[^\s]*)?',
        r'https?://(?:www\.)?youtube\.com/v/[a-zA-Z0-9_-]{11}(?:\?[^\s]*)?',
    ]
    urls = []
    for pattern in patterns:
        urls.extend(re.findall(pattern, text))
    return list(set(urls))  # Remove duplicates


@tool
def get_youtube_transcript(youtube_url: str) -> str:
    """
    Get the full transcript of a YouTube video.

    Args:
        youtube_url: The YouTube video URL (e.g., https://www.youtube.com/watch?v=VIDEO_ID)

    Returns:
        The complete transcript text, or error message if transcript is unavailable.

    Example:
        >>> transcript = get_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    """
    try:
        # Extract video ID
        video_id = extract_youtube_video_id(youtube_url)
        if not video_id:
            return f"❌ Error: Could not extract video ID from URL: {youtube_url}"

        print(f"🎥 Extracting transcript for video ID: {video_id}")

        # Get transcript
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)

        # Combine all transcript segments
        full_transcript = " ".join([segment['text'] for segment in transcript_list])

        # Get video metadata
        duration_seconds = sum([segment['duration'] for segment in transcript_list])
        duration_minutes = int(duration_seconds / 60)

        result = f"""✅ YouTube Transcript Retrieved

Video ID: {video_id}
Duration: ~{duration_minutes} minutes
Transcript Length: {len(full_transcript)} characters

--- TRANSCRIPT ---
{full_transcript}
--- END TRANSCRIPT ---
"""

        print(f"✅ Successfully retrieved transcript ({len(full_transcript)} chars)")
        return result

    except TranscriptsDisabled:
        return f"❌ Error: Transcripts are disabled for this video: {youtube_url}"

    except NoTranscriptFound:
        return f"❌ Error: No transcript available for this video: {youtube_url}"

    except Exception as e:
        return f"❌ Error extracting transcript: {str(e)}"


@tool
def analyze_youtube_transcript(youtube_url: str) -> str:
    """
    Get a YouTube video transcript AND generate a comprehensive summary.
    This is a convenience tool that combines transcript extraction and summarization.

    Includes caching to avoid re-fetching transcripts for the same video.

    Args:
        youtube_url: The YouTube video URL

    Returns:
        A comprehensive summary of the video content based on the transcript.

    Example:
        >>> summary = analyze_youtube_transcript("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    """
    # Extract video ID for caching
    video_id = extract_youtube_video_id(youtube_url)
    if not video_id:
        return f"❌ Error: Could not extract video ID from URL: {youtube_url}"

    # Check cache first
    if video_id in _transcript_cache:
        cached_result, cached_time = _transcript_cache[video_id]
        if datetime.now() - cached_time < timedelta(hours=CACHE_TTL_HOURS):
            print(f"✅ Using cached transcript for video {video_id} (cached {(datetime.now() - cached_time).seconds // 60} minutes ago)")
            return cached_result

    # Get the transcript
    transcript_result = get_youtube_transcript(youtube_url)

    if "❌ Error" in transcript_result:
        return transcript_result

    # Prepare the final result with analysis instructions
    final_result = f"""{transcript_result}

📝 Instructions for the LLM:
Please provide a comprehensive summary of this YouTube video transcript including:
1. Main topic and key points
2. Important insights or takeaways
3. Any specific examples or data mentioned
4. Overall tone and style of the content

Format the summary in a way that would be useful for writing an authentic, informed comment on a social media post sharing this video.
"""

    # Cache the result
    _transcript_cache[video_id] = (final_result, datetime.now())
    print(f"💾 Cached transcript for video {video_id}")

    return final_result


def test_youtube_transcript():
    """Test the YouTube transcript tool"""
    # Test URL extraction
    test_urls = [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://www.youtube.com/embed/dQw4w9WgXcQ",
    ]

    print("Testing YouTube video ID extraction...")
    for url in test_urls:
        video_id = extract_youtube_video_id(url)
        print(f"  {url} -> {video_id}")

    print("\n✅ YouTube transcript tool ready!")


if __name__ == "__main__":
    test_youtube_transcript()

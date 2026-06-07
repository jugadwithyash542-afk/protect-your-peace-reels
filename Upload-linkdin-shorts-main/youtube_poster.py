"""
YouTube Shorts Poster Module
Handles video uploads to YouTube via the YouTube Data API v3.
Reference: https://developers.google.com/youtube/v3
"""

import os
import time
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

load_dotenv()

# Configuration - loaded from environment
YOUTUBE_CLIENT_ID = os.environ.get('YOUTUBE_CLIENT_ID')
YOUTUBE_CLIENT_SECRET = os.environ.get('YOUTUBE_CLIENT_SECRET')
YOUTUBE_ACCESS_TOKEN = os.environ.get('YOUTUBE_ACCESS_TOKEN')
YOUTUBE_REFRESH_TOKEN = os.environ.get('YOUTUBE_REFRESH_TOKEN')
YOUTUBE_ENABLED = os.environ.get('YOUTUBE_ENABLED', 'true').lower() == 'true'

# YouTube Shorts specifications
# - Vertical video (9:16 aspect ratio)
# - Maximum 60 seconds
# - Maximum 256 MB file size
YOUTUBE_MAX_FILE_SIZE_MB = 256


def upload_video_to_youtube(video_path: str, title: str, description: str = "") -> dict:
    """
    Upload a video to YouTube as a Short.
    
    Args:
        video_path: Path to the video file
        title: Video title (include #Shorts for better discovery)
        description: Video description
    
    Returns:
        dict with keys: success (bool), video_id (str or None), error (str or None)
    """
    result = {'success': False, 'video_id': None, 'error': None}
    
    if not YOUTUBE_ENABLED:
        result['error'] = 'YouTube posting is disabled'
        return result
    
    if not YOUTUBE_ACCESS_TOKEN:
        result['error'] = 'YouTube access token not configured'
        return result
    
    if not os.path.exists(video_path):
        result['error'] = f'Video file not found: {video_path}'
        return result
    
    try:
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        print(f"  → YouTube: File size: {file_size:.2f} MB")
        
        if file_size > YOUTUBE_MAX_FILE_SIZE_MB:
            result['error'] = f'File too large for YouTube ({file_size:.2f} MB > {YOUTUBE_MAX_FILE_SIZE_MB} MB limit)'
            return result
        
        # Create credentials from token
        credentials = Credentials(
            token=YOUTUBE_ACCESS_TOKEN,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            token_uri='https://oauth2.googleapis.com/token'
        )
        
        # Build YouTube API client
        youtube = build('youtube', 'v3', credentials=credentials)
        
        # Prepare video metadata
        # Include #Shorts hashtag for better discovery
        full_description = description
        if '#Shorts' not in description and '#shorts' not in description.lower():
            full_description = description + '\n\n#Shorts'
        
        print("  → YouTube: Starting upload...")
        
        # Create media upload object
        media = MediaFileUpload(
            video_path,
            mimetype='video/mp4',
            resumable=True,
            chunksize=1024 * 1024  # 1MB chunks
        )
        
        # Create upload request
        request_body = {
            'snippet': {
                'title': title[:100],  # YouTube title limit
                'description': full_description[:5000],  # YouTube description limit
                'tags': ['Shorts', 'AI', 'Content'],
                'categoryId': '22'  # People & Blogs
            },
            'status': {
                'privacyStatus': 'public',
                'selfDeclaredMadeForKids': False
            }
        }
        
        # Start resumable upload
        upload_request = youtube.videos().insert(
            part='snippet,status',
            body=request_body,
            media_body=media
        )
        
        # Execute upload with progress tracking
        response = None
        retries = 0
        max_retries = 3
        
        while response is None and retries < max_retries:
            try:
                status, response = upload_request.next_chunk()
                
                if status:
                    progress = status.progress()
                    print(f"  → YouTube: Upload progress: {progress * 100:.1f}%")
                    
            except HttpError as e:
                if e.resp.status in [500, 502, 503, 504]:
                    retries += 1
                    print(f"  → YouTube: Retrying upload (attempt {retries}/{max_retries})...")
                    time.sleep(5)
                else:
                    raise
        
        if response and 'id' in response:
            video_id = response['id']
            result['success'] = True
            result['video_id'] = video_id
            print(f"  ✓ YouTube: Video uploaded successfully! ID: {video_id}")
            print(f"  → YouTube: URL: https://youtube.com/shorts/{video_id}")
        else:
            result['error'] = 'No video ID returned from YouTube'
        
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        result['error'] = f'YouTube API error: {error_content}'
        print(f"  ✗ YouTube: Upload failed: {error_content}")
        
    except Exception as e:
        result['error'] = str(e)
        print(f"  ✗ YouTube: Upload failed: {str(e)}")
    
    return result


def add_youtube_comment(video_id: str, comment_text: str) -> bool:
    """
    Post a top comment on a published YouTube video.
    
    Args:
        video_id: The YouTube video ID
        comment_text: Text of the comment to post
    
    Returns:
        True on success, False otherwise
    """
    try:
        if not YOUTUBE_ACCESS_TOKEN:
            print("  ⚠ YouTube: No access token for comment")
            return False
        
        credentials = Credentials(
            token=YOUTUBE_ACCESS_TOKEN,
            refresh_token=YOUTUBE_REFRESH_TOKEN,
            client_id=YOUTUBE_CLIENT_ID,
            client_secret=YOUTUBE_CLIENT_SECRET,
            token_uri='https://oauth2.googleapis.com/token'
        )
        
        youtube = build('youtube', 'v3', credentials=credentials)
        
        # Create comment
        comment_request = youtube.commentThreads().insert(
            part='snippet',
            body={
                'snippet': {
                    'videoId': video_id,
                    'topLevelComment': {
                        'snippet': {
                            'textOriginal': comment_text
                        }
                    }
                }
            }
        )
        
        response = comment_request.execute()
        comment_id = response.get('id')
        
        if comment_id:
            print(f"  ✓ YouTube: Top comment posted: {comment_id}")
            return True
        else:
            print(f"  ⚠ YouTube: Comment failed - no ID returned")
            return False
            
    except Exception as e:
        print(f"  ⚠ YouTube: Comment error: {e}")
        return False


def post_to_youtube_shorts(video_path: str, caption: str = "", top_comment: str = "") -> dict:
    """
    Interface for app.py to post to YouTube Shorts.
    
    Args:
        video_path: Path to the video file
        caption: Caption/description for the video
        top_comment: Optional top comment to post immediately after publishing
    
    Returns:
        dict with keys: success (bool), media_id (str or None), error (str or None)
    """
    # Extract title from caption (first line or first 100 chars)
    title = caption.split('\n')[0][:100] if caption else 'New Short'
    
    result = upload_video_to_youtube(video_path, title, caption)
    
    # Post top comment if video was successful and comment provided
    if result['success'] and top_comment and result['video_id']:
        add_youtube_comment(result['video_id'], top_comment)
    
    # Map to standard interface
    return {
        'success': result['success'],
        'media_id': result['video_id'],
        'error': result['error']
    }

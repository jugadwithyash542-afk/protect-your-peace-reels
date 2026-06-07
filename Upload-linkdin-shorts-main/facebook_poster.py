"""
Facebook Poster Module
Provides functions for posting videos to Facebook Reels/Page via the Graph API.
"""

import os
import requests
import json

# Configuration - loaded from environment
FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID')
FACEBOOK_ENABLED = os.environ.get('FACEBOOK_ENABLED', 'true').lower() == 'true'

# Facebook API endpoint for video uploads
API_BASE_URL = "https://graph-video.facebook.com/v19.0"

def add_facebook_comment(media_id: str, comment_text: str) -> bool:
    """
    Post a top comment on a published Facebook video/post.

    Args:
        media_id: The published post/video ID
        comment_text: Text of the comment to post

    Returns:
        True on success, False otherwise
    """
    try:
        url = f"https://graph.facebook.com/v19.0/{media_id}/comments"
        payload = {
            'message': comment_text,
            'access_token': FACEBOOK_ACCESS_TOKEN
        }
        response = requests.post(url, data=payload, timeout=30)
        data = response.json()
        if 'id' in data:
            print(f"  ✓ Facebook top comment posted: {data['id']}")
            return True
        print(f"  ⚠ Facebook comment failed: {data.get('error', {}).get('message', 'Unknown')}")
    except Exception as e:
        print(f"  ⚠ Facebook comment error: {e}")
    return False


def post_to_facebook(video_path: str, caption: str = "", top_comment: str = "") -> dict:
    """
    Upload a local video file to Facebook Page (as a Reel/Video).
    
    Args:
        video_path: Path to the video file
        caption: Text content for the post
        top_comment: Optional first comment to post immediately after publishing
    
    Returns:
        dict with keys: success (bool), media_id (str or None), error (str or None)
    """
    result = {'success': False, 'media_id': None, 'error': None}
    
    if not FACEBOOK_ENABLED:
        result['error'] = 'Facebook posting is disabled'
        return result
    
    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID:
        result['error'] = 'Facebook credentials not configured'
        return result
    
    if not os.path.exists(video_path):
        result['error'] = f'Video file not found: {video_path}'
        return result
    
    try:
        url = f"{API_BASE_URL}/{FACEBOOK_PAGE_ID}/videos"
        
        # Open file in binary mode
        with open(video_path, 'rb') as video_file:
            # Prepare payload
            payload = {
                'access_token': FACEBOOK_ACCESS_TOKEN,
                'description': caption,
                # 'title': caption[:50], # Optional title
            }
            
            # Prepare file
            files = {
                'source': video_file
            }
            
            # Send request
            response = requests.post(url, data=payload, files=files, timeout=300)
            data = response.json()
            
            if 'id' in data:
                result['success'] = True
                result['media_id'] = data['id']
                # Post top comment if provided
                if top_comment:
                    add_facebook_comment(data['id'], top_comment)
            else:
                error_msg = data.get('error', {}).get('message', 'Unknown error')
                result['error'] = error_msg
                
    except Exception as e:
        result['error'] = str(e)
    
    return result

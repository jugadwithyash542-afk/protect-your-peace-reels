"""
Instagram Poster Module
Provides functions for posting videos to Instagram Reels via the Graph API.
Uses temporary file hosting to provide video_url (required by Business Login for Instagram).
"""

import os
import time
import requests

# Configuration - loaded from environment
INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
INSTAGRAM_ACCOUNT_ID = os.environ.get('INSTAGRAM_ACCOUNT_ID')
INSTAGRAM_ENABLED = os.environ.get('INSTAGRAM_ENABLED', 'true').lower() == 'true'
API_VERSION = 'v21.0'


def upload_video_to_temp_host(video_path: str) -> str | None:
    """
    Upload video to a temporary file hosting service.
    Returns the public URL or None on failure.
    
    Uses tmpfiles.org which was tested and working.
    """
    try:
        with open(video_path, 'rb') as f:
            response = requests.post(
                'https://tmpfiles.org/api/v1/upload',
                files={'file': f},
                timeout=300
            )
        
        if response.status_code == 200:
            result = response.json()
            if result.get('status') == 'success':
                url = result.get('data', {}).get('url', '')
                # Convert to direct download URL
                direct_url = url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                return direct_url
    except Exception:
        pass
    
    return None


def create_instagram_container(video_url: str, caption: str = "") -> tuple[str | None, str | None]:
    """
    Create a media container for the Reel.
    Returns (container_id, error_message) tuple.
    """
    url = f"https://graph.instagram.com/{API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_url,
        'caption': caption,
        'access_token': INSTAGRAM_ACCESS_TOKEN
    }
    
    response = requests.post(url, data=payload, timeout=60)
    result = response.json()
    
    if 'id' in result:
        return result['id'], None
    
    error_msg = result.get('error', {}).get('message', 'Unknown error')
    return None, error_msg


def check_container_status(container_id: str, max_attempts: int = 60) -> tuple[bool, str | None]:
    """
    Wait for video processing to complete.
    Returns (success, error_message) tuple.
    """
    url = f"https://graph.instagram.com/{API_VERSION}/{container_id}"
    params = {
        'fields': 'status_code,status',
        'access_token': INSTAGRAM_ACCESS_TOKEN
    }
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, params=params, timeout=30)
            status_data = response.json()
            status = status_data.get('status_code')
            
            if status == 'FINISHED':
                return True, None
            elif status == 'ERROR':
                return False, f"Processing error: {status_data.get('status', 'Unknown')}"
            
            time.sleep(5)
        except Exception as e:
            time.sleep(5)
    
    return False, "Timeout waiting for video processing"


def publish_instagram_reel(container_id: str) -> tuple[str | None, str | None]:
    """
    Publish the processed Reel.
    Returns (media_id, error_message) tuple.
    """
    url = f"https://graph.instagram.com/{API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
    payload = {
        'creation_id': container_id,
        'access_token': INSTAGRAM_ACCESS_TOKEN
    }
    
    response = requests.post(url, data=payload, timeout=60)
    result = response.json()
    
    if 'id' in result:
        return result['id'], None
    
    error_msg = result.get('error', {}).get('message', 'Unknown error')
    return None, error_msg


def add_instagram_comment(media_id: str, comment_text: str) -> bool:
    """
    Post a top comment on a published Instagram media.

    Args:
        media_id: The published media ID
        comment_text: Text of the comment to post

    Returns:
        True on success, False otherwise
    """
    try:
        url = f"https://graph.instagram.com/{API_VERSION}/{media_id}/comments"
        payload = {
            'message': comment_text,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        response = requests.post(url, data=payload, timeout=30)
        result = response.json()
        if 'id' in result:
            print(f"  ✓ Instagram top comment posted: {result['id']}")
            return True
        print(f"  ⚠ Instagram comment failed: {result.get('error', {}).get('message', 'Unknown')}")
    except Exception as e:
        print(f"  ⚠ Instagram comment error: {e}")
    return False


def post_to_instagram_reel(video_path: str, caption: str = "", top_comment: str = "") -> dict:
    """
    Upload a local video file to Instagram as a Reel.
    
    Args:
        video_path: Path to the video file
        caption: Caption for the Reel
        top_comment: Optional first comment to post immediately after publishing
    
    Returns:
        dict with keys: success (bool), media_id (str or None), error (str or None)
    """
    result = {'success': False, 'media_id': None, 'error': None}
    
    if not INSTAGRAM_ENABLED:
        result['error'] = 'Instagram posting is disabled'
        return result
    
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        result['error'] = 'Instagram credentials not configured'
        return result
    
    if not os.path.exists(video_path):
        result['error'] = f'Video file not found: {video_path}'
        return result
    
    try:
        # Step 1: Upload to temp host to get public URL
        public_url = upload_video_to_temp_host(video_path)
        if not public_url:
            result['error'] = 'Failed to upload video to temporary host'
            return result
        
        # Step 2: Create container with video URL
        container_id, error = create_instagram_container(public_url, caption)
        if not container_id:
            result['error'] = f'Failed to create container: {error}'
            return result
        
        # Step 3: Wait for processing
        success, error = check_container_status(container_id)
        if not success:
            result['error'] = error or 'Video processing failed'
            return result
        
        # Step 4: Publish
        media_id, error = publish_instagram_reel(container_id)
        if media_id:
            result['success'] = True
            result['media_id'] = media_id
            # Step 5: Post top comment if provided
            if top_comment:
                add_instagram_comment(media_id, top_comment)
        else:
            result['error'] = f'Failed to publish: {error}'
        
    except Exception as e:
        result['error'] = str(e)
    
    return result

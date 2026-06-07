"""
Threads Poster Module
Provides functions for posting videos to Threads via the Graph API.
Uses temporary file hosting to provide video_url (required by the API).
"""

import os
import time
import requests

# Configuration - loaded from environment
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')
THREADS_ACCOUNT_ID = os.environ.get('THREADS_ACCOUNT_ID')
THREADS_ENABLED = os.environ.get('THREADS_ENABLED', 'true').lower() == 'true'
# Threads API endpoint
API_BASE_URL = "https://graph.threads.net/v1.0"


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


def create_threads_container(video_url: str, text: str = "") -> tuple[str | None, str | None]:
    """
    Create a media container for the Threads post.
    Returns (container_id, error_message) tuple.
    """
    url = f"{API_BASE_URL}/{THREADS_ACCOUNT_ID}/threads"
    payload = {
        'media_type': 'VIDEO',
        'video_url': video_url,
        'text': text,
        'access_token': THREADS_ACCESS_TOKEN
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
    url = f"{API_BASE_URL}/{container_id}"
    params = {
        'fields': 'status,error_message',
        'access_token': THREADS_ACCESS_TOKEN
    }
    
    for attempt in range(max_attempts):
        try:
            response = requests.get(url, params=params, timeout=30)
            status_data = response.json()
            status = status_data.get('status')
            
            if status == 'FINISHED':
                return True, None
            elif status == 'ERROR':
                return False, f"Processing error: {status_data.get('error_message', 'Unknown')}"
            
            time.sleep(5)
        except Exception as e:
            time.sleep(5)
    
    return False, "Timeout waiting for video processing"


def publish_threads_post(container_id: str) -> tuple[str | None, str | None]:
    """
    Publish the processed Threads post.
    Returns (media_id, error_message) tuple.
    """
    url = f"{API_BASE_URL}/{THREADS_ACCOUNT_ID}/threads_publish"
    payload = {
        'creation_id': container_id,
        'access_token': THREADS_ACCESS_TOKEN
    }
    
    response = requests.post(url, data=payload, timeout=60)
    result = response.json()
    
    if 'id' in result:
        return result['id'], None
    
    error_msg = result.get('error', {}).get('message', 'Unknown error')
    return None, error_msg


def add_threads_reply(post_id: str, reply_text: str) -> bool:
    """
    Post a top comment (reply thread) on a published Threads post.

    Args:
        post_id: The published post ID to reply to
        reply_text: Text for the reply thread

    Returns:
        True on success, False otherwise
    """
    try:
        # Step 1: Create a reply container
        url = f"{API_BASE_URL}/{THREADS_ACCOUNT_ID}/threads"
        payload = {
            'media_type': 'TEXT',
            'text': reply_text,
            'reply_to_id': post_id,
            'access_token': THREADS_ACCESS_TOKEN
        }
        response = requests.post(url, data=payload, timeout=30)
        result = response.json()

        if 'id' not in result:
            print(f"  ⚠ Threads reply container failed: {result.get('error', {}).get('message', 'Unknown')}")
            return False

        reply_container_id = result['id']

        # Step 2: Publish the reply
        pub_url = f"{API_BASE_URL}/{THREADS_ACCOUNT_ID}/threads_publish"
        pub_payload = {
            'creation_id': reply_container_id,
            'access_token': THREADS_ACCESS_TOKEN
        }
        pub_response = requests.post(pub_url, data=pub_payload, timeout=30)
        pub_result = pub_response.json()

        if 'id' in pub_result:
            print(f"  ✓ Threads top comment posted: {pub_result['id']}")
            return True
        print(f"  ⚠ Threads reply publish failed: {pub_result.get('error', {}).get('message', 'Unknown')}")
    except Exception as e:
        print(f"  ⚠ Threads reply error: {e}")
    return False


def post_to_threads(video_path: str, text: str = "", top_comment: str = "") -> dict:
    """
    Upload a local video file to Threads.
    
    Args:
        video_path: Path to the video file
        text: Text content for the post
        top_comment: Optional first reply to post immediately after publishing
    
    Returns:
        dict with keys: success (bool), media_id (str or None), error (str or None)
    """
    result = {'success': False, 'media_id': None, 'error': None}
    
    if not THREADS_ENABLED:
        result['error'] = 'Threads posting is disabled'
        return result
    
    if not THREADS_ACCESS_TOKEN or not THREADS_ACCOUNT_ID:
        result['error'] = 'Threads credentials not configured'
        return result
    
    if not os.path.exists(video_path):
        result['error'] = f'Video file not found: {video_path}'
        return result
    
    # Truncate text to 500 characters (Threads limit)
    if len(text) > 500:
        text = text[:497] + "..."
    
    try:
        # Step 1: Upload to temp host to get public URL
        public_url = upload_video_to_temp_host(video_path)
        if not public_url:
            result['error'] = 'Failed to upload video to temporary host'
            return result
        
        # Step 2: Create container with video URL
        container_id, error = create_threads_container(public_url, text)
        if not container_id:
            result['error'] = f'Failed to create container: {error}'
            return result
        
        # Step 3: Wait for processing
        success, error = check_container_status(container_id)
        if not success:
            result['error'] = error or 'Video processing failed'
            return result
        
        # Step 4: Publish
        media_id, error = publish_threads_post(container_id)
        if media_id:
            result['success'] = True
            result['media_id'] = media_id
            # Step 5: Post top comment as a reply if provided
            if top_comment:
                add_threads_reply(media_id, top_comment)
        else:
            result['error'] = f'Failed to publish: {error}'
        
    except Exception as e:
        result['error'] = str(e)
    
    return result

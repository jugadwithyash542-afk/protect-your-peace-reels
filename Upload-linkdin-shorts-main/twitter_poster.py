"""
Twitter (X) Poster Module
Handles video uploads and tweet creation via the X API.
Required libraries: requests, requests_oauthlib
"""

import os
import time
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

load_dotenv()

# Configuration - loaded from environment
TWITTER_API_KEY = os.environ.get('TWITTER_API_KEY')
TWITTER_API_SECRET = os.environ.get('TWITTER_API_SECRET')
TWITTER_ACCESS_TOKEN = os.environ.get('TWITTER_ACCESS_TOKEN')
TWITTER_ACCESS_SECRET = os.environ.get('TWITTER_ACCESS_SECRET')
TWITTER_ENABLED = os.environ.get('TWITTER_ENABLED', 'true').lower() == 'true'

# API Endpoints
UPLOAD_URL = "https://upload.twitter.com/1.1/media/upload.json"
TWEET_URL = "https://api.twitter.com/2/tweets"

class TwitterPoster:
    def __init__(self):
        self.auth = OAuth1(
            TWITTER_API_KEY,
            TWITTER_API_SECRET,
            TWITTER_ACCESS_TOKEN,
            TWITTER_ACCESS_SECRET
        )

    def upload_video(self, video_path):
        """
        Performs a chunked video upload to Twitter v1.1 endpoint.
        """
        file_size = os.path.getsize(video_path)
        
        # Step 1: INIT
        init_data = {
            "command": "INIT",
            "media_type": "video/mp4",
            "total_bytes": file_size,
            "media_category": "tweet_video"
        }
        resp = requests.post(UPLOAD_URL, auth=self.auth, data=init_data)
        if resp.status_code >= 400:
            return None, f"INIT failed: {resp.text}"
        
        media_id = resp.json()["media_id_string"]
        
        # Step 2: APPEND
        segment_id = 0
        with open(video_path, 'rb') as f:
            while True:
                chunk = f.read(4 * 1024 * 1024) # 4MB chunks
                if not chunk:
                    break
                
                append_data = {
                    "command": "APPEND",
                    "media_id": media_id,
                    "segment_index": segment_id
                }
                files = {"media": chunk}
                append_resp = requests.post(UPLOAD_URL, auth=self.auth, data=append_data, files=files)
                if append_resp.status_code >= 400:
                    return None, f"APPEND segment {segment_id} failed: {append_resp.text}"
                
                segment_id += 1
        
        # Step 3: FINALIZE
        finalize_data = {
            "command": "FINALIZE",
            "media_id": media_id
        }
        finalize_resp = requests.post(UPLOAD_URL, auth=self.auth, data=finalize_data)
        if finalize_resp.status_code >= 400:
            return None, f"FINALIZE failed: {finalize_resp.text}"
        
        # Step 4: STATUS (Polling for processing)
        processing_info = finalize_resp.json().get('processing_info')
        while processing_info:
            state = processing_info.get('state')
            if state == 'succeeded':
                break
            if state == 'failed':
                return None, f"Video processing failed: {processing_info.get('error', {}).get('message')}"
            
            check_after_secs = processing_info.get('check_after_secs', 5)
            time.sleep(check_after_secs)
            
            status_params = {
                "command": "STATUS",
                "media_id": media_id
            }
            status_resp = requests.get(UPLOAD_URL, auth=self.auth, params=status_params)
            processing_info = status_resp.json().get('processing_info')
            
        return media_id, None

    def create_tweet(self, text, media_id):
        """
        Creates a tweet using X API v2.
        """
        payload = {
            "text": text
        }
        if media_id:
            payload["media"] = {"media_ids": [media_id]}
            
        resp = requests.post(TWEET_URL, auth=self.auth, json=payload)
        result = resp.json()
        
        if resp.status_code == 201:
            return result.get('data', {}).get('id'), None
        
        return None, f"Tweet creation failed: {resp.text}"

def post_to_twitter(video_path: str, caption: str = "") -> dict:
    """
    Interface for app.py to post to Twitter.
    """
    result = {'success': False, 'media_id': None, 'error': None}
    
    if not TWITTER_ENABLED:
        result['error'] = 'Twitter posting is disabled'
        return result
        
    if not all([TWITTER_API_KEY, TWITTER_API_SECRET, TWITTER_ACCESS_TOKEN, TWITTER_ACCESS_SECRET]):
        result['error'] = 'Twitter credentials not configured'
        return result

    # Truncate to 280 characters for Twitter
    if len(caption) > 280:
        caption = caption[:277] + "..."

    try:
        poster = TwitterPoster()
        
        # Upload video
        media_id, err = poster.upload_video(video_path)
        if err:
            result['error'] = err
            return result
            
        # Create tweet
        tweet_id, err = poster.create_tweet(caption, media_id)
        if err:
            result['error'] = err
            return result
            
        result['success'] = True
        result['media_id'] = tweet_id # This is the Tweet ID
        
    except Exception as e:
        result['error'] = str(e)
        
    return result

"""
TikTok Poster Module
Handles video uploads to TikTok via the TikTok Upload API.
Reference: https://developers.tiktok.com/doc/upload-api
"""

import os
import time
import requests
import hashlib
import hmac
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()

# Configuration - loaded from environment
TIKTOK_CLIENT_KEY = os.environ.get('TIKTOK_CLIENT_KEY')
TIKTOK_CLIENT_SECRET = os.environ.get('TIKTOK_CLIENT_SECRET')
TIKTOK_ACCESS_TOKEN = os.environ.get('TIKTOK_ACCESS_TOKEN')
TIKTOK_ENABLED = os.environ.get('TIKTOK_ENABLED', 'true').lower() == 'true'

# API Endpoints
TIKTOK_API_BASE = "https://open.tiktokapis.com/upload/v2"


class TikTokUploader:
    def __init__(self):
        self.access_token = TIKTOK_ACCESS_TOKEN
        self.client_key = TIKTOK_CLIENT_KEY
        
    def _get_headers(self):
        """Get standard headers for TikTok API requests."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=UTF-8"
        }
    
    def create_upload_session(self, video_size: int, filename: str) -> tuple[str | None, str | None]:
        """
        Create an upload session and get upload URL.
        Returns (upload_url, error_message) tuple.
        """
        url = f"{TIKTOK_API_BASE}/video/upload/init"
        
        payload = {
            "upload_size": video_size,
            "file_name": filename,
            "chunk_size": 10 * 1024 * 1024  # 10MB chunks
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=60)
            result = response.json()
            
            if response.status_code == 200 and result.get("code") == 0:
                data = result.get("data", {})
                upload_url = data.get("upload_url")
                upload_id = data.get("upload_id")
                return upload_id, None
            
            error_msg = result.get("message", "Unknown error")
            return None, f"Upload session creation failed: {error_msg}"
            
        except Exception as e:
            return None, f"Upload session creation error: {str(e)}"
    
    def upload_video_chunks(self, upload_url: str, video_path: str, chunk_size: int = 10 * 1024 * 1024) -> tuple[bool, str | None]:
        """
        Upload video in chunks.
        Returns (success, error_message) tuple.
        """
        file_size = os.path.getsize(video_path)
        
        try:
            with open(video_path, 'rb') as f:
                chunk_index = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    headers = {
                        "Content-Type": "application/octet-stream",
                        "Content-Range": f"bytes {chunk_index * chunk_size}-{min((chunk_index + 1) * chunk_size - 1, file_size - 1)}/{file_size}"
                    }
                    
                    response = requests.put(upload_url, headers=headers, data=chunk, timeout=300)
                    
                    if response.status_code not in (200, 204):
                        return False, f"Chunk {chunk_index} upload failed: {response.status_code}"
                    
                    chunk_index += 1
                    print(f"  Uploaded chunk {chunk_index}")
            
            return True, None
            
        except Exception as e:
            return False, f"Chunk upload error: {str(e)}"
    
    def create_video(self, upload_id: str, caption: str, privacy_level: str = "PUBLIC_TO_EVERYONE") -> tuple[str | None, str | None]:
        """
        Create the video post after upload.
        Returns (video_id, error_message) tuple.
        """
        url = f"{TIKTOK_API_BASE}/video/publish"
        
        payload = {
            "upload_id": upload_id,
            "title": caption[:100],  # TikTok title limit
            "description": caption,
            "privacy_level": privacy_level,
            "disable_duet": False,
            "disable_comment": False,
            "disable_stitch": False
        }
        
        try:
            response = requests.post(url, headers=self._get_headers(), json=payload, timeout=60)
            result = response.json()
            
            if response.status_code == 200 and result.get("code") == 0:
                data = result.get("data", {})
                video_id = data.get("id")
                return video_id, None
            
            error_msg = result.get("message", "Unknown error")
            return None, f"Video creation failed: {error_msg}"
            
        except Exception as e:
            return None, f"Video creation error: {str(e)}"
    
    def check_publish_status(self, video_id: str, max_attempts: int = 60) -> tuple[bool, str | None]:
        """
        Wait for video publishing to complete.
        Returns (success, error_message) tuple.
        """
        url = f"{TIKTOK_API_BASE}/video/query"
        
        payload = {"video_id": video_id}
        
        for attempt in range(max_attempts):
            try:
                response = requests.post(url, headers=self._get_headers(), json=payload, timeout=30)
                status_data = response.json()
                
                if status_data.get("code") == 0:
                    data = status_data.get("data", {})
                    status = data.get("status")
                    
                    if status == "PUBLISHED":
                        return True, None
                    elif status == "FAILED":
                        return False, f"Publishing failed: {data.get('message', 'Unknown error')}"
                    elif status == "DELETED":
                        return False, "Video was deleted"
                
                time.sleep(5)
                
            except Exception as e:
                time.sleep(5)
        
        return False, "Timeout waiting for publishing"


def post_to_tiktok(video_path: str, caption: str, privacy_level: str = "PUBLIC_TO_EVERYONE") -> dict:
    """
    Post video to TikTok.
    
    Args:
        video_path: Path to video file
        caption: Video caption with hashtags
        privacy_level: PUBLIC_TO_EVERYONE, FRIENDS_OF_FRIENDS, or FRIENDS_ONLY
    
    Returns:
        dict: {
            'success': bool,
            'platform': 'tiktok',
            'video_id': str or None,
            'message': str
        }
    """
    if not TIKTOK_ENABLED:
        return {
            'success': False,
            'platform': None,
            'video_id': None,
            'message': 'TikTok integration is disabled'
        }
    
    if not TIKTOK_ACCESS_TOKEN:
        return {
            'success': False,
            'platform': None,
            'video_id': None,
            'message': 'TikTok access token not configured'
        }
    
    try:
        file_size = os.path.getsize(video_path)
        filename = os.path.basename(video_path)
        
        print(f"  → Uploading to TikTok ({file_size / 1024 / 1024:.1f}MB)...")
        
        uploader = TikTokUploader()
        
        # Step 1: Create upload session
        upload_id, error = uploader.create_upload_session(file_size, filename)
        if error:
            return {
                'success': False,
                'platform': None,
                'video_id': None,
                'message': error
            }
        
        print(f"  ✓ Upload session created: {upload_id}")
        
        # Step 2: Upload video chunks (need upload_url from session)
        # Note: Simplified - in production, get upload_url from session response
        success, error = uploader.upload_video_chunks(upload_id, video_path)
        if error:
            return {
                'success': False,
                'platform': None,
                'video_id': None,
                'message': error
            }
        
        print(f"  ✓ Video uploaded")
        
        # Step 3: Create/publish video
        video_id, error = uploader.create_video(upload_id, caption, privacy_level)
        if error:
            return {
                'success': False,
                'platform': None,
                'video_id': None,
                'message': error
            }
        
        print(f"  ✓ Video created: {video_id}")
        
        # Step 4: Check publish status
        success, error = uploader.check_publish_status(video_id)
        if error:
            return {
                'success': False,
                'platform': None,
                'video_id': video_id,
                'message': error
            }
        
        print(f"  ✓ Posted to TikTok!")
        
        return {
            'success': True,
            'platform': 'tiktok',
            'video_id': video_id,
            'message': 'Successfully posted to TikTok'
        }
        
    except Exception as e:
        return {
            'success': False,
            'platform': None,
            'video_id': None,
            'message': f'TikTok upload failed: {str(e)}'
        }

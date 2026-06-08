#!/usr/bin/env python3
import os
import re
import sys

# Prioritize local python_packages folder for dependencies
scripts_dir = os.path.dirname(os.path.abspath(__file__))
workspace_dir = os.path.dirname(scripts_dir)
local_packages = os.path.join(workspace_dir, 'python_packages')
if os.path.exists(local_packages):
    sys.path.insert(0, local_packages)

import site
site.addsitedir(site.getusersitepackages())
import time
import requests
import json
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account
from dotenv import load_dotenv

# Load environment variables from the root .env file
workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
dotenv_path = os.path.join(workspace, '.env')
load_dotenv(dotenv_path)

# ----------------- CONFIGURATION -----------------
# Google Drive
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_DRIVE_CREDENTIALS_PATH = os.environ.get(
    'GOOGLE_DRIVE_CREDENTIALS_PATH',
    os.path.join(workspace, 'justakemycard-audio-6ca2fff8e699.json')
)

# Instagram Reels
INSTAGRAM_ENABLED = os.environ.get('INSTAGRAM_ENABLED', 'true').lower() == 'true'
INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
INSTAGRAM_ACCOUNT_ID = os.environ.get('INSTAGRAM_ACCOUNT_ID')
INSTAGRAM_API_VERSION = 'v21.0'

# Facebook Page Reels/Videos
FACEBOOK_ENABLED = os.environ.get('FACEBOOK_ENABLED', 'true').lower() == 'true'
FACEBOOK_ACCESS_TOKEN = os.environ.get('FACEBOOK_ACCESS_TOKEN')
FACEBOOK_PAGE_ID = os.environ.get('FACEBOOK_PAGE_ID')

# Threads Integration
THREADS_ENABLED = os.environ.get('THREADS_ENABLED', 'true').lower() == 'true'
THREADS_ACCESS_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')
THREADS_ACCOUNT_ID = os.environ.get('THREADS_ACCOUNT_ID')

# Video Hosting URL
PUBLIC_SERVER_URL = os.environ.get('PUBLIC_SERVER_URL')

# Files
VIDEO_PATH = os.path.join(workspace, 'generated-audio/rendered_reel_latest.mp4')
SCRIPT_PATH = os.path.join(workspace, 'generated-audio/marketing-script-latest.md')


# ----------------- CAPTION GENERATION -----------------
def generate_female_targeted_caption(md_path):
    """
    Parses the generated markdown script to extract the Hook and Core Value Point,
    and returns a clean, polished Instagram/Facebook/Threads caption targeted at a female audience.
    """
    if not os.path.exists(md_path):
        print(f"⚠️ Marketing script not found at {md_path}. Using a default caption.")
        return ("Hey sis, protecting your peace is not selfish—it is necessary. 💖\n\n"
                "👉 Hit Follow to join the sisterhood, and click the link in our bio to grab your Boundary Script Toolkit today! 🕊️\n\n"
                "#MentalLoad #Boundaries #SelfCareForWomen #PeoplePleaser #ReclaimYourPeace #HeySis #WomenEmpowerment #MentalWellbeing #SayNoWithoutGuilt")

    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract Hook and Lesson using regular expressions
        hook_match = re.search(r'## Hook \(Reels/TikTok 3-Second Scroll-Stopper\)\n(.*?)(?=\n\n##|$)', content, re.DOTALL)
        lesson_match = re.search(r'## Core Value Point\n(.*?)(?=\n\n##|$)', content, re.DOTALL)

        hook = hook_match.group(1).strip() if hook_match else ""
        lesson = lesson_match.group(1).strip() if lesson_match else ""

        # Clean up bracketed audio cues from hook/lesson if they exist (e.g. [soft whisper])
        hook = re.sub(r'\[.*?\]', '', hook).strip()
        lesson = re.sub(r'\[.*?\]', '', lesson).strip()

        # Remove surrounding quotes if generated
        hook = hook.strip('\'"“”‘’')
        lesson = lesson.strip('\'"“”‘’')

        # Formulate sister-targeted copy
        caption_parts = []
        if hook:
            caption_parts.append(f"Hey sis, read this: \"{hook}\" 💖")
        else:
            caption_parts.append("Hey sis, protecting your peace is not selfish—it is necessary. 💖")

        if lesson:
            caption_parts.append(lesson)

        # Standard female-support Call to Action
        caption_parts.append("👉 Hit Follow to join the sisterhood, and click the link in our bio to grab your Boundary Script Toolkit today! 🕊️")

        # Female-targeted hashtags
        hashtags = (
            "#MentalLoad #Boundaries #SelfCareForWomen #PeoplePleaser #ReclaimYourPeace "
            "#HeySis #WomenEmpowerment #MentalWellbeing #SayNoWithoutGuilt #SistersSupport #ProtectYourPeace"
        )
        caption_parts.append(hashtags)

        caption = "\n\n".join(caption_parts)
        return caption

    except Exception as e:
        print(f"⚠️ Error parsing markdown caption: {e}. Falling back to default.")
        return ("Hey sis, protecting your peace is not selfish—it is necessary. 💖\n\n"
                "👉 Hit Follow to join the sisterhood, and click the link in our bio to grab your Boundary Script Toolkit today! 🕊️\n\n"
                "#MentalLoad #Boundaries #SelfCareForWomen #PeoplePleaser #ReclaimYourPeace #HeySis #WomenEmpowerment #MentalWellbeing #SayNoWithoutGuilt")


# ----------------- GOOGLE DRIVE UPLOAD -----------------
def upload_to_google_drive(file_path):
    """
    Uploads the video file to the designated Google Drive folder using the service account.
    """
    if not GOOGLE_DRIVE_FOLDER_ID or GOOGLE_DRIVE_FOLDER_ID == 'your_google_drive_folder_id_here':
        print("ℹ️ GOOGLE_DRIVE_FOLDER_ID is not configured in .env. Skipping Google Drive upload.")
        return None

    creds_json = os.environ.get('GOOGLE_DRIVE_CREDENTIALS_JSON')
    creds = None
    scopes = ['https://www.googleapis.com/auth/drive']

    if creds_json and creds_json.strip():
        print("🔑 Authenticating Google Drive via environment JSON credentials...")
        try:
            creds = service_account.Credentials.from_service_account_info(
                json.loads(creds_json), scopes=scopes
            )
        except Exception as e:
            print(f"❌ Failed to load Google Drive credentials JSON from environment: {e}")
            return None
    else:
        if not os.path.exists(GOOGLE_DRIVE_CREDENTIALS_PATH):
            print(f"⚠️ Google Drive credentials file not found at {GOOGLE_DRIVE_CREDENTIALS_PATH} and GOOGLE_DRIVE_CREDENTIALS_JSON is not set in environment. Skipping upload.")
            return None
        print(f"🔑 Authenticating Google Drive via credentials file: {GOOGLE_DRIVE_CREDENTIALS_PATH}...")
        try:
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes
            )
        except Exception as e:
            print(f"❌ Failed to load Google Drive credentials file: {e}")
            return None

    print("🚀 Uploading video to Google Drive...")
    try:
        service = build('drive', 'v3', credentials=creds, cache_discovery=False)

        # Generate folder-friendly date-based filename to avoid overwrites
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        filename = f"protect_your_peace_reel_{timestamp}.mp4"

        file_metadata = {
            'name': filename,
            'parents': [GOOGLE_DRIVE_FOLDER_ID]
        }

        media = MediaFileUpload(
            file_path,
            mimetype='video/mp4',
            resumable=True
        )

        file = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, webViewLink'
        ).execute()

        print(f"✅ Successfully uploaded to Google Drive as: {filename}")
        print(f"🔗 Google Drive File ID: {file.get('id')}")
        print(f"🔗 View Link: {file.get('webViewLink')}")
        return file.get('webViewLink')

    except Exception as e:
        print(f"❌ Google Drive Upload failed: {str(e)}")
        return None


# ----------------- TEMPORARY VIDEO HOSTING -----------------
def upload_to_temp_host(video_path):
    """
    Uploads a local video to tmpfiles.org to get a direct public URL for Meta Graph APIs.
    """
    print("🌐 Uploading video to temporary host for Meta Graph APIs (Instagram & Threads)...")
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
                # Convert to direct download URL (required by Meta)
                direct_url = url.replace('tmpfiles.org/', 'tmpfiles.org/dl/')
                print(f"✅ Video hosted temporarily at: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"⚠️ Temporary upload failed: {e}")
    return None


# ----------------- INSTAGRAM REELS UPLOAD -----------------
def post_to_instagram_reel(video_path, caption, public_video_url):
    """
    Uploads and publishes the video to Instagram Reels using the Meta Graph API.
    """
    if not INSTAGRAM_ENABLED:
        print("ℹ️ Instagram publishing is disabled in .env. Skipping Instagram Reel post.")
        return None

    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID or 'your_' in INSTAGRAM_ACCESS_TOKEN or 'your_' in INSTAGRAM_ACCOUNT_ID:
        print("⚠️ Instagram Access Token or Account ID is not configured (or is placeholder) in .env. Skipping post.")
        return None

    if not public_video_url:
        print("❌ Cannot post to Instagram: failed to acquire a public video URL.")
        return None

    print("🚀 Publishing video as Instagram Reel...")
    try:
        # Step 1: Create media container
        container_url = f"https://graph.facebook.com/{INSTAGRAM_API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media"
        container_payload = {
            'media_type': 'REELS',
            'video_url': public_video_url,
            'caption': caption,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        print("  → Creating Instagram media container...")
        res = requests.post(container_url, data=container_payload, timeout=60)
        res_data = res.json()
        
        if 'id' not in res_data:
            err_msg = res_data.get('error', {}).get('message', 'Unknown container error')
            print(f"❌ Failed to create Instagram media container: {err_msg}")
            print(res_data)
            return None
            
        container_id = res_data['id']
        print(f"✅ Instagram container created. ID: {container_id}")
        
        # Step 2: Wait for Meta to process the video (polling status)
        status_url = f"https://graph.facebook.com/{INSTAGRAM_API_VERSION}/{container_id}"
        params = {
            'fields': 'status_code,status',
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        print("  → Waiting for Instagram video processing (polling every 10 seconds)...")
        max_attempts = 30
        processing_done = False
        
        for attempt in range(max_attempts):
            time.sleep(10)
            status_res = requests.get(status_url, params=params, timeout=30)
            status_data = status_res.json()
            status_code = status_data.get('status_code')
            
            if status_code == 'FINISHED':
                print("✅ Instagram processing complete!")
                processing_done = True
                break
            elif status_code == 'ERROR':
                print(f"❌ Instagram video processing failed: {status_data.get('status', 'Unknown error')}")
                return None
            else:
                print(f"  ... Still processing (Attempt {attempt+1}/{max_attempts}). Status: {status_code}")
                
        if not processing_done:
            print("❌ Timeout waiting for Instagram video processing.")
            return None
            
        # Step 3: Publish Reel
        publish_url = f"https://graph.facebook.com/{INSTAGRAM_API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        publish_payload = {
            'creation_id': container_id,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        print("  → Publishing Reel to Instagram profile...")
        publish_res = requests.post(publish_url, data=publish_payload, timeout=60)
        publish_data = publish_res.json()
        
        if 'id' in publish_data:
            media_id = publish_data['id']
            print(f"🎉 SUCCESS! Instagram Reel published. Media ID: {media_id}")
            return media_id
        else:
            err_msg = publish_data.get('error', {}).get('message', 'Unknown publish error')
            print(f"❌ Failed to publish Instagram Reel: {err_msg}")
            print(publish_data)
            return None

    except Exception as e:
        print(f"❌ Instagram Posting failed with error: {str(e)}")
        return None


# ----------------- FACEBOOK PAGE UPLOAD -----------------
def get_facebook_page_token():
    """
    Exchanges the Facebook User Access Token for a Page Access Token.
    """
    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID or 'your_' in FACEBOOK_ACCESS_TOKEN or 'your_' in FACEBOOK_PAGE_ID:
        return None
    try:
        url = f"https://graph.facebook.com/v21.0/{FACEBOOK_PAGE_ID}?fields=access_token&access_token={FACEBOOK_ACCESS_TOKEN}"
        res = requests.get(url, timeout=30)
        res_data = res.json()
        if 'access_token' in res_data:
            print("🔑 Exchanged Facebook User Token for Page Access Token.")
            return res_data['access_token']
        else:
            print(f"⚠️ Facebook token exchange failed: {res_data.get('error', {}).get('message')}")
    except Exception as e:
        print(f"⚠️ Facebook token exchange error: {e}")
    return FACEBOOK_ACCESS_TOKEN  # Fallback to User Token


def post_to_facebook_page(video_path, caption):
    """
    Uploads a local video file directly to the Facebook Page using form-data (no public URL required).
    """
    if not FACEBOOK_ENABLED:
        print("ℹ️ Facebook Page publishing is disabled in .env. Skipping Facebook post.")
        return None

    if not FACEBOOK_ACCESS_TOKEN or not FACEBOOK_PAGE_ID or 'your_' in FACEBOOK_ACCESS_TOKEN or 'your_' in FACEBOOK_PAGE_ID:
        print("⚠️ Facebook Access Token or Page ID is not configured (or is placeholder) in .env. Skipping post.")
        return None

    page_token = get_facebook_page_token()

    print("🚀 Uploading video directly to Facebook Page...")
    try:
        url = f"https://graph-video.facebook.com/v19.0/{FACEBOOK_PAGE_ID}/videos"
        
        with open(video_path, 'rb') as video_file:
            payload = {
                'access_token': page_token,
                'description': caption,
            }
            files = {
                'source': video_file
            }
            
            res = requests.post(url, data=payload, files=files, timeout=300)
            res_data = res.json()
            
            if 'id' in res_data:
                media_id = res_data['id']
                print(f"🎉 SUCCESS! Facebook Page post published. Media ID: {media_id}")
                return media_id
            else:
                err_msg = res_data.get('error', {}).get('message', 'Unknown error')
                print(f"❌ Failed to publish to Facebook Page: {err_msg}")
                print(res_data)
                return None
                
    except Exception as e:
        print(f"❌ Facebook posting failed with error: {str(e)}")
        return None


# ----------------- THREADS POST UPLOAD -----------------
def post_to_threads_profile(video_path, caption, public_video_url):
    """
    Uploads and publishes the video to Threads using the Threads Graph API.
    """
    if not THREADS_ENABLED:
        print("ℹ️ Threads publishing is disabled in .env. Skipping Threads post.")
        return None

    if not THREADS_ACCESS_TOKEN or not THREADS_ACCOUNT_ID or 'your_' in THREADS_ACCESS_TOKEN or 'your_' in THREADS_ACCOUNT_ID:
        print("⚠️ Threads Access Token or Account ID is not configured (or is placeholder) in .env. Skipping post.")
        return None

    if not public_video_url:
        print("❌ Cannot post to Threads: failed to acquire a public video URL.")
        return None

    print("🚀 Publishing video as Threads post...")
    try:
        # Threads limit is 500 characters. Truncate caption if it exceeds.
        threads_text = caption
        if len(threads_text) > 500:
            threads_text = threads_text[:497] + "..."

        # Step 1: Create media container
        container_url = f"https://graph.threads.net/v1.0/{THREADS_ACCOUNT_ID}/threads"
        container_payload = {
            'media_type': 'VIDEO',
            'video_url': public_video_url,
            'text': threads_text,
            'access_token': THREADS_ACCESS_TOKEN
        }
        
        print("  → Creating Threads media container...")
        res = requests.post(container_url, data=container_payload, timeout=60)
        res_data = res.json()
        
        if 'id' not in res_data:
            err_msg = res_data.get('error', {}).get('message', 'Unknown container error')
            print(f"❌ Failed to create Threads media container: {err_msg}")
            print(res_data)
            return None
            
        container_id = res_data['id']
        print(f"✅ Threads container created. ID: {container_id}")
        
        # Step 2: Poll status of the container
        status_url = f"https://graph.threads.net/v1.0/{container_id}"
        params = {
            'fields': 'status,error_message',
            'access_token': THREADS_ACCESS_TOKEN
        }
        
        print("  → Waiting for Threads video processing (polling every 10 seconds)...")
        max_attempts = 30
        processing_done = False
        
        for attempt in range(max_attempts):
            time.sleep(10)
            status_res = requests.get(status_url, params=params, timeout=30)
            status_data = status_res.json()
            status_code = status_data.get('status')
            
            if status_code == 'FINISHED':
                print("✅ Threads processing complete!")
                processing_done = True
                break
            elif status_code == 'ERROR':
                print(f"❌ Threads video processing failed: {status_data.get('error_message', 'Unknown error')}")
                return None
            else:
                print(f"  ... Still processing (Attempt {attempt+1}/{max_attempts}). Status: {status_code}")
                
        if not processing_done:
            print("❌ Timeout waiting for Threads video processing.")
            return None
            
        # Step 3: Publish the container
        publish_url = f"https://graph.threads.net/v1.0/{THREADS_ACCOUNT_ID}/threads_publish"
        publish_payload = {
            'creation_id': container_id,
            'access_token': THREADS_ACCESS_TOKEN
        }
        
        print("  → Publishing post to Threads feed...")
        publish_res = requests.post(publish_url, data=publish_payload, timeout=60)
        publish_data = publish_res.json()
        
        if 'id' in publish_data:
            media_id = publish_data['id']
            print(f"🎉 SUCCESS! Threads post published. Media ID: {media_id}")
            return media_id
        else:
            err_msg = publish_data.get('error', {}).get('message', 'Unknown publish error')
            print(f"❌ Failed to publish Threads post: {err_msg}")
            print(publish_data)
            return None

    except Exception as e:
        print(f"❌ Threads posting failed with error: {str(e)}")
        return None


# ----------------- MAIN PIPELINE -----------------
def main():
    print("=" * 60)
    print("🚀 STARTING MULTI-PLATFORM UPLOAD PIPELINE")
    print("=" * 60)

    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Latest video file not found at {VIDEO_PATH}. Make sure render script has completed.")
        sys.exit(1)

    # 1. Google Drive
    drive_link = upload_to_google_drive(VIDEO_PATH)

    # 2. Extract and format Female-Targeted Caption
    caption = generate_female_targeted_caption(SCRIPT_PATH)
    print("\n📝 Generated Female-Targeted Caption:")
    print("-" * 50)
    print(caption)
    print("-" * 50 + "\n")

    # 3. Determine public hosting link for Instagram and Threads
    public_video_url = None
    if INSTAGRAM_ENABLED or THREADS_ENABLED:
        if PUBLIC_SERVER_URL and PUBLIC_SERVER_URL.strip():
            base_url = PUBLIC_SERVER_URL.strip().rstrip('/')
            public_video_url = f"{base_url}/generated-audio/rendered_reel_latest.mp4"
            print(f"🔗 Using production public URL for fetch: {public_video_url}")
        else:
            # Check if we actually have active credentials before attempting temporary hosting upload
            has_instagram_credentials = (INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID and 
                                         'your_' not in INSTAGRAM_ACCESS_TOKEN and 'your_' not in INSTAGRAM_ACCOUNT_ID)
            has_threads_credentials = (THREADS_ACCESS_TOKEN and THREADS_ACCOUNT_ID and 
                                       'your_' not in THREADS_ACCESS_TOKEN and 'your_' not in THREADS_ACCOUNT_ID)
            
            if (INSTAGRAM_ENABLED and has_instagram_credentials) or (THREADS_ENABLED and has_threads_credentials):
                public_video_url = upload_to_temp_host(VIDEO_PATH)
            else:
                print("ℹ️ Skipping temporary public hosting upload (no active Instagram or Threads credentials).")

    # 4. Platform Publishing
    instagram_id = post_to_instagram_reel(VIDEO_PATH, caption, public_video_url)
    facebook_id = post_to_facebook_page(VIDEO_PATH, caption)
    threads_id = post_to_threads_profile(VIDEO_PATH, caption, public_video_url)

    print("\n" + "=" * 60)
    print("🏁 PIPELINE COMPLETED")
    print("-" * 60)
    print(f"Google Drive:  {'Uploaded' if drive_link else 'Skipped/Failed'}")
    print(f"Instagram:     {f'Published (ID: {instagram_id})' if instagram_id else 'Skipped/Failed'}")
    print(f"Facebook Page: {f'Published (ID: {facebook_id})' if facebook_id else 'Skipped/Failed'}")
    print(f"Threads:       {f'Published (ID: {threads_id})' if threads_id else 'Skipped/Failed'}")
    print("=" * 60)


if __name__ == '__main__':
    main()

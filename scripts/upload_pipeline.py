#!/usr/bin/env python3
import os
import re
import sys
import time
import requests
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

# Instagram
INSTAGRAM_ENABLED = os.environ.get('INSTAGRAM_ENABLED', 'true').lower() == 'true'
INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN')
INSTAGRAM_ACCOUNT_ID = os.environ.get('INSTAGRAM_ACCOUNT_ID')
API_VERSION = 'v21.0'

# Video Hosting URL
PUBLIC_SERVER_URL = os.environ.get('PUBLIC_SERVER_URL')

# Files
VIDEO_PATH = os.path.join(workspace, 'generated-audio/rendered_reel_latest.mp4')
SCRIPT_PATH = os.path.join(workspace, 'generated-audio/marketing-script-latest.md')


# ----------------- CAPTION GENERATION -----------------
def generate_female_targeted_caption(md_path):
    """
    Parses the generated markdown script to extract the Hook and Core Value Point,
    and returns a clean, polished Instagram caption targeted at a female audience.
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

    if not os.path.exists(GOOGLE_DRIVE_CREDENTIALS_PATH):
        print(f"⚠️ Google Drive credentials file not found at {GOOGLE_DRIVE_CREDENTIALS_PATH}. Skipping upload.")
        return None

    print("🚀 Uploading video to Google Drive...")
    try:
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(
            GOOGLE_DRIVE_CREDENTIALS_PATH, scopes=scopes
        )
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


# ----------------- INSTAGRAM REELS UPLOAD -----------------
def upload_to_temp_host(video_path):
    """
    Uploads a local video to tmpfiles.org to get a direct public URL for Meta Graph API.
    """
    print("🌐 Uploading video to temporary host for Meta Graph API...")
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


def post_to_instagram_reel(video_path, caption):
    """
    Uploads and publishes the video to Instagram Reels using the Meta Graph API.
    """
    if not INSTAGRAM_ENABLED:
        print("ℹ️ Instagram publishing is disabled in .env. Skipping Instagram Reel post.")
        return None

    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID or 'your_' in INSTAGRAM_ACCESS_TOKEN or 'your_' in INSTAGRAM_ACCOUNT_ID:
        print("⚠️ Instagram Access Token or Account ID is not configured (or is placeholder) in .env. Skipping post.")
        return None

    print("🚀 Publishing video as Instagram Reel...")
    
    # 1. Determine Public Video URL (Meta must be able to fetch the video)
    video_url = None
    if PUBLIC_SERVER_URL and PUBLIC_SERVER_URL.strip():
        # Clean double slashes
        base_url = PUBLIC_SERVER_URL.strip().rstrip('/')
        video_url = f"{base_url}/generated-audio/rendered_reel_latest.mp4"
        print(f"🔗 Using production URL for Meta fetch: {video_url}")
    else:
        video_url = upload_to_temp_host(video_path)
        
    if not video_url:
        print("❌ Cannot post to Instagram: failed to acquire a public video URL.")
        return None

    try:
        # Step 2: Create media container
        container_url = f"https://graph.facebook.com/{API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media"
        container_payload = {
            'media_type': 'REELS',
            'video_url': video_url,
            'caption': caption,
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        print("  → Creating media container...")
        res = requests.post(container_url, data=container_payload, timeout=60)
        res_data = res.json()
        
        if 'id' not in res_data:
            err_msg = res_data.get('error', {}).get('message', 'Unknown container error')
            print(f"❌ Failed to create Instagram media container: {err_msg}")
            print(res_data)
            return None
            
        container_id = res_data['id']
        print(f"✅ Container created. ID: {container_id}")
        
        # Step 3: Wait for Meta to process the video (polling status)
        status_url = f"https://graph.facebook.com/{API_VERSION}/{container_id}"
        params = {
            'fields': 'status_code,status',
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }
        
        print("  → Waiting for Meta processing (polling every 10 seconds)...")
        max_attempts = 30
        processing_done = False
        
        for attempt in range(max_attempts):
            time.sleep(10)
            status_res = requests.get(status_url, params=params, timeout=30)
            status_data = status_res.json()
            status_code = status_data.get('status_code')
            
            if status_code == 'FINISHED':
                print("✅ Meta processing complete!")
                processing_done = True
                break
            elif status_code == 'ERROR':
                print(f"❌ Meta video processing failed: {status_data.get('status', 'Unknown error')}")
                return None
            else:
                print(f"  ... Still processing (Attempt {attempt+1}/{max_attempts}). Status: {status_code}")
                
        if not processing_done:
            print("❌ Timeout waiting for Meta video processing.")
            return None
            
        # Step 4: Publish Reel
        publish_url = f"https://graph.facebook.com/{API_VERSION}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
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


# ----------------- MAIN PIPELINE -----------------
def main():
    print("=" * 60)
    print("🚀 STARTING UPLOAD PIPELINE (Google Drive & Instagram)")
    print("=" * 60)

    if not os.path.exists(VIDEO_PATH):
        print(f"❌ Latest video file not found at {VIDEO_PATH}. Make sure render script has completed.")
        sys.exit(1)

    # 1. Google Drive
    drive_link = upload_to_google_drive(VIDEO_PATH)

    # 2. Instagram Reels
    caption = generate_female_targeted_caption(SCRIPT_PATH)
    print("\n📝 Generated Female-Targeted Caption:")
    print("-" * 50)
    print(caption)
    print("-" * 50 + "\n")
    
    instagram_media_id = post_to_instagram_reel(VIDEO_PATH, caption)

    print("\n" + "=" * 60)
    print("🏁 PIPELINE COMPLETED")
    print("-" * 60)
    print(f"Google Drive: {'Uploaded' if drive_link else 'Skipped/Failed'}")
    print(f"Instagram: {'Published (Media ID: ' + instagram_media_id + ')' if instagram_media_id else 'Skipped/Failed'}")
    print("=" * 60)


if __name__ == '__main__':
    main()

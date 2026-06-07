"""
LinkedIn Video Automation - Flask App for Vercel
Randomly selects videos from Google Drive, generates AI descriptions, and posts to LinkedIn
"""

import os
import random
import time
import tempfile
from io import BytesIO
from flask import Flask, render_template_string, redirect, session, Response, jsonify, stream_with_context, request
from google_drive_helper import GoogleDriveManager
from google import genai
import requests
from dotenv import load_dotenv
import queue
import threading
from device_manager import DeviceManager
from instagram_poster import post_to_instagram_reel, INSTAGRAM_ENABLED
from threads_poster import post_to_threads, THREADS_ENABLED
from facebook_poster import post_to_facebook, FACEBOOK_ENABLED
from twitter_poster import post_to_twitter, TWITTER_ENABLED
from tiktok_poster import post_to_tiktok, TIKTOK_ENABLED
from youtube_poster import post_to_youtube_shorts, YOUTUBE_ENABLED

# Load environment variables from .env file (for local development)
load_dotenv()

# Import retry utilities and CMO alert system
from retry_utils import retry_operation, RetryError, is_retryable_exception
from cmo_alerts import send_cmo_alert

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-production')

# Global dict to store log queues for each video processing
log_queues = {}

# Configuration from environment variables
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
LINKEDIN_ACCESS_TOKEN = os.environ.get('LINKEDIN_ACCESS_TOKEN')
LINKEDIN_OWNER_URN = os.environ.get('LINKEDIN_OWNER_URN')
GOOGLE_DRIVE_FOLDER_ID = os.environ.get('GOOGLE_DRIVE_FOLDER_ID')
GOOGLE_CREDENTIALS_JSON = os.environ.get('GOOGLE_CREDENTIALS_JSON')  # Base64 encoded

# API Key for authentication (used for both login and autopost)
AUTOPOST_API_KEY = os.environ.get('AUTOPOST_API_KEY')  # Single API key for all authentication

# Autopost folder (separate from main folder)
AUTOPOST_FOLDER_ID = os.environ.get('AUTOPOST_FOLDER_ID', '1jqDwMAWKl6EPkoRKmsMPLxrb837NN6MD')

# Skip folder for large files that can't be uploaded to LinkedIn
SKIP_FOLDER_ID = os.environ.get('SKIP_FOLDER_ID', '17Dw6SqWZyiWjvS2A0qLhhVr8rvPknbBQ')

# Maximum file size for LinkedIn upload (in MB) - LinkedIn limit is ~100MB
# Files larger than this will be moved to skip folder
LINKEDIN_MAX_FILE_SIZE_MB = int(os.environ.get('LINKEDIN_MAX_FILE_SIZE_MB', '100'))

# Promo videos - randomly picked and posted alongside the main video
# Load from promo_videos.json (falls back to env var PROMO_VIDEOS_JSON, then default)
def _load_promo_videos():
    import json as _json
    promo_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'promo_videos.json')
    if os.path.exists(promo_file):
        with open(promo_file, 'r') as f:
            return _json.load(f)
    env_json = os.environ.get('PROMO_VIDEOS_JSON', '')
    if env_json:
        return _json.loads(env_json)
    return [{
        'file_id': '1l4ZjLdKqfBCdfYkseTgWMsCxj7AtLGne',
        'caption': 'Save it once. Find it fast. Try it out today   #Productivity #KnowledgeManagement #AI #Founders #MemoryStore.in'
    }]

PROMO_VIDEOS = _load_promo_videos()

def get_random_promo_video():
    """Pick a random promo video from the list, or None if empty."""
    return random.choice(PROMO_VIDEOS) if PROMO_VIDEOS else None

# Promo images - randomly picked from Google Drive and posted alongside videos
PROMO_IMAGES_FOLDER_ID = os.environ.get('PROMO_IMAGES_FOLDER_ID', '1i4gFwBEHkNxDX-fd-so3K3P6uqY_0-8e')
PROMO_IMAGE_CAPTION = os.environ.get('PROMO_IMAGE_CAPTION', 'Try MemoryStore.in')

def get_random_promo_image():
    """Pick a random image from the promo images folder, or None if empty/folder not accessible."""
    try:
        manager = get_drive_manager()
        image = manager.get_random_image_fast(PROMO_IMAGES_FOLDER_ID, sample_size=50)
        return image
    except Exception as e:
        print(f"  ⚠️ Could not fetch promo image: {e}")
        return None

# Top comment posted immediately after each platform post
TOP_COMMENT = os.environ.get('TOP_COMMENT', '')

# Posted videos folder (will be created automatically)
POSTED_FOLDER_NAME = "Posted_Videos"
REJECTED_FOLDER_NAME = "Rejected_Videos"
posted_folder_id = None
rejected_folder_id = None

# Device restriction DISABLED by default
DEVICE_RESTRICTION_ENABLED = os.environ.get('DEVICE_RESTRICTION_ENABLED', 'false').lower() == 'true'

# Initialize Google Drive Manager
drive_manager = None

# Initialize Device Manager
device_manager = DeviceManager()

@app.before_request
def check_device_before_request():
    """
    Global device check before ANY request
    Only allows device-setup, device-blocked, and static routes without device check
    """
    # Skip device check for these routes (they need to be accessible for setup)
    allowed_routes = [
        'device_blocked',
        'device_setup',
        'static',
        'robots',
        'health',
        'autopost',        # API-authenticated route
        'autopost_status'  # API-authenticated route
    ]
    
    # Check if current endpoint is in allowed routes
    if request.endpoint in allowed_routes:
        return None
    
    # Check device restriction
    if DEVICE_RESTRICTION_ENABLED:
        is_allowed, device_info = device_manager.is_device_allowed(request)
        if not is_allowed:
            # Redirect to device blocked page immediately
            return redirect('/device-blocked')
    
    return None

def get_drive_manager():
    """Initialize Drive Manager lazily"""
    global drive_manager
    if drive_manager is None:
        # For Vercel, credentials will be in environment variable
        if GOOGLE_CREDENTIALS_JSON:
            import json
            import base64
            creds_dict = json.loads(base64.b64decode(GOOGLE_CREDENTIALS_JSON))
            # Create temporary file for credentials
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                json.dump(creds_dict, f)
                creds_path = f.name
        else:
            # Local development
            creds_path = 'credentials.json'
        
        drive_manager = GoogleDriveManager(
            credentials_path=creds_path,
            use_service_account=True
        )
    return drive_manager

def require_auth(f):
    """Decorator to require authentication (device check done globally)"""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Device check is already done in before_request
        # Just check authentication here
        if not session.get('authenticated'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

def get_runtime_config_status():
    """Return non-secret runtime configuration status for diagnostics."""
    return {
        'auth_configured': bool(AUTOPOST_API_KEY),
        'gemini_api_configured': bool(GEMINI_API_KEY),
        'linkedin_configured': bool(LINKEDIN_ACCESS_TOKEN and LINKEDIN_OWNER_URN),
        'google_drive_configured': bool(GOOGLE_CREDENTIALS_JSON or os.path.exists('credentials.json')),
        'device_restriction_enabled': DEVICE_RESTRICTION_ENABLED,
        'flask_secret_configured': bool(os.environ.get('FLASK_SECRET_KEY'))
    }

def extract_creator_name(video_filename):
    """
    Extract creator name from video filename.
    Example: 'longliveai_reel_12_07_2025_18_18_193675086533226295792.mp4' -> 'longliveai'
    
    Args:
        video_filename: The video filename
    
    Returns:
        Creator name (text before first underscore) or None if not found
    """
    if not video_filename:
        return None
    
    # Remove extension first
    name_without_ext = video_filename.rsplit('.', 1)[0] if '.' in video_filename else video_filename
    
    # Get the part before the first underscore
    if '_' in name_without_ext:
        creator = name_without_ext.split('_')[0]
        return creator if creator else None
    
    return None

def add_credit_to_description(description, video_filename):
    """
    Add credit line to the end of the description.
    
    Args:
        description: The AI-generated description
        video_filename: The video filename to extract creator from
    
    Returns:
        Description with credit line appended
    """
    creator = extract_creator_name(video_filename)
    
    if creator:
        credit_line = f"\n\nThanks to {creator} for sharing this video 🙏"
        return description.strip() + credit_line
    
    return description

def select_random_video():
    """
    Select a random video from Google Drive FAST
    Only fetches a small sample instead of ALL videos
    """
    import time
    
    # Seed with current timestamp for extra randomness
    random.seed(time.time())
    
    manager = get_drive_manager()
    
    # Use the fast method - only fetches 50 videos instead of all
    print("🚀 Fetching random video (fast method - only 50 samples)...")
    selected_video = manager.get_random_video_fast(GOOGLE_DRIVE_FOLDER_ID, sample_size=50)
    
    if not selected_video:
        return None
    
    print(f"✅ Selected video: {selected_video['name']}")
    
    return selected_video

def get_video_capable_models():
    """
    Dynamically fetch all Gemini models that support video processing.
    Any model with 'generateContent' in supported_actions can be used.
    Returns a list of model names sorted by capabilities.
    """
    try:
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Fetch all available models
        print("  → Querying Gemini API for available models...")
        all_models = list(client.models.list())
        
        print(f"  → API returned {len(all_models)} total models")
        
        video_models = []
        
        for model in all_models:
            try:
                model_name = model.name if hasattr(model, 'name') else str(model)
                display_name = model.display_name if hasattr(model, 'display_name') else model_name
                
                # Check if model supports generateContent
                # It can be in either 'supported_actions' or 'supported_generation_methods'
                supported_actions = []
                if hasattr(model, 'supported_actions'):
                    supported_actions = model.supported_actions
                elif hasattr(model, 'supported_generation_methods'):
                    supported_actions = model.supported_generation_methods
                
                if 'generateContent' not in supported_actions:
                    continue  # Skip models that don't support generateContent
                
                # All models with generateContent can be used for video description
                is_gemini_2 = 'gemini-2' in model_name.lower() or 'gemini2' in model_name.lower()
                
                video_models.append({
                    'name': model_name,
                    'display_name': display_name,
                    'description': model.description if hasattr(model, 'description') else 'N/A',
                    'input_token_limit': model.input_token_limit if hasattr(model, 'input_token_limit') else 0,
                    'output_token_limit': model.output_token_limit if hasattr(model, 'output_token_limit') else 0,
                    'supported_actions': supported_actions,
                    'is_gemini_2': is_gemini_2
                })
                print(f"    ✓ {display_name}: {model_name}")
            except Exception as e:
                print(f"    ⚠️ Error processing model: {e}")
                continue
        
        # If we found models from API, use them
        if video_models:
            # Sort: Gemini 2.x first, then by token limit (higher is better)
            video_models.sort(key=lambda x: (x.get('is_gemini_2', False), x['input_token_limit']), reverse=True)
            
            print(f"  ✅ Found {len(video_models)} video-capable models from API")
            return video_models
        else:
            # No models found, this shouldn't happen but just in case
            print(f"  ⚠️ No video-capable models found from API")
            print(f"  ⚠️ This likely means the API key is invalid or API is down")
            raise Exception("No models found - API may be unavailable")
    
    except Exception as e:
        print(f"  ❌ CRITICAL: Could not fetch models from API: {str(e)[:200]}")
        print(f"  ❌ Please check your GEMINI_API_KEY and internet connection")
        raise  # Don't use fallback - force the error to be visible

def select_best_video_model(preferred_model=None):
    """
    Select the best available model for video processing.
    
    Args:
        preferred_model: Optional specific model name to use
        
    Returns:
        Model name string to use with Gemini API
    """
    if preferred_model:
        return preferred_model
    
    # Get all video-capable models
    video_models = get_video_capable_models()
    
    if not video_models:
        # Ultimate fallback
        return "gemini-2.0-flash-exp"
    
    # Priority order: experimental > flash > pro
    # Experimental models often have latest features
    for model in video_models:
        if 'exp' in model['name'].lower() and 'flash' in model['name'].lower():
            print(f"🎯 Selected model: {model['display_name']}")
            return model['name']
    
    # Next preference: flash models (faster)
    for model in video_models:
        if 'flash' in model['name'].lower():
            print(f"🎯 Selected model: {model['display_name']}")
            return model['name']
    
    # Fallback to first available
    print(f"🎯 Selected model: {video_models[0]['display_name']}")
    return video_models[0]['name']

def is_quota_error(error):
    """Check if error is a quota/rate limit error (429)"""
    error_str = str(error).lower()
    if 'quota' in error_str or 'resource_exhausted' in error_str or '429' in error_str:
        return True
    # Check if it's a dict with error code
    if isinstance(error, dict) and 'error' in error:
        return error.get('error', {}).get('code') == 429
    return False

def generate_video_description_with_model(video_file_id, myfile, client, model_name):
    """Generate description using a specific model"""
    # LinkedIn Algorithm-Optimized Prompt (2024 best practices)
    # IMPORTANT: LinkedIn does NOT support markdown - no bold, italic, bullets
    prompt = """Analyze this video and create a VIRAL LinkedIn post. Follow this EXACT structure:
the first 2 lines readers see before they have to click "… more" on LinkedIn (roughly 2 short sentences of ~55 characters max each).

The hook's only job is to break the reader's scrolling pattern and make them NEED to click "… more." It should feel like a pattern interrupt — something unexpected, counterintuitive, or so specific the reader thinks "wait, what?"

<rules>
- The hook must be about the READER or a universal tension — never about me.
- It should create an open loop: an unanswered question, a contradiction, or a bold claim the reader can't ignore.
- Avoid anything that sounds like a personal achievement, no emoji openers, no hashtags.
- It should feel like something a friend would text you that makes you reply "wait, explain."
</rules>

<hook_techniques>
1. Contradiction — say something that sounds wrong ("The worst LinkedIn posts get the most followers.")
2. Specific number + unexpected context ("I mass-unfollowed 2,000 people. My engagement tripled.")
3. Direct accusation — call the reader out ("You're writing LinkedIn posts for your mom, not your audience.")
4. Stolen thought — say what the reader secretly thinks but won't say out loud ("You know your LinkedIn posts are boring. So does everyone scrolling past them.")
5. Absurd reframe — take something mundane and make it dramatic ("Your LinkedIn hook has 1.2 seconds to live. Most die instantly.")
</hook_techniques>

LINE 6: End with a thought-provoking QUESTION that invites comments.

[blank line]

LINE 7: Add exactly 4-5 relevant hashtags. Mix popular ones with niche ones. Format: #HashTag

CRITICAL RULES:
- DO NOT use asterisks, bold, or any markdown formatting (LinkedIn doesn't support it)
- DO NOT use bullet points or dashes
- Keep total length under 200 words
- Use simple line breaks between sections
- Sound like a thought leader, not a marketer


Write the post directly as PLAIN TEXT. No asterisks, no formatting symbols."""
    
    try:
        print(f"  → Attempting with model: {model_name}")
        response = client.models.generate_content(
            model=model_name,
            contents=[myfile, prompt]
        )
        print(response.text)
        result_text = response.text
        if not result_text or not result_text.strip():
            raise Exception(f"Empty response from {model_name}")
        return result_text
    except Exception as e:
        if is_quota_error(e):
            print(f"  ⚠️ Quota exceeded for {model_name}")
            raise
        else:
            print(f"  ❌ Error with {model_name}: {str(e)[:100]}")
            raise

def generate_video_description(video_file_id, local_video_path=None):
    """
    Generate engaging description using Gemini AI with automatic model fallback.
    If a model hits quota limits, automatically tries the next available model.
    """
    manager = get_drive_manager()
    client = genai.Client(api_key=GEMINI_API_KEY)
    
    # Reuse an existing local file when one is already available so we do not
    # duplicate the same video in /tmp during background processing.
    temp_path = local_video_path or f"/tmp/{video_file_id}.mp4"
    should_cleanup = local_video_path is None
    
    try:
        if local_video_path:
            print("  → Reusing downloaded video for AI analysis...")
        else:
            print("  → Downloading video for AI analysis...")
            manager.download_video(video_file_id, temp_path)
        
        # Upload to Gemini - use exact syntax from working code
        print("  → Uploading to Gemini AI...")
        myfile = client.files.upload(file=str(temp_path))
        
        # Wait for processing
        print("  → Waiting for Gemini to process...")
        while True:
            file_status = client.files.get(name=myfile.name)
            if file_status.state == "ACTIVE":
                break
            elif file_status.state == "FAILED":
                raise Exception("File upload to Gemini failed")
            time.sleep(2)
        
        # Get all available video models
        print("  → Fetching available models...")
        video_models = get_video_capable_models()
        
        # Note: get_video_capable_models() now always returns fallback models if needed
        print(f"  → Will try {len(video_models)} model(s)")
        
        # Try each model until we get a successful response
        last_error = None
        for i, model_info in enumerate(video_models):
            model_name = model_info['name']
            
            try:
                description = generate_video_description_with_model(
                    video_file_id, myfile, client, model_name
                )
                print(f"  ✅ Successfully generated description with {model_name}")
                return description
                
            except Exception as e:
                last_error = e
                if is_quota_error(e):
                    print(f"  → Model {i+1}/{len(video_models)} exhausted, trying next...")
                    continue  # Try next model
                else:
                    # Non-quota error, might be worth trying other models
                    print(f"  → Error with model {i+1}/{len(video_models)}, trying next...")
                    continue
        
        # All models failed
        error_msg = f"All {len(video_models)} models failed. Last error: {str(last_error)}"
        print(f"  ❌ {error_msg}")
        raise Exception(error_msg)
        
    finally:
        # Cleanup only when this function created the temp file.
        if should_cleanup and os.path.exists(temp_path):
            try:
                os.unlink(temp_path)
                print("  → Cleaned up temp file")
            except:
                pass

def post_to_linkedin(video_file_id, description):
    """Upload video and create LinkedIn post - optimized for Vercel"""
    manager = get_drive_manager()

    # Use /tmp for Vercel serverless
    temp_path = f"/tmp/{video_file_id}_linkedin.mp4"

    try:
        # Download video for LinkedIn upload
        print("  → Downloading video for LinkedIn...")
        manager.download_video(video_file_id, temp_path)

        # Use the new function with local file
        return post_to_linkedin_with_local_file(temp_path, description)

    finally:
        # Cleanup
        if os.path.exists(temp_path):
            os.unlink(temp_path)

def post_to_linkedin_with_local_file(video_path, description):
    """
    Upload video and create LinkedIn post using local file path.
    If file is too large, uploads to Google Drive skip folder instead.

    Returns:
        dict: {
            'success': bool,
            'platform': str ('linkedin' or 'skipped'),
            'post_urn': str or None,
            'drive_link': str or None,
            'message': str
        }
    """
    try:
        file_size = os.path.getsize(video_path) / (1024 * 1024)
        print(f"  → File size: {file_size:.2f} MB")

        # Check if file is too large for LinkedIn
        if file_size > LINKEDIN_MAX_FILE_SIZE_MB:
            print(f"  ⚠ File too large for LinkedIn ({file_size:.2f} MB > {LINKEDIN_MAX_FILE_SIZE_MB} MB limit)")
            print(f"  → Uploading to Google Drive skip folder instead...")
            return upload_to_skip_folder(video_path, description, file_size)

        # Warn about large files (but still attempt upload)
        if file_size > 10:
            print(f"  ⚠ Warning: Large file ({file_size:.2f} MB) - upload may take longer")

        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Step 1: Register upload
        print("  → Registering upload with LinkedIn...")
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        register_payload = {
            "registerUploadRequest": {
                "owner": LINKEDIN_OWNER_URN,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-video"],
                "serviceRelationships": [{
                    "identifier": "urn:li:userGeneratedContent",
                    "relationshipType": "OWNER"
                }],
                "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"]
            }
        }

        register_response = requests.post(register_url, headers=headers, json=register_payload, timeout=30)
        register_response.raise_for_status()
        register_data = register_response.json()

        upload_url = register_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset = register_data["value"]["asset"]

        # Step 2: Upload video with retry logic
        print("  → Uploading video to LinkedIn...")
        max_retries = 3
        retry_delay = 5

        for attempt in range(max_retries):
            try:
                with open(video_path, "rb") as video_file:
                    # Longer timeout for larger files: 5 minutes
                    upload_response = requests.put(
                        upload_url,
                        headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
                        data=video_file,
                        timeout=300
                    )
                upload_response.raise_for_status()
                print("  ✓ Video uploaded successfully!")
                break
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    print(f"  ⚠ Upload timeout, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2  # Exponential backoff
                else:
                    raise
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1 and "504" in str(e):
                    print(f"  ⚠ Gateway timeout, retrying in {retry_delay}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    raise

        # Wait for LinkedIn to process
        time.sleep(3)

        # Step 3: Create post
        print("  → Creating LinkedIn post...")
        post_url = "https://api.linkedin.com/v2/ugcPosts"
        post_payload = {
            "author": LINKEDIN_OWNER_URN,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": description},
                    "shareMediaCategory": "VIDEO",
                    "media": [{"status": "READY", "media": asset}]
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
        }

        post_response = requests.post(post_url, headers=headers, json=post_payload, timeout=30)
        post_response.raise_for_status()

        # Extract the URN of the created post (returned in response body or header)
        post_urn = None
        try:
            post_urn = post_response.json().get('id')
        except Exception:
            pass
        if not post_urn:
            post_urn = post_response.headers.get('X-RestLi-Id')

        print("  ✓ Posted to LinkedIn!")
        return {
            'success': True,
            'platform': 'linkedin',
            'post_urn': post_urn,
            'drive_link': None,
            'message': 'Successfully posted to LinkedIn'
        }

    except Exception as e:
        error_str = str(e)
        print(f"  ✗ LinkedIn posting failed: {error_str}")

        # Check if it's a memory/runtime error (Vercel specific)
        if 'memory' in error_str.lower() or 'killed' in error_str.lower() or 'runtime' in error_str.lower():
            print(f"  ⚠ Detected memory/runtime error - uploading to skip folder instead...")
            try:
                file_size = os.path.getsize(video_path) / (1024 * 1024)
                return upload_to_skip_folder(video_path, description, file_size)
            except Exception as fallback_error:
                print(f"  ✗ Fallback to skip folder also failed: {str(fallback_error)}")

        return {
            'success': False,
            'platform': None,
            'post_urn': None,
            'drive_link': None,
            'message': f'LinkedIn upload failed: {error_str}'
        }


def upload_to_skip_folder(video_path, description, file_size=None):
    """
    Upload large video to Google Drive skip folder.

    Args:
        video_path: Path to video file
        description: Video description (used for filename)
        file_size: File size in MB (optional, will calculate if not provided)

    Returns:
        dict: {
            'success': bool,
            'platform': 'skipped',
            'post_urn': None,
            'drive_link': str,
            'message': str
        }
    """
    try:
        if file_size is None:
            file_size = os.path.getsize(video_path) / (1024 * 1024)

        manager = get_drive_manager()

        # Generate filename with timestamp
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        original_name = os.path.basename(video_path)
        # Create filename: skipped_YYYYMMDD_HHMMSS_originalname
        skip_filename = f"skipped_{timestamp}_{original_name}"

        print(f"  → Uploading to Google Drive skip folder: {skip_filename}")
        print(f"  → File size: {file_size:.2f} MB")

        # Upload to skip folder
        uploaded_file = manager.upload_video(
            file_path=video_path,
            folder_id=SKIP_FOLDER_ID,
            filename=skip_filename
        )

        drive_link = uploaded_file.get('webViewLink', 'N/A')

        print(f"  ✓ Uploaded to Google Drive skip folder!")
        print(f"  → Drive link: {drive_link}")

        return {
            'success': True,
            'platform': 'skipped',
            'post_urn': None,
            'drive_link': drive_link,
            'message': f'File too large for LinkedIn. Uploaded to Google Drive skip folder: {drive_link}'
        }

    except Exception as e:
        print(f"  ✗ Upload to skip folder failed: {str(e)}")
        return {
            'success': False,
            'platform': None,
            'post_urn': None,
            'drive_link': None,
            'message': f'Skip folder upload failed: {str(e)}'
        }


def post_to_linkedin_image(image_path, caption):
    """
    Upload an image and create a LinkedIn image post.

    Args:
        image_path: Local path to the image file
        caption: Text caption for the image post

    Returns:
        dict: {
            'success': bool,
            'post_urn': str or None,
            'message': str
        }
    """
    try:
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }

        # Step 1: Register image upload
        print("  → Registering image upload with LinkedIn...")
        register_url = "https://api.linkedin.com/v2/assets?action=registerUpload"
        register_payload = {
            "registerUploadRequest": {
                "owner": LINKEDIN_OWNER_URN,
                "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                "serviceRelationships": [{
                    "identifier": "urn:li:userGeneratedContent",
                    "relationshipType": "OWNER"
                }],
                "supportedUploadMechanism": ["SYNCHRONOUS_UPLOAD"]
            }
        }

        register_response = requests.post(register_url, headers=headers, json=register_payload, timeout=30)
        register_response.raise_for_status()
        register_data = register_response.json()

        upload_url = register_data["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
        asset = register_data["value"]["asset"]

        # Step 2: Upload image
        print("  → Uploading image to LinkedIn...")
        with open(image_path, "rb") as image_file:
            upload_response = requests.put(
                upload_url,
                headers={"Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}"},
                data=image_file,
                timeout=120
            )
        upload_response.raise_for_status()
        print("  ✓ Image uploaded successfully!")

        time.sleep(2)

        # Step 3: Create image post
        print("  → Creating LinkedIn image post...")
        post_url = "https://api.linkedin.com/v2/ugcPosts"
        post_payload = {
            "author": LINKEDIN_OWNER_URN,
            "lifecycleState": "PUBLISHED",
            "specificContent": {
                "com.linkedin.ugc.ShareContent": {
                    "shareCommentary": {"text": caption},
                    "shareMediaCategory": "IMAGE",
                    "media": [{"status": "READY", "media": asset}]
                }
            },
            "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
        }

        post_response = requests.post(post_url, headers=headers, json=post_payload, timeout=30)
        post_response.raise_for_status()

        post_urn = None
        try:
            post_urn = post_response.json().get('id')
        except Exception:
            pass
        if not post_urn:
            post_urn = post_response.headers.get('X-RestLi-Id')

        print("  ✓ Posted image to LinkedIn!")
        return {
            'success': True,
            'post_urn': post_urn,
            'message': 'Successfully posted image to LinkedIn'
        }

    except Exception as e:
        error_str = str(e)
        print(f"  ✗ LinkedIn image posting failed: {error_str}")
        return {
            'success': False,
            'post_urn': None,
            'message': f'LinkedIn image posting failed: {error_str}'
        }


def add_linkedin_comment(post_urn: str, comment_text: str) -> bool:
    """
    Post a top comment on a published LinkedIn UGC post.

    Args:
        post_urn: The URN of the published post (e.g. urn:li:ugcPost:123...)
        comment_text: Text of the comment to post

    Returns:
        True on success, False otherwise
    """
    try:
        headers = {
            "Authorization": f"Bearer {LINKEDIN_ACCESS_TOKEN}",
            "Content-Type": "application/json"
        }
        url = f"https://api.linkedin.com/v2/socialActions/{requests.utils.quote(post_urn, safe='')}/comments"
        payload = {
            "actor": LINKEDIN_OWNER_URN,
            "message": {"text": comment_text}
        }
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        if response.status_code in (200, 201):
            print(f"  ✓ LinkedIn top comment posted")
            return True
        print(f"  ⚠ LinkedIn comment failed ({response.status_code}): {response.text[:200]}")
    except Exception as e:
        print(f"  ⚠ LinkedIn comment error: {e}")
    return False

# HTML Templates
LOGIN_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <meta name="googlebot" content="noindex, nofollow">
    <title>Login - LinkedIn Video Automation</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: white;
            border-radius: 20px;
            padding: 50px 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 400px;
            width: 100%;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
            text-align: center;
        }
        .subtitle {
            color: #666;
            text-align: center;
            margin-bottom: 30px;
            font-size: 0.9em;
        }
        .form-group {
            margin-bottom: 20px;
        }
        label {
            display: block;
            color: #555;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 0.9em;
        }
        input {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .btn {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1.1em;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            margin-top: 10px;
        }
        .btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 10px 25px rgba(102, 126, 234, 0.4);
        }
        .btn:active {
            transform: translateY(0);
        }
        .error {
            background: #fee;
            color: #c33;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.9em;
            text-align: center;
        }
        .lock-icon {
            text-align: center;
            font-size: 3em;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="lock-icon">🔑</div>
        <h1>Welcome</h1>
        <p class="subtitle">LinkedIn Video Automation</p>
        
        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}
        
        <form method="POST" action="/login">
            <div class="form-group">
                <label for="api_key">API Key</label>
                <input type="password" id="api_key" name="api_key" placeholder="Enter your API key" required autofocus>
            </div>
            
            <button type="submit" class="btn">Login</button>
        </form>
    </div>
</body>
</html>
"""

DEVICE_BLOCKED_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Device Not Authorized</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 50px 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
            text-align: center;
        }
        .icon {
            font-size: 80px;
            margin-bottom: 20px;
        }
        h1 {
            color: #f5576c;
            margin-bottom: 20px;
            font-size: 2em;
        }
        p {
            color: #666;
            margin-bottom: 15px;
            line-height: 1.6;
        }
        .device-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            text-align: left;
        }
        .device-info h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1em;
        }
        .device-info p {
            margin: 8px 0;
            font-size: 0.9em;
            color: #555;
        }
        .fingerprint {
            font-family: monospace;
            background: #e9ecef;
            padding: 8px;
            border-radius: 5px;
            word-break: break-all;
        }
        .btn {
            display: inline-block;
            margin-top: 20px;
            padding: 12px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">🚫</div>
        <h1>Device Not Authorized</h1>
        <p>This device is not whitelisted to access this application.</p>
        <p>Only authorized devices (owner's Mac and mobile) can access this app.</p>
        
        <div class="device-info">
            <h3>Your Device Information:</h3>
            <p><strong>Device Type:</strong> {{ device_info.device_type }}</p>
            <p><strong>Browser:</strong> {{ device_info.browser }}</p>
            <p><strong>Device Fingerprint:</strong></p>
            <p class="fingerprint">{{ fingerprint }}</p>
        </div>
        
        <p style="margin-top: 20px;"><strong>If this is your device:</strong></p>
        <p>Visit the device setup page and add this device to the whitelist.</p>
        
        <a href="/device-setup" class="btn">Device Setup</a>
    </div>
</body>
</html>
"""

DEVICE_SETUP_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="robots" content="noindex, nofollow">
    <title>Device Management</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        .container {
            max-width: 1000px;
            margin: 0 auto;
        }
        .card {
            background: white;
            border-radius: 20px;
            padding: 30px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            margin-bottom: 20px;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
        }
        h2 {
            color: #555;
            margin-bottom: 15px;
            font-size: 1.3em;
            border-bottom: 2px solid #667eea;
            padding-bottom: 10px;
        }
        .subtitle {
            color: #666;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        .form-group {
            margin-bottom: 15px;
        }
        label {
            display: block;
            color: #555;
            font-weight: 600;
            margin-bottom: 8px;
            font-size: 0.9em;
        }
        input[type="text"],
        input[type="password"] {
            width: 100%;
            padding: 12px 15px;
            border: 2px solid #e0e0e0;
            border-radius: 10px;
            font-size: 1em;
            transition: all 0.3s ease;
        }
        input:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .btn {
            padding: 12px 25px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 10px;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover {
            transform: translateY(-2px);
        }
        .btn-danger {
            background: linear-gradient(135deg, #f5576c 0%, #f093fb 100%);
            padding: 8px 15px;
            font-size: 0.85em;
        }
        .alert {
            padding: 15px 20px;
            border-radius: 10px;
            margin-bottom: 20px;
            font-weight: 500;
        }
        .alert-success {
            background: #d4edda;
            color: #155724;
            border: 1px solid #c3e6cb;
        }
        .alert-error {
            background: #f8d7da;
            color: #721c24;
            border: 1px solid #f5c6cb;
        }
        .current-device {
            background: #e7f3ff;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
            border-left: 4px solid #667eea;
        }
        .current-device p {
            margin: 5px 0;
            color: #555;
        }
        .device-list {
            margin-top: 20px;
        }
        .device-item {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 15px;
            border-left: 4px solid #667eea;
        }
        .device-item h3 {
            color: #333;
            margin-bottom: 10px;
            font-size: 1.1em;
        }
        .device-item p {
            margin: 5px 0;
            color: #666;
            font-size: 0.9em;
        }
        .device-item .fingerprint {
            font-family: monospace;
            background: #e9ecef;
            padding: 5px 8px;
            border-radius: 5px;
            font-size: 0.85em;
            word-break: break-all;
        }
        .device-actions {
            margin-top: 15px;
        }
        .back-link {
            display: inline-block;
            margin-top: 20px;
            color: white;
            text-decoration: none;
            font-weight: 600;
        }
        .back-link:hover {
            text-decoration: underline;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="card">
            <h1>🔒 Device Management</h1>
            <p class="subtitle">Manage whitelisted devices for this application</p>
            
            {% if message %}
            <div class="alert alert-success">{{ message }}</div>
            {% endif %}
            
            {% if error %}
            <div class="alert alert-error">{{ error }}</div>
            {% endif %}
            
            {% if current_device %}
            <div class="current-device">
                <h3>📱 Current Device</h3>
                <p><strong>Type:</strong> {{ current_info.device_type }}</p>
                <p><strong>Browser:</strong> {{ current_info.browser }}</p>
                <p><strong>Fingerprint:</strong> <span class="fingerprint">{{ current_device.fingerprint }}</span></p>
            </div>
            {% endif %}
            
            <h2>Add Current Device</h2>
            <form method="POST">
                <input type="hidden" name="action" value="add">
                <div class="form-group">
                    <label for="device_name">Device Name (optional):</label>
                    <input type="text" id="device_name" name="device_name" 
                           placeholder="e.g., My MacBook Pro, My iPhone 13">
                </div>
                <div class="form-group">
                    <label for="password">API Key:</label>
                    <input type="password" id="password" name="password" placeholder="Enter your API key" required>
                </div>
                <button type="submit" class="btn">Add This Device</button>
            </form>
        </div>
        
        <div class="card">
            <h2>Whitelisted Devices ({{ devices|length }})</h2>
            
            {% if devices %}
            <div class="device-list">
                {% for device in devices %}
                <div class="device-item">
                    <h3>{{ device.name }}</h3>
                    <p><strong>Type:</strong> {{ device.device_type }}</p>
                    <p><strong>Browser:</strong> {{ device.browser }}</p>
                    <p><strong>Added:</strong> {{ device.added_at }}</p>
                    <p><strong>Last Seen:</strong> {{ device.last_seen }}</p>
                    <p><strong>Last IP:</strong> {{ device.last_ip }}</p>
                    <p><strong>Fingerprint:</strong> <span class="fingerprint">{{ device.fingerprint }}</span></p>
                    
                    <div class="device-actions">
                        <form method="POST" style="display: inline;" 
                              onsubmit="return confirm('Remove this device?');">
                            <input type="hidden" name="action" value="remove">
                            <input type="hidden" name="fingerprint" value="{{ device.fingerprint }}">
                            <input type="password" name="password" placeholder="API key" required
                                   style="width: 200px; display: inline-block; margin-right: 10px;">
                            <button type="submit" class="btn btn-danger">Remove Device</button>
                        </form>
                    </div>
                </div>
                {% endfor %}
            </div>
            {% else %}
            <p style="color: #999; text-align: center; padding: 40px;">
                No devices whitelisted yet. Add your devices above.
            </p>
            {% endif %}
        </div>
        
        <a href="/" class="back-link">← Back to Home</a>
    </div>
</body>
</html>
"""

AUTOPOST_RESULT_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <title>Autopost Result - LinkedIn Automation</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, {% if success %}#667eea 0%, #764ba2{% else %}#f5576c 0%, #f093fb{% endif %} 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 700px;
            width: 100%;
            text-align: center;
        }
        .icon { font-size: 80px; margin-bottom: 20px; }
        h1 { color: {% if success %}#28a745{% else %}#dc3545{% endif %}; margin-bottom: 15px; font-size: 2em; }
        .message { color: #666; font-size: 1.1em; margin-bottom: 25px; }
        .video-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            margin: 20px 0;
            text-align: left;
        }
        .video-info h3 { color: #333; margin-bottom: 15px; font-size: 1.1em; }
        .video-info p { margin: 10px 0; color: #555; line-height: 1.6; }
        .video-info .label { font-weight: 600; color: #333; }
        .description-box {
            background: #e9ecef;
            padding: 15px;
            border-radius: 8px;
            margin-top: 15px;
            text-align: left;
            font-size: 0.95em;
            line-height: 1.6;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        .error-box {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
            text-align: left;
        }
        .btn {
            display: inline-block;
            padding: 14px 30px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            margin: 10px;
            transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .btn-success { background: linear-gradient(135deg, #28a745 0%, #20c997 100%); }
        .creator-tag {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-bottom: 15px;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">{% if success %}🎉{% else %}❌{% endif %}</div>
        <h1>{% if success %}Posted Successfully!{% else %}Posting Failed{% endif %}</h1>
        <p class="message">{{ message }}</p>
        
        {% if creator %}
        <span class="creator-tag">@{{ creator }}</span>
        {% endif %}
        
        <div class="video-info">
            <h3>📹 Video Details</h3>
            <p><span class="label">Filename:</span> {{ video_name }}</p>
            <p><span class="label">Video ID:</span> {{ video_id }}</p>
            
            {% if description %}
            <p><span class="label">Posted Description:</span></p>
            <div class="description-box">{{ description }}</div>
            {% endif %}
            
            {% if error %}
            <div class="error-box">
                <strong>Error:</strong> {{ error }}
            </div>
            {% endif %}
        </div>
        
        <div>
            <a href="/autopost?api_key={{ request.args.get('api_key', '') }}&sync=true" class="btn btn-success">📤 Post Another</a>
            <a href="/autopost/status?api_key={{ request.args.get('api_key', '') }}" class="btn">📊 Check Status</a>
        </div>
    </div>
</body>
</html>
"""

AUTOPOST_PROCESSING_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <title>Processing - LinkedIn Automation</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 700px;
            width: 100%;
            text-align: center;
        }
        .spinner {
            border: 4px solid #f3f3f3;
            border-top: 4px solid #667eea;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            animation: spin 1s linear infinite;
            margin: 0 auto 25px;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        h1 { color: #333; margin-bottom: 15px; font-size: 1.8em; }
        .message { color: #666; font-size: 1.1em; margin-bottom: 25px; }
        .video-info {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            margin: 20px 0;
            text-align: left;
        }
        .video-info p { margin: 8px 0; color: #555; }
        .video-info .label { font-weight: 600; color: #333; }
        .creator-tag {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 5px 15px;
            border-radius: 20px;
            font-size: 0.9em;
            margin-bottom: 15px;
        }
        #logs {
            background: #1e1e1e;
            color: #0f0;
            padding: 20px;
            border-radius: 10px;
            text-align: left;
            font-family: monospace;
            font-size: 13px;
            max-height: 300px;
            overflow-y: auto;
            margin-top: 20px;
        }
        #logs .log-line { margin: 5px 0; }
        .done { color: #28a745; font-weight: bold; }
        .error { color: #dc3545; }
    </style>
</head>
<body>
    <div class="container">
        <div class="spinner" id="spinner"></div>
        <h1 id="title">🚀 Processing Video...</h1>
        <p class="message" id="status">Generating AI description and uploading to LinkedIn</p>
        
        {% if creator %}
        <span class="creator-tag">@{{ creator }}</span>
        {% endif %}
        
        <div class="video-info">
            <p><span class="label">Filename:</span> {{ video_name }}</p>
            <p><span class="label">Video ID:</span> {{ video_id }}</p>
        </div>
        
        <div id="logs"></div>
    </div>
    
    <script>
        const logsDiv = document.getElementById('logs');
        const spinner = document.getElementById('spinner');
        const title = document.getElementById('title');
        const status = document.getElementById('status');
        
        // Connect to log stream
        const eventSource = new EventSource('/logs/{{ video_id }}');
        
        eventSource.onmessage = function(event) {
            const message = event.data;
            
            if (message === 'DONE') {
                eventSource.close();
                spinner.style.display = 'none';
                title.textContent = '✅ Processing Complete!';
                status.textContent = 'Video has been posted to LinkedIn';
                
                // Add completion message
                const doneMsg = document.createElement('div');
                doneMsg.className = 'log-line done';
                doneMsg.textContent = '✅ All done!';
                logsDiv.appendChild(doneMsg);
            } else if (message === '...') {
                // Keep-alive, ignore
            } else {
                const logLine = document.createElement('div');
                logLine.className = 'log-line';
                if (message.includes('❌')) logLine.className += ' error';
                if (message.includes('✅')) logLine.className += ' done';
                logLine.textContent = message;
                logsDiv.appendChild(logLine);
                logsDiv.scrollTop = logsDiv.scrollHeight;
            }
        };
        
        eventSource.onerror = function() {
            eventSource.close();
        };
    </script>
</body>
</html>
"""

AUTOPOST_STATUS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <title>Autopost Status - LinkedIn Automation</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 600px;
            width: 100%;
            text-align: center;
        }
        .icon { font-size: 60px; margin-bottom: 20px; }
        h1 { color: #333; margin-bottom: 20px; font-size: 1.8em; }
        .stats {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
            margin: 25px 0;
        }
        .stat-card {
            background: #f8f9fa;
            padding: 25px;
            border-radius: 12px;
            text-align: center;
        }
        .stat-card.full { grid-column: 1 / -1; }
        .stat-number { font-size: 2.5em; font-weight: bold; color: #667eea; }
        .stat-label { color: #666; font-size: 0.9em; margin-top: 5px; }
        .config-list {
            background: #f8f9fa;
            padding: 20px;
            border-radius: 12px;
            text-align: left;
            margin: 20px 0;
        }
        .config-item {
            display: flex;
            justify-content: space-between;
            padding: 10px 0;
            border-bottom: 1px solid #e9ecef;
        }
        .config-item:last-child { border-bottom: none; }
        .config-item .label { color: #333; font-weight: 500; }
        .config-item .status { font-weight: 600; }
        .config-item .status.ok { color: #28a745; }
        .config-item .status.error { color: #dc3545; }
        .btn {
            display: inline-block;
            padding: 14px 30px;
            background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
            color: white;
            text-decoration: none;
            border-radius: 10px;
            font-weight: 600;
            margin: 10px;
            transition: transform 0.2s;
        }
        .btn:hover { transform: translateY(-2px); }
        .error-box {
            background: #f8d7da;
            color: #721c24;
            padding: 15px;
            border-radius: 8px;
            margin: 20px 0;
        }
        .folder-id {
            font-family: monospace;
            background: #e9ecef;
            padding: 5px 10px;
            border-radius: 5px;
            font-size: 0.85em;
            word-break: break-all;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="icon">📊</div>
        <h1>Autopost Status</h1>
        
        {% if error %}
        <div class="error-box">
            <strong>Error:</strong> {{ error }}
        </div>
        {% endif %}
        
        {% if success %}
        <div class="stats">
            <div class="stat-card full">
                <div class="stat-number">{{ videos_available }}</div>
                <div class="stat-label">Videos Available</div>
            </div>
        </div>
        
        <div class="config-list">
            <div class="config-item">
                <span class="label">📁 Folder ID</span>
                <span class="folder-id">{{ folder_id }}</span>
            </div>
            <div class="config-item">
                <span class="label">🤖 Gemini AI</span>
                <span class="status {% if config.gemini_api_configured %}ok{% else %}error{% endif %}">
                    {% if config.gemini_api_configured %}✅ Configured{% else %}❌ Not Set{% endif %}
                </span>
            </div>
            <div class="config-item">
                <span class="label">💼 LinkedIn</span>
                <span class="status {% if config.linkedin_configured %}ok{% else %}error{% endif %}">
                    {% if config.linkedin_configured %}✅ Configured{% else %}❌ Not Set{% endif %}
                </span>
            </div>
            <div class="config-item">
                <span class="label">📂 Google Drive</span>
                <span class="status {% if config.google_drive_configured %}ok{% else %}error{% endif %}">
                    {% if config.google_drive_configured %}✅ Configured{% else %}❌ Not Set{% endif %}
                </span>
            </div>
        </div>
        {% endif %}
        
        <div>
            <a href="/autopost?api_key={{ request.args.get('api_key', '') }}&sync=true" class="btn">🚀 Post Now</a>
        </div>
    </div>
</body>
</html>
"""

HOME_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="robots" content="noindex, nofollow">
    <meta name="googlebot" content="noindex, nofollow">
    <title>Video Preview - LinkedIn Automation</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Arial, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .container {
            background: white;
            border-radius: 20px;
            padding: 40px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            max-width: 900px;
            width: 100%;
            text-align: center;
        }
        h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 2em;
        }
        .filename {
            color: #666;
            font-size: 16px;
            margin-bottom: 30px;
            font-weight: 600;
            word-break: break-all;
        }
        .category {
            display: inline-block;
            background: #667eea;
            color: white;
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            margin-bottom: 20px;
        }
        .video-preview {
            margin: 20px 0;
            border-radius: 12px;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0,0,0,0.15);
            background: #000;
        }
        .video-preview video {
            width: 100%;
            max-height: 500px;
            display: block;
            object-fit: contain;
        }
        /* Prevent fullscreen on mobile */
        video::-webkit-media-controls-fullscreen-button {
            display: none;
        }
        video {
            -webkit-playsinline: true;
            playsinline: true;
        }
        .buttons {
            margin-top: 30px;
            display: flex;
            gap: 20px;
            justify-content: center;
            flex-wrap: wrap;
        }
        button {
            padding: 16px 48px;
            font-size: 18px;
            font-weight: 600;
            border: none;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 4px 15px rgba(0,0,0,0.2);
            min-width: 180px;
        }
        .accept {
            background: #28a745;
            color: white;
        }
        .accept:hover {
            background: #218838;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(40,167,69,0.4);
        }
        .reject {
            background: #dc3545;
            color: white;
        }
        .reject:hover {
            background: #c82333;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(220,53,69,0.4);
        }
        .info {
            color: #666;
            margin-top: 25px;
            font-size: 14px;
            line-height: 1.6;
        }
        .loading {
            display: none;
            margin-top: 20px;
            color: #667eea;
            font-weight: 600;
        }
        .spinner {
            border: 3px solid #f3f3f3;
            border-top: 3px solid #667eea;
            border-radius: 50%;
            width: 40px;
            height: 40px;
            animation: spin 1s linear infinite;
            margin: 20px auto;
        }
        @keyframes spin {
            0% { transform: rotate(0deg); }
            100% { transform: rotate(360deg); }
        }
        button:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }
        @media (max-width: 600px) {
            .container {
                padding: 24px;
            }
            h1 {
                font-size: 1.5em;
            }
            button {
                padding: 14px 32px;
                font-size: 16px;
                min-width: 150px;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 Video Preview</h1>
        <div class="category">{{ category }}</div>
        <div class="filename">{{ filename }}</div>
        
        <div class="video-preview">
            <div id="videoLoading" style="padding: 60px; color: #667eea;">
                <div class="spinner"></div>
                <p style="margin-top: 20px; font-size: 18px; font-weight: 600;">Loading video from Google Drive...</p>
                <p style="margin-top: 10px; font-size: 14px; color: #999;">This may take a few moments</p>
            </div>
            <video controls playsinline webkit-playsinline id="videoPlayer" style="display: none;">
                <source src="/video/{{ video_id }}" type="video/mp4">
                Your browser does not support video playback.
            </video>
        </div>
        
        <div class="buttons">
            <button class="accept" onclick="handleAction('accept')">
                ✓ Accept & Post to LinkedIn
            </button>
            <button class="reject" onclick="handleAction('reject')">
                ✗ Reject & Delete
            </button>
        </div>
        
        <div class="info">
            <strong>Accept:</strong> Starts background processing (generates AI description → posts to LinkedIn → moves to "Posted" folder)<br>
            <strong>You can close the page after clicking Accept!</strong> It continues in the background.<br>
            <strong>Reject:</strong> Moves this video to "Rejected" folder and shows you another one
        </div>
        
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p id="loadingText">Processing...</p>
            <div id="logs" style="
                margin-top: 20px;
                text-align: left;
                background: #f5f5f5;
                padding: 15px;
                border-radius: 8px;
                font-family: monospace;
                font-size: 13px;
                max-height: 300px;
                overflow-y: auto;
                display: none;
            "></div>
        </div>
    </div>
    
    <script>
        let eventSource = null;
        
        // Handle video loading
        const videoPlayer = document.getElementById('videoPlayer');
        const videoLoading = document.getElementById('videoLoading');
        let videoShown = false;
        
        function showVideo() {
            if (videoShown) return;
            videoShown = true;
            // Hide loading, show video
            videoLoading.style.display = 'none';
            videoPlayer.style.display = 'block';
            // Auto-play once loaded (with fallback for mobile)
            const playPromise = videoPlayer.play();
            if (playPromise !== undefined) {
                playPromise.catch(e => {
                    console.log('Autoplay prevented:', e);
                    // On mobile, autoplay might be blocked - that's okay
                });
            }
        }
        
        // Multiple event listeners for better mobile compatibility
        videoPlayer.addEventListener('loadeddata', showVideo);
        videoPlayer.addEventListener('canplay', showVideo);
        videoPlayer.addEventListener('loadedmetadata', function() {
            // Start showing video after metadata loads (faster on mobile)
            setTimeout(showVideo, 100);
        });
        
        videoPlayer.addEventListener('error', function(e) {
            console.error('Video error:', e);
            videoLoading.innerHTML = '<p style="color: #dc3545; font-size: 16px;">⚠️ Error loading video. Please refresh the page.</p>';
        });
        
        // Fallback: Show video after 3 seconds even if events don't fire
        setTimeout(function() {
            if (!videoShown && videoPlayer.readyState > 0) {
                console.log('Fallback: showing video after timeout');
                showVideo();
            }
        }, 3000);
        
        function handleAction(action) {
            // Disable buttons
            const buttons = document.querySelectorAll('button');
            buttons.forEach(btn => btn.disabled = true);
            
            // Show loading
            const loading = document.getElementById('loading');
            const loadingText = document.getElementById('loadingText');
            const logsDiv = document.getElementById('logs');
            loading.style.display = 'block';
            
            if (action === 'accept') {
                loadingText.textContent = 'Starting processing... (you can close this page)';
            } else {
                loadingText.textContent = 'Moving video to Rejected folder...';
            }
            
            // Send request
            fetch('/' + action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    if (action === 'accept' && data.video_id) {
                        // Show logs container
                        logsDiv.style.display = 'block';
                        loadingText.textContent = '🎬 Processing in background (you can close this page or watch logs)';
                        
                        // Connect to log stream
                        eventSource = new EventSource('/logs/' + data.video_id);
                        
                        eventSource.onmessage = function(event) {
                            const message = event.data;
                            
                            if (message === 'DONE') {
                                // Processing complete - close the window
                                loadingText.textContent = '✅ All done! Closing window...';
                                eventSource.close();
                                setTimeout(() => {
                                    window.close();
                                    // Fallback: if window.close() doesn't work (some browsers), show message
                                    setTimeout(() => {
                                        loadingText.textContent = '✅ All done! You can close this window now.';
                                    }, 500);
                                }, 1500);
                            } else if (message === '...') {
                                // Keep-alive, ignore
                            } else {
                                // Add log message
                                const logLine = document.createElement('div');
                                logLine.textContent = message;
                                logLine.style.marginBottom = '5px';
                                logsDiv.appendChild(logLine);
                                // Auto-scroll to bottom
                                logsDiv.scrollTop = logsDiv.scrollHeight;
                            }
                        };
                        
                        eventSource.onerror = function() {
                            console.log('Log stream ended');
                            eventSource.close();
                        };
                        
                    } else {
                        // Redirect to new video (reject action)
                        window.location.href = '/';
                    }
                } else {
                    alert('Error: ' + (data.error || 'Unknown error'));
                    window.location.href = '/';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert('An error occurred. Please try again.');
                window.location.href = '/';
            });
        }
        
        // Close event source when leaving page
        window.addEventListener('beforeunload', function() {
            if (eventSource) {
                eventSource.close();
            }
        });
    </script>
</body>
</html>
"""

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page - uses API key authentication"""
    from flask import request
    config_status = get_runtime_config_status()

    if not config_status['auth_configured']:
        return render_template_string(
            LOGIN_TEMPLATE,
            error="Server configuration error: AUTOPOST_API_KEY is not set on Vercel. Add it in Project Settings -> Environment Variables and redeploy."
        ), 500
    
    # Check device whitelist BEFORE showing login
    if DEVICE_RESTRICTION_ENABLED:
        is_allowed, device_info = device_manager.is_device_allowed(request)
        if not is_allowed:
            # Device not whitelisted - redirect immediately
            return redirect('/device-blocked')
    
    # Check for API key in URL parameter (GET request)
    api_key_from_url = request.args.get('api_key', '').strip()
    if api_key_from_url:
        if AUTOPOST_API_KEY and api_key_from_url == AUTOPOST_API_KEY:
            session['authenticated'] = True
            return redirect('/')
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid API key")
    
    if request.method == 'POST':
        api_key = request.form.get('api_key', '').strip()
        
        # Validate API key against AUTOPOST_API_KEY
        if AUTOPOST_API_KEY and api_key == AUTOPOST_API_KEY:
            session['authenticated'] = True
            return redirect('/')
        else:
            return render_template_string(LOGIN_TEMPLATE, error="Invalid API key")
    
    # If already authenticated, redirect to home
    if session.get('authenticated'):
        return redirect('/')
    
    return render_template_string(LOGIN_TEMPLATE)

@app.route('/logout')
def logout():
    """Logout and clear session"""
    session.clear()
    return redirect('/login')

@app.route('/device-blocked')
def device_blocked():
    """Show page when device is not whitelisted"""
    device_data = device_manager.get_device_fingerprint(request)
    device_info = device_manager.get_device_info(request)
    
    return render_template_string(DEVICE_BLOCKED_TEMPLATE, 
                                 device_info=device_info,
                                 fingerprint=device_data['fingerprint'])

@app.route('/device-setup', methods=['GET', 'POST'])
def device_setup():
    """Setup page to whitelist your devices (password protected)"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        action = request.form.get('action', '')
        
        # Verify API key (use AUTOPOST_API_KEY instead of password)
        if not AUTOPOST_API_KEY or password != AUTOPOST_API_KEY:
            return render_template_string(DEVICE_SETUP_TEMPLATE, 
                                         error="Invalid API key",
                                         devices=device_manager.list_devices())
        
        if action == 'add':
            device_name = request.form.get('device_name', '')
            success, result = device_manager.add_device(request, device_name)
            if success:
                message = f"✓ Device '{result['name']}' added successfully!"
            else:
                message = f"⚠️ {result}"
            
            return render_template_string(DEVICE_SETUP_TEMPLATE,
                                         message=message,
                                         devices=device_manager.list_devices())
        
        elif action == 'remove':
            fingerprint = request.form.get('fingerprint', '')
            success = device_manager.remove_device(fingerprint)
            message = "✓ Device removed" if success else "⚠️ Device not found"
            
            return render_template_string(DEVICE_SETUP_TEMPLATE,
                                         message=message,
                                         devices=device_manager.list_devices())
    
    # GET request
    current_device = device_manager.get_device_fingerprint(request)
    current_info = device_manager.get_device_info(request)
    
    return render_template_string(DEVICE_SETUP_TEMPLATE,
                                 devices=device_manager.list_devices(),
                                 current_device=current_device,
                                 current_info=current_info)

@app.route('/export-whitelist')
def export_whitelist():
    """Export whitelist as JSON (for copying to environment variable)"""
    # Require authentication
    if not session.get('authenticated'):
        return redirect('/login')
    
    whitelist_json = device_manager.get_whitelist_json()
    return Response(
        whitelist_json,
        mimetype='application/json',
        headers={'Content-Disposition': 'attachment; filename=device_whitelist.json'}
    )

@app.route('/robots.txt')
def robots():
    """Prevent search engine indexing"""
    return """User-agent: *
Disallow: /
""", 200, {'Content-Type': 'text/plain'}

@app.route('/')
@require_auth
def index():
    """Show random video preview"""
    try:
        # Select random video
        video = select_random_video()
        
        if not video:
            return "<h1>No videos found in Google Drive folder!</h1>", 404
        
        # Store video ID in session
        session['current_video_id'] = video['id']
        session['current_video_name'] = video['name']
        
        # Extract category from filename
        filename = video['name']
        category = filename.split('_')[0] if '_' in filename else 'other'
        
        return render_template_string(
            HOME_TEMPLATE,
            filename=filename,
            video_id=video['id'],
            category=category.title()
        )
    except Exception as e:
        return f"<h1>Error: {str(e)}</h1>", 500

@app.route('/video/<file_id>')
def stream_video(file_id):
    """Stream video from Google Drive - with SSL workaround"""
    try:
        manager = get_drive_manager()
        
        # Workaround: Download to temp file instead of streaming
        # This avoids SSL issues during chunked transfer
        temp_path = f"/tmp/preview_{file_id}.mp4"
        
        # Check if already cached
        if not os.path.exists(temp_path):
            print(f"  → Downloading video for preview...")
            manager.download_video(file_id, temp_path)
        else:
            print(f"  → Using cached video")
        
        # Serve the file
        with open(temp_path, 'rb') as f:
            video_data = f.read()
        
        return Response(
            video_data,
            mimetype='video/mp4',
            headers={
                'Content-Disposition': 'inline',
                'Accept-Ranges': 'bytes',
                'Cache-Control': 'public, max-age=3600'
            }
        )
            
    except Exception as e:
        print(f"Error streaming video: {str(e)}")
        import traceback
        traceback.print_exc()
        return f"Error streaming video: {str(e)}", 500

@app.route('/accept', methods=['POST'])
def accept_video():
    """Accept video: generate description, post to LinkedIn, delete from Drive"""
    try:
        video_id = session.get('current_video_id')
        video_name = session.get('current_video_name')
        
        if not video_id:
            return jsonify({'success': False, 'error': 'No video selected'}), 400
        
        print(f"\n✓ Video accepted: {video_name}")
        
        # Create a queue for this video's logs
        log_queue = queue.Queue()
        log_queues[video_id] = log_queue
        
        def log(message):
            """Send log to queue and print"""
            print(message)
            try:
                log_queue.put(message)
            except:
                pass
        
        # Start background processing
        def process_in_background():
            """Process video in background - continues even if browser closes"""
            temp_path = None
            temp_path2 = None
            image_path = None
            try:
                log("🎬 Starting 2-video processing...")

                import concurrent.futures

                description = None

                log("📥 Downloading video 1 (randomly selected)...")
                manager = get_drive_manager()
                temp_path = f"/tmp/{video_id}_processing.mp4"
                manager.download_video(video_id, temp_path)
                log("✅ Video 1 downloaded for processing")

                promo_video = get_random_promo_video()
                if promo_video:
                    log(f"📥 Downloading promo video ({promo_video['file_id']})...")
                    temp_path2 = f"/tmp/{promo_video['file_id']}_processing.mp4"
                    manager.download_video(promo_video['file_id'], temp_path2)
                    log(f"✅ Promo video downloaded")
                    description2 = promo_video['caption']
                    log(f"📝 Promo caption: {description2[:100]}...")
                else:
                    log("⏭️ No promo videos configured, skipping second video")
                    temp_path2 = None
                    description2 = None

                # Parameterized post functions (reusable for both videos)
                def post_linkedin(path, desc):
                    log("📤 Posting to LinkedIn...")
                    result = post_to_linkedin_with_local_file(path, desc)
                    if result.get('success'):
                        log(f"✅ Posted to LinkedIn successfully! (Platform: {result.get('platform', 'unknown')})")
                        if result.get('drive_link'):
                            log(f"  → Drive link: {result['drive_link']}")
                        post_urn = result.get('post_urn')
                        if TOP_COMMENT and post_urn and isinstance(post_urn, str):
                            log("💬 Adding top comment to LinkedIn...")
                            add_linkedin_comment(post_urn, TOP_COMMENT)
                        return True
                    else:
                        log(f"⚠️ LinkedIn posting failed: {result.get('message', 'Unknown error')}")
                        return False

                def post_instagram(path, desc):
                    if not INSTAGRAM_ENABLED:
                        log("⏭️ Instagram posting disabled, skipping...")
                        return False
                    log("📸 Posting to Instagram Reels...")
                    result = post_to_instagram_reel(path, desc, top_comment=TOP_COMMENT)
                    if result['success']:
                        log(f"✅ Posted to Instagram! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"⚠️ Instagram posting failed: {result['error']}")
                        return False

                def post_threads(path, desc):
                    if not THREADS_ENABLED:
                        log("⏭️ Threads posting disabled, skipping...")
                        return False
                    log("🧵 Posting to Threads...")
                    result = post_to_threads(path, desc, top_comment=TOP_COMMENT)
                    if result['success']:
                        log(f"✅ Posted to Threads! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"⚠️ Threads posting failed: {result['error']}")
                        return False

                def post_facebook(path, desc):
                    if not FACEBOOK_ENABLED:
                        log("⏭️ Facebook posting disabled, skipping...")
                        return False
                    log("📘 Posting to Facebook...")
                    result = post_to_facebook(path, desc, top_comment=TOP_COMMENT)
                    if result['success']:
                        log(f"✅ Posted to Facebook! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"⚠️ Facebook posting failed: {result['error']}")
                        return False

                def post_twitter(path, desc):
                    if not TWITTER_ENABLED:
                        log("⏭️ Twitter posting disabled, skipping...")
                        return False
                    log("🐦 Posting to Twitter (X)...")
                    result = post_to_twitter(path, desc)
                    if result['success']:
                        log(f"✅ Posted to Twitter! Tweet ID: {result['media_id']}")
                        return True
                    else:
                        log(f"⚠️ Twitter posting failed: {result['error']}")
                        return False

                # Check for promo image
                promo_image = get_random_promo_image()
                image_path = None
                if promo_image:
                    log(f"🖼️  Downloading promo image from Drive ({promo_image['name']})...")
                    image_path = f"/tmp/{promo_image['id']}_image.png"
                    manager.download_image(promo_image['id'], image_path)
                    log(f"✅ Promo image downloaded: {promo_image['name']}")
                else:
                    log("⏭️ No promo images available, skipping image post")

                log("⚡ Video 2 + Image posting immediately while video 1 gets AI description...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
                    # Video 2 (promo): Post immediately if available - no AI needed
                    if promo_video:
                        f2_linkedin = executor.submit(post_linkedin, temp_path2, description2)
                        f2_instagram = executor.submit(post_instagram, temp_path2, description2)
                        f2_threads = executor.submit(post_threads, temp_path2, description2)
                        f2_facebook = executor.submit(post_facebook, temp_path2, description2)
                        f2_twitter = executor.submit(post_twitter, temp_path2, description2)
                    else:
                        f2_linkedin = f2_instagram = f2_threads = f2_facebook = f2_twitter = None

                    # Promo image: Post immediately if available
                    if promo_image:
                        log(f"🖼️  Posting image to LinkedIn: {PROMO_IMAGE_CAPTION}")
                        f2_image = executor.submit(post_to_linkedin_image, image_path, PROMO_IMAGE_CAPTION)
                    else:
                        f2_image = None

                    # Video 1 (randomly selected): Generate AI description first, then post
                    def process_video1():
                        log("🤖 Generating AI description with Gemini for video 1...")
                        desc = generate_video_description(video_id, local_video_path=temp_path)
                        if not desc:
                            raise Exception("Gemini returned empty description")
                        log(f"✅ Description generated for video 1: {desc[:100]}...")
                        desc = add_credit_to_description(desc, video_name)
                        log(f"📝 Added credit to video 1 description")
                        nonlocal description
                        description = desc
                        log("📤 Video 1 posting to all platforms...")
                        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as inner:
                            i_l = inner.submit(post_linkedin, temp_path, desc)
                            i_i = inner.submit(post_instagram, temp_path, desc)
                            i_t = inner.submit(post_threads, temp_path, desc)
                            i_f = inner.submit(post_facebook, temp_path, desc)
                            i_x = inner.submit(post_twitter, temp_path, desc)
                            return {
                                'linkedin': i_l.result(),
                                'instagram': i_i.result(),
                                'threads': i_t.result(),
                                'facebook': i_f.result(),
                                'twitter': i_x.result()
                            }

                    f1_all = executor.submit(process_video1)

                    # Collect video 2 results (if available)
                    linkedin_success2 = f2_linkedin.result() if f2_linkedin else False
                    instagram_success2 = f2_instagram.result() if f2_instagram else False
                    threads_success2 = f2_threads.result() if f2_threads else False
                    facebook_success2 = f2_facebook.result() if f2_facebook else False
                    twitter_success2 = f2_twitter.result() if f2_twitter else False

                    # Collect image result (if available)
                    image_result = f2_image.result() if f2_image else None
                    image_success = image_result.get('success', False) if image_result else False

                    # Collect video 1 results
                    v1 = f1_all.result()
                    linkedin_success = v1['linkedin']
                    instagram_success = v1['instagram']
                    threads_success = v1['threads']
                    facebook_success = v1['facebook']
                    twitter_success = v1['twitter']

                if promo_image and image_success:
                    log("🖼️  Promo Image: SUCCESS")
                elif promo_image:
                    log("🖼️  Promo Image: FAILED")
                if linkedin_success:
                    log("🎯 LinkedIn Video 1: SUCCESS")
                if linkedin_success2:
                    log("🎯 LinkedIn Video 2: SUCCESS")
                if instagram_success:
                    log("🎯 Instagram Video 1: SUCCESS")
                if instagram_success2:
                    log("🎯 Instagram Video 2: SUCCESS")
                if threads_success:
                    log("🎯 Threads Video 1: SUCCESS")
                if threads_success2:
                    log("🎯 Threads Video 2: SUCCESS")
                if facebook_success:
                    log("🎯 Facebook Video 1: SUCCESS")
                if facebook_success2:
                    log("🎯 Facebook Video 2: SUCCESS")
                if twitter_success:
                    log("🎯 Twitter Video 1: SUCCESS")
                if twitter_success2:
                    log("🎯 Twitter Video 2: SUCCESS")

                # Move video 1 to Posted folder instead of deleting
                log("📂 Moving video 1 to Posted folder...")
                manager = get_drive_manager()

                # Get or create Posted folder
                global posted_folder_id
                if not posted_folder_id:
                    posted_folder_id = manager.find_or_create_folder(
                        POSTED_FOLDER_NAME,
                        parent_folder_id=GOOGLE_DRIVE_FOLDER_ID
                    )

                if posted_folder_id:
                    success = manager.move_video(video_id, posted_folder_id)
                    if success:
                        log("✅ Moved video 1 to Posted folder")
                    else:
                        log("⚠️  Could not move (will try to delete)")
                        # Fallback to delete if move fails
                        manager.delete_video(video_id)
                else:
                    log("⚠️  Could not create Posted folder (will try to delete)")
                    manager.delete_video(video_id)

                # Cleanup video 1 temp file
                if temp_path and os.path.exists(temp_path):
                    os.unlink(temp_path)

                log("🧹 Cleaned up temp files")

                log(f"🎉 All done! Both videos processed successfully!")
                log("DONE")  # Signal completion

            except Exception as e:
                log(f"❌ Error: {str(e)}")
                log("DONE")
                import traceback
                traceback.print_exc()
            finally:
                # Always clean up temp files regardless of success or failure
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                    except Exception:
                        pass
                if temp_path2 and os.path.exists(temp_path2):
                    try:
                        os.unlink(temp_path2)
                    except Exception:
                        pass
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                    except Exception:
                        pass
                # Also clean up preview temp if exists
                preview_temp = f"/tmp/preview_{video_id}.mp4"
                if os.path.exists(preview_temp):
                    try:
                        os.unlink(preview_temp)
                    except Exception:
                        pass
        
        # Start background thread
        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()
        
        # Clear session
        session.pop('current_video_id', None)
        session.pop('current_video_name', None)
        
        # Return immediately with log stream info
        return jsonify({
            'success': True,
            'video_id': video_id,
            'message': 'Processing started! You can close this page or watch the logs.'
        })
        
    except Exception as e:
        print(f"Error in accept: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/logs/<video_id>')
def stream_logs(video_id):
    """Stream logs for a video in real-time"""
    def generate():
        log_queue = log_queues.get(video_id)
        if not log_queue:
            yield "data: Log stream not found\n\n"
            return
        
        while True:
            try:
                # Get log message with timeout
                message = log_queue.get(timeout=30)
                
                # Check if processing is done
                if message == "DONE":
                    yield f"data: {message}\n\n"
                    # Clean up queue
                    if video_id in log_queues:
                        del log_queues[video_id]
                    break
                
                # Send log message
                yield f"data: {message}\n\n"
                
            except queue.Empty:
                # Keep connection alive
                yield "data: ...\n\n"
                
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no'
        }
    )

@app.route('/reject', methods=['POST'])
def reject_video():
    """Reject video: move to Rejected folder"""
    try:
        video_id = session.get('current_video_id')
        video_name = session.get('current_video_name')
        
        if not video_id:
            return jsonify({'success': False, 'error': 'No video selected'}), 400
        
        print(f"\n✗ Video rejected: {video_name}")
        
        # Move to Rejected folder instead of deleting
        print("Moving to Rejected folder...")
        manager = get_drive_manager()
        
        # Get or create Rejected folder
        global rejected_folder_id
        if not rejected_folder_id:
            rejected_folder_id = manager.find_or_create_folder(
                REJECTED_FOLDER_NAME,
                parent_folder_id=GOOGLE_DRIVE_FOLDER_ID
            )
        
        if rejected_folder_id:
            success = manager.move_video(video_id, rejected_folder_id)
            if success:
                print("✓ Moved to Rejected folder")
            else:
                print("⚠️  Could not move (will try to delete)")
                manager.delete_video(video_id)
        else:
            print("⚠️  Could not create Rejected folder (will try to delete)")
            manager.delete_video(video_id)
        
        # Cleanup temp file if exists
        temp_path = f"/tmp/preview_{video_id}.mp4"
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        
        print(f"✓ Processed: {video_name}")
        
        # Clear session
        session.pop('current_video_id', None)
        session.pop('current_video_name', None)
        
        return jsonify({'success': True})
        
    except Exception as e:
        print(f"Error in reject: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============================================================
# AUTOPOST API - Automatic posting without accept/reject flow
# ============================================================

def validate_api_key():
    """
    Validate API key from request headers.
    Returns (is_valid, error_message)
    """
    if not AUTOPOST_API_KEY:
        return False, "AUTOPOST_API_KEY not configured on server"
    
    # Check for API key in various headers
    api_key = request.headers.get('X-API-Key') or \
              request.headers.get('Authorization', '').replace('Bearer ', '') or \
              request.args.get('api_key')
    
    if not api_key:
        return False, "API key required. Provide via X-API-Key header, Authorization: Bearer <key>, or ?api_key= parameter"
    
    if api_key != AUTOPOST_API_KEY:
        return False, "Invalid API key"
    
    return True, None

def select_random_video_from_folder(folder_id):
    """
    Select a random video from a specific Google Drive folder.
    Similar to select_random_video but uses specified folder.
    """
    import time
    
    # Seed with current timestamp for extra randomness
    random.seed(time.time())
    
    manager = get_drive_manager()
    
    # Use the fast method - only fetches 50 videos instead of all
    print(f"🚀 Fetching random video from folder {folder_id}...")
    selected_video = manager.get_random_video_fast(folder_id, sample_size=50)
    
    if not selected_video:
        return None
    
    print(f"✅ Selected video: {selected_video['name']}")
    
    return selected_video

def get_or_create_autopost_posted_folder(manager, parent_folder_id):
    """
    Get or create Posted_Videos folder inside the autopost folder.
    """
    return manager.find_or_create_folder(
        POSTED_FOLDER_NAME,
        parent_folder_id=parent_folder_id
    )

@app.route('/autopost', methods=['POST', 'GET'])
def autopost():
    """
    Automatic posting endpoint - no accept/reject flow.
    Uses API key authentication instead of login.
    
    Flow:
    1. Validate API key
    2. Pick random video from AUTOPOST_FOLDER_ID
    3. Generate AI description
    4. Post to LinkedIn
    5. Move to Posted_Videos folder
    
    Can be triggered by cron job, webhook, or manual API call.
    
    Query parameters:
    - api_key: API key for authentication (alternative to header)
    - sync: If 'true', wait for processing to complete (default: false)
    
    Headers:
    - X-API-Key: API key for authentication
    - Authorization: Bearer <api_key>
    
    Returns:
    - JSON response with status and details
    """
    # Validate API key
    is_valid, error_msg = validate_api_key()
    if not is_valid:
        return jsonify({
            'success': False,
            'error': error_msg
        }), 401
    
    # Check if sync mode requested
    sync_mode = request.args.get('sync', 'false').lower() == 'true'
    
    try:
        # Step 1: Select random video from autopost folder
        print("\n" + "="*60)
        print("🤖 AUTOPOST: Starting automatic video post")
        print("="*60)
        
        video = select_random_video_from_folder(AUTOPOST_FOLDER_ID)
        
        if not video:
            return jsonify({
                'success': False,
                'error': 'No videos found in autopost folder',
                'folder_id': AUTOPOST_FOLDER_ID
            }), 404
        
        video_id = video['id']
        video_name = video['name']
        
        print(f"📹 Selected video: {video_name}")
        
        # Create a queue for logs
        log_queue = queue.Queue()
        log_queues[video_id] = log_queue
        
        def log(message):
            """Send log to queue and print"""
            print(message)
            try:
                log_queue.put(message)
            except:
                pass
        
        # Process result storage
        process_result = {'success': False, 'error': None, 'description': None}
        
        def process_autopost():
            """Process video automatically - no user interaction needed"""
            temp_path = None
            temp_path2 = None
            image_path = None
            try:
                log("🎬 AUTOPOST: Starting automatic 2-video processing...")

                import concurrent.futures

                description = None

                log("📥 AUTOPOST: Downloading video 1 (randomly selected)...")
                manager = get_drive_manager()
                temp_path = f"/tmp/{video_id}_autopost_processing.mp4"
                manager.download_video(video_id, temp_path)
                log("✅ AUTOPOST: Video 1 downloaded for processing")

                promo_video = get_random_promo_video()
                if promo_video:
                    log(f"📥 AUTOPOST: Downloading promo video ({promo_video['file_id']})...")
                    temp_path2 = f"/tmp/{promo_video['file_id']}_autopost_processing.mp4"
                    manager.download_video(promo_video['file_id'], temp_path2)
                    log(f"✅ AUTOPOST: Promo video downloaded")
                    description2 = promo_video['caption']
                    log(f"📝 AUTOPOST: Promo caption: {description2[:100]}...")
                else:
                    log("⏭️ AUTOPOST: No promo videos configured, skipping second video")
                    temp_path2 = None
                    description2 = None

                # Check for promo image
                promo_image = get_random_promo_image()
                if promo_image:
                    log(f"🖼️  AUTOPOST: Downloading promo image ({promo_image['name']})...")
                    image_path = f"/tmp/{promo_image['id']}_autopost_image.png"
                    manager.download_image(promo_image['id'], image_path)
                    log(f"✅ AUTOPOST: Promo image downloaded: {promo_image['name']}")
                else:
                    log("⏭️ AUTOPOST: No promo images available, skipping image post")

                # Parameterized post functions with retry logic (reusable for both videos)
                def post_linkedin(path, desc):
                    """Post to LinkedIn with retry logic."""
                    log("📤 AUTOPOST: Posting to LinkedIn...")
                    
                    def do_post():
                        result = post_to_linkedin_with_local_file(path, desc)
                        if not result.get('success'):
                            raise Exception(result.get('message', 'LinkedIn posting failed'))
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to LinkedIn successfully! (Platform: {result.get('platform', 'unknown')})")
                        if result.get('drive_link'):
                            log(f"  → Drive link: {result['drive_link']}")
                        post_urn = result.get('post_urn')
                        if TOP_COMMENT and post_urn and isinstance(post_urn, str):
                            log("💬 AUTOPOST: Adding top comment to LinkedIn...")
                            add_linkedin_comment(post_urn, TOP_COMMENT)
                        return True
                    else:
                        log(f"❌ AUTOPOST: LinkedIn posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='LinkedIn',
                            retry_attempts=3
                        )
                        return False

                def post_instagram(path, desc):
                    """Post to Instagram with retry logic."""
                    if not INSTAGRAM_ENABLED:
                        log("⏭️ AUTOPOST: Instagram posting disabled, skipping...")
                        return False
                    
                    log("📸 AUTOPOST: Posting to Instagram Reels...")
                    
                    def do_post():
                        result = post_to_instagram_reel(path, desc, top_comment=TOP_COMMENT)
                        if not result['success']:
                            raise Exception(result['error'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to Instagram! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: Instagram posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='Instagram',
                            retry_attempts=3
                        )
                        return False

                def post_threads(path, desc):
                    """Post to Threads with retry logic."""
                    if not THREADS_ENABLED:
                        log("⏭️ AUTOPOST: Threads posting disabled, skipping...")
                        return False
                    
                    log("🧵 AUTOPOST: Posting to Threads...")
                    
                    def do_post():
                        result = post_to_threads(path, desc, top_comment=TOP_COMMENT)
                        if not result['success']:
                            raise Exception(result['error'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to Threads! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: Threads posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='Threads',
                            retry_attempts=3
                        )
                        return False

                def post_facebook(path, desc):
                    """Post to Facebook with retry logic."""
                    if not FACEBOOK_ENABLED:
                        log("⏭️ AUTOPOST: Facebook posting disabled, skipping...")
                        return False
                    
                    log("📘 AUTOPOST: Posting to Facebook...")
                    
                    def do_post():
                        result = post_to_facebook(path, desc, top_comment=TOP_COMMENT)
                        if not result['success']:
                            raise Exception(result['error'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to Facebook! Media ID: {result['media_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: Facebook posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='Facebook',
                            retry_attempts=3
                        )
                        return False

                def post_twitter(path, desc):
                    """Post to Twitter with retry logic."""
                    if not TWITTER_ENABLED:
                        log("⏭️ AUTOPOST: Twitter posting disabled, skipping...")
                        return False
                    
                    log("🐦 AUTOPOST: Posting to Twitter (X)...")
                    
                    def do_post():
                        result = post_to_twitter(path, desc)
                        if not result['success']:
                            raise Exception(result['error'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to Twitter! Tweet ID: {result['media_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: Twitter posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='Twitter',
                            retry_attempts=3
                        )
                        return False

                def post_tiktok(path, desc):
                    """Post to TikTok with retry logic."""
                    if not TIKTOK_ENABLED:
                        log("⏭️ AUTOPOST: TikTok posting disabled, skipping...")
                        return False
                    
                    log("🎵 AUTOPOST: Posting to TikTok...")
                    
                    def do_post():
                        result = post_to_tiktok(path, desc)
                        if not result['success']:
                            raise Exception(result['message'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to TikTok! Video ID: {result['video_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: TikTok posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='TikTok',
                            retry_attempts=3
                        )
                        return False

                def post_youtube(path, desc):
                    """Post to YouTube Shorts with retry logic."""
                    if not YOUTUBE_ENABLED:
                        log("⏭️ AUTOPOST: YouTube posting disabled, skipping...")
                        return False
                    
                    log("📺 AUTOPOST: Posting to YouTube Shorts...")
                    
                    def do_post():
                        result = post_to_youtube_shorts(path, desc)
                        if not result['success']:
                            raise Exception(result['error'])
                        return result
                    
                    success, result, error = retry_operation(
                        do_post,
                        max_retries=3,
                        base_delay=2.0,
                        exceptions=(Exception,)
                    )
                    
                    if success:
                        log(f"✅ AUTOPOST: Posted to YouTube Shorts! Video ID: {result['video_id']}")
                        return True
                    else:
                        log(f"❌ AUTOPOST: YouTube posting failed after retries: {error}")
                        send_cmo_alert(
                            error_message=error,
                            video_id=video_id,
                            video_name=video_name,
                            platform='YouTube',
                            retry_attempts=3
                        )
                        return False

                log("⚡ AUTOPOST: Video 2 + Image posting immediately while video 1 gets AI description...")
                with concurrent.futures.ThreadPoolExecutor(max_workers=14) as executor:
                    # Video 2 (promo): Post immediately if available - no AI needed
                    if promo_video:
                        f2_linkedin = executor.submit(post_linkedin, temp_path2, description2)
                        f2_instagram = executor.submit(post_instagram, temp_path2, description2)
                        f2_threads = executor.submit(post_threads, temp_path2, description2)
                        f2_facebook = executor.submit(post_facebook, temp_path2, description2)
                        f2_twitter = executor.submit(post_twitter, temp_path2, description2)
                        f2_tiktok = executor.submit(post_tiktok, temp_path2, description2)
                        f2_youtube = executor.submit(post_youtube, temp_path2, description2)
                    else:
                        f2_linkedin = f2_instagram = f2_threads = f2_facebook = f2_twitter = f2_tiktok = f2_youtube = None

                    # Promo image: Post immediately if available
                    if promo_image:
                        log(f"🖼️  AUTOPOST: Posting image to LinkedIn: {PROMO_IMAGE_CAPTION}")
                        f2_image = executor.submit(post_to_linkedin_image, image_path, PROMO_IMAGE_CAPTION)
                    else:
                        f2_image = None

                    # Video 1 (randomly selected): Generate AI description first, then post
                    def process_video1():
                        log("🤖 AUTOPOST: Generating AI description with Gemini for video 1...")
                        desc = generate_video_description(video_id, local_video_path=temp_path)
                        if not desc:
                            raise Exception("Gemini returned empty description")
                        log(f"✅ AUTOPOST: Description generated for video 1: {desc[:100]}...")
                        desc = add_credit_to_description(desc, video_name)
                        log(f"📝 AUTOPOST: Added credit to video 1 description")
                        nonlocal description
                        description = desc
                        process_result['description'] = desc
                        log("📤 AUTOPOST: Video 1 posting to all platforms...")
                        with concurrent.futures.ThreadPoolExecutor(max_workers=7) as inner:
                            i_l = inner.submit(post_linkedin, temp_path, desc)
                            i_i = inner.submit(post_instagram, temp_path, desc)
                            i_t = inner.submit(post_threads, temp_path, desc)
                            i_f = inner.submit(post_facebook, temp_path, desc)
                            i_x = inner.submit(post_twitter, temp_path, desc)
                            i_tt = inner.submit(post_tiktok, temp_path, desc)
                            i_yt = inner.submit(post_youtube, temp_path, desc)
                            return {
                                'linkedin': i_l.result(),
                                'instagram': i_i.result(),
                                'threads': i_t.result(),
                                'facebook': i_f.result(),
                                'twitter': i_x.result(),
                                'tiktok': i_tt.result(),
                                'youtube': i_yt.result()
                            }

                    f1_all = executor.submit(process_video1)

                    # Collect video 2 results (if available)
                    linkedin_success2 = f2_linkedin.result() if f2_linkedin else False
                    instagram_success2 = f2_instagram.result() if f2_instagram else False
                    threads_success2 = f2_threads.result() if f2_threads else False
                    facebook_success2 = f2_facebook.result() if f2_facebook else False
                    twitter_success2 = f2_twitter.result() if f2_twitter else False
                    tiktok_success2 = f2_tiktok.result() if f2_tiktok else False
                    youtube_success2 = f2_youtube.result() if f2_youtube else False

                    # Collect image result (if available)
                    image_result = f2_image.result() if f2_image else None
                    image_success = image_result.get('success', False) if image_result else False

                    # Collect video 1 results
                    v1 = f1_all.result()
                    linkedin_success = v1['linkedin']
                    instagram_success = v1['instagram']
                    threads_success = v1['threads']
                    facebook_success = v1['facebook']
                    twitter_success = v1['twitter']
                    tiktok_success = v1['tiktok']
                    youtube_success = v1['youtube']

                # Track failures for aggregate alert
                all_failures = []

                if promo_image and image_success:
                    log("🖼️  AUTOPOST: Promo Image: SUCCESS")
                elif promo_image:
                    log("🖼️  AUTOPOST: Promo Image: FAILED")
                
                if linkedin_success:
                    log("🎯 AUTOPOST: LinkedIn Video 1: SUCCESS")
                else:
                    all_failures.append('LinkedIn')
                    log("🎯 AUTOPOST: LinkedIn Video 1: FAILED")
                    
                if linkedin_success2:
                    log("🎯 AUTOPOST: LinkedIn Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('LinkedIn (Video 2)')
                    log("🎯 AUTOPOST: LinkedIn Video 2: FAILED")
                    
                if instagram_success:
                    log("🎯 AUTOPOST: Instagram Video 1: SUCCESS")
                else:
                    all_failures.append('Instagram')
                    log("🎯 AUTOPOST: Instagram Video 1: FAILED")
                    
                if instagram_success2:
                    log("🎯 AUTOPOST: Instagram Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('Instagram (Video 2)')
                    log("🎯 AUTOPOST: Instagram Video 2: FAILED")
                    
                if threads_success:
                    log("🎯 AUTOPOST: Threads Video 1: SUCCESS")
                else:
                    all_failures.append('Threads')
                    log("🎯 AUTOPOST: Threads Video 1: FAILED")
                    
                if threads_success2:
                    log("🎯 AUTOPOST: Threads Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('Threads (Video 2)')
                    log("🎯 AUTOPOST: Threads Video 2: FAILED")
                    
                if facebook_success:
                    log("🎯 AUTOPOST: Facebook Video 1: SUCCESS")
                else:
                    all_failures.append('Facebook')
                    log("🎯 AUTOPOST: Facebook Video 1: FAILED")
                    
                if facebook_success2:
                    log("🎯 AUTOPOST: Facebook Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('Facebook (Video 2)')
                    log("🎯 AUTOPOST: Facebook Video 2: FAILED")
                    
                if twitter_success:
                    log("🎯 AUTOPOST: Twitter Video 1: SUCCESS")
                else:
                    all_failures.append('Twitter')
                    log("🎯 AUTOPOST: Twitter Video 1: FAILED")
                    
                if twitter_success2:
                    log("🎯 AUTOPOST: Twitter Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('Twitter (Video 2)')
                    log("🎯 AUTOPOST: Twitter Video 2: FAILED")
                    
                if tiktok_success:
                    log("🎯 AUTOPOST: TikTok Video 1: SUCCESS")
                else:
                    all_failures.append('TikTok')
                    log("🎯 AUTOPOST: TikTok Video 1: FAILED")
                    
                if tiktok_success2:
                    log("🎯 AUTOPOST: TikTok Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('TikTok (Video 2)')
                    log("🎯 AUTOPOST: TikTok Video 2: FAILED")
                    
                if youtube_success:
                    log("🎯 AUTOPOST: YouTube Shorts Video 1: SUCCESS")
                else:
                    all_failures.append('YouTube')
                    log("🎯 AUTOPOST: YouTube Shorts Video 1: FAILED")
                    
                if youtube_success2:
                    log("🎯 AUTOPOST: YouTube Shorts Video 2: SUCCESS")
                elif promo_video:
                    all_failures.append('YouTube (Video 2)')
                    log("🎯 AUTOPOST: YouTube Shorts Video 2: FAILED")
                
                # Send aggregate CMO alert if all platforms failed
                if len(all_failures) >= 5:  # More than 5 failures indicates a systemic issue
                    log(f"🚨 AUTOPOST: Critical failure - {len(all_failures)} platform(s) failed")
                    send_cmo_alert(
                        error_message=f"Auto-posting systemic failure: {len(all_failures)} platforms failed: {', '.join(all_failures)}",
                        video_id=video_id,
                        video_name=video_name,
                        platform='All Platforms',
                        retry_attempts=3
                    )

                # Move video 1 to Posted folder inside autopost folder
                log("📂 AUTOPOST: Moving video 1 to Posted folder...")
                manager = get_drive_manager()

                # Get or create Posted folder inside autopost folder
                autopost_posted_folder_id = get_or_create_autopost_posted_folder(
                    manager, AUTOPOST_FOLDER_ID
                )

                if autopost_posted_folder_id:
                    success = manager.move_video(video_id, autopost_posted_folder_id)
                    if success:
                        log("✅ AUTOPOST: Moved video 1 to Posted folder")
                    else:
                        log("⚠️ AUTOPOST: Could not move video 1")
                else:
                    log("⚠️ AUTOPOST: Could not create Posted folder")

                log(f"🎉 AUTOPOST: Both videos processed successfully!")
                log("DONE")

                process_result['success'] = True

            except Exception as e:
                error_msg = str(e)
                log(f"❌ AUTOPOST Error: {error_msg}")
                log("DONE")
                process_result['error'] = error_msg
                import traceback
                traceback.print_exc()
            finally:
                # Always clean up temp files regardless of success or failure
                if temp_path and os.path.exists(temp_path):
                    try:
                        os.unlink(temp_path)
                        log("🧹 AUTOPOST: Cleaned up video 1 temp file")
                    except Exception:
                        pass
                if temp_path2 and os.path.exists(temp_path2):
                    try:
                        os.unlink(temp_path2)
                        log("🧹 AUTOPOST: Cleaned up video 2 temp file")
                    except Exception:
                        pass
                if image_path and os.path.exists(image_path):
                    try:
                        os.unlink(image_path)
                        log("🧹 AUTOPOST: Cleaned up promo image temp file")
                    except Exception:
                        pass
        
        if sync_mode:
            # Synchronous mode - wait for completion
            process_autopost()
            
            # Clean up queue
            if video_id in log_queues:
                del log_queues[video_id]
            
            # Check if browser wants HTML (not API call)
            wants_html = 'text/html' in request.headers.get('Accept', '') or request.args.get('format') == 'html'
            
            if process_result['success']:
                if wants_html:
                    return render_template_string(AUTOPOST_RESULT_TEMPLATE,
                        success=True,
                        message=f"Video posted successfully!",
                        video_name=video_name,
                        video_id=video_id,
                        description=process_result['description'],
                        creator=extract_creator_name(video_name),
                        error=None
                    )
                else:
                    return jsonify({
                        'success': True,
                        'message': f"Video '{video_name}' posted successfully!",
                        'video_id': video_id,
                        'video_name': video_name,
                        'description': process_result['description']
                    })
            else:
                if wants_html:
                    return render_template_string(AUTOPOST_RESULT_TEMPLATE,
                        success=False,
                        message="Failed to post video",
                        video_name=video_name,
                        video_id=video_id,
                        description=None,
                        creator=None,
                        error=process_result['error']
                    )
                else:
                    return jsonify({
                        'success': False,
                        'error': process_result['error'],
                        'video_id': video_id,
                        'video_name': video_name
                    }), 500
        else:
            # Async mode - but for browser, force sync mode to show result directly
            wants_html = 'text/html' in request.headers.get('Accept', '') or request.args.get('format') == 'html'
            
            if wants_html:
                # Browser request - run synchronously and show result
                process_autopost()
                
                # Clean up queue
                if video_id in log_queues:
                    del log_queues[video_id]
                
                if process_result['success']:
                    return render_template_string(AUTOPOST_RESULT_TEMPLATE,
                        success=True,
                        message=f"Video posted successfully!",
                        video_name=video_name,
                        video_id=video_id,
                        description=process_result['description'],
                        creator=extract_creator_name(video_name),
                        error=None
                    )
                else:
                    return render_template_string(AUTOPOST_RESULT_TEMPLATE,
                        success=False,
                        message="Failed to post video",
                        video_name=video_name,
                        video_id=video_id,
                        description=None,
                        creator=extract_creator_name(video_name),
                        error=process_result['error']
                    )
            else:
                # API request - run async
                thread = threading.Thread(target=process_autopost, daemon=True)
                thread.start()
                
                return jsonify({
                    'success': True,
                    'message': 'Autopost processing started!',
                    'video_id': video_id,
                    'video_name': video_name,
                    'log_stream': f'/logs/{video_id}',
                    'note': 'Add ?sync=true to wait for completion'
                })
        
    except Exception as e:
        print(f"❌ AUTOPOST Error: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/autopost/status')
def autopost_status():
    """
    Check autopost configuration status.
    Returns info about folder and configuration.
    """
    # Validate API key
    is_valid, error_msg = validate_api_key()
    if not is_valid:
        wants_html = 'text/html' in request.headers.get('Accept', '') or request.args.get('format') == 'html'
        if wants_html:
            return render_template_string(AUTOPOST_STATUS_TEMPLATE,
                success=False,
                error=error_msg,
                videos_available=0,
                folder_id=AUTOPOST_FOLDER_ID,
                config={}
            ), 401
        return jsonify({
            'success': False,
            'error': error_msg
        }), 401
    
    try:
        manager = get_drive_manager()
        
        # Try to list videos in autopost folder
        videos = manager.list_videos_in_folder(AUTOPOST_FOLDER_ID)
        
        config = get_runtime_config_status()
        
        # Check if browser wants HTML
        wants_html = 'text/html' in request.headers.get('Accept', '') or request.args.get('format') == 'html'
        
        if wants_html:
            return render_template_string(AUTOPOST_STATUS_TEMPLATE,
                success=True,
                error=None,
                videos_available=len(videos),
                folder_id=AUTOPOST_FOLDER_ID,
                config=config
            )
        
        return jsonify({
            'success': True,
            'autopost_folder_id': AUTOPOST_FOLDER_ID,
            'videos_available': len(videos),
            'configuration': config
        })
        
    except Exception as e:
        wants_html = 'text/html' in request.headers.get('Accept', '') or request.args.get('format') == 'html'
        if wants_html:
            return render_template_string(AUTOPOST_STATUS_TEMPLATE,
                success=False,
                error=str(e),
                videos_available=0,
                folder_id=AUTOPOST_FOLDER_ID,
                config={}
            ), 500
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/health')
def health():
    """Health check endpoint"""
    config = get_runtime_config_status()
    status_code = 200 if config['auth_configured'] else 500
    return jsonify({
        'status': 'healthy' if status_code == 200 else 'degraded',
        'configuration': config
    }), status_code

if __name__ == '__main__':
    # For local development
    app.run(debug=True, port=5000)

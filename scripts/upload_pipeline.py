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
import random
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

# Instagram reach / discovery options (all OPTIONAL — each is a no-op if its env var is unset,
# so existing deployments behave exactly as before until these are configured).
# PAST: the Reel container sent only media_type/video_url/caption/access_token.
# ISSUE: no collaborators, no chosen cover frame, no feed-share flag, and the store link sat in
#        the caption — leaving free Graph-API reach/discovery signals on the table.
# PRESENT: expose collaborators, a cover frame (thumb_offset), share_to_feed, an optional location,
#          and a "link in first comment" toggle, all driven by env config.
# RATIONALE: collaborator posts reach a partner's whole audience, a strong cover lifts profile
#            visits→follows, and a link-free caption avoids the reach penalty outbound links carry.
STORE_URL = os.environ.get('STORE_URL', 'https://girlstalk.justakemycard.com/')
# Up to 3 IG usernames (comma-separated). A collab Reel publishes to every collaborator's feed too.
INSTAGRAM_COLLABORATORS = os.environ.get('INSTAGRAM_COLLABORATORS', '')
# Cover frame as milliseconds into the video (e.g. "1000" picks the frame at 1.0s). Blank = default.
INSTAGRAM_THUMB_OFFSET_MS = os.environ.get('INSTAGRAM_THUMB_OFFSET_MS', '')
# Optional Facebook Page-backed location id to geotag the Reel (helps local/Explore surfacing).
INSTAGRAM_LOCATION_ID = os.environ.get('INSTAGRAM_LOCATION_ID', '')
# When true, keep the caption link-free and post the store link as the first comment instead.
INSTAGRAM_LINK_IN_COMMENT = os.environ.get('INSTAGRAM_LINK_IN_COMMENT', 'true').lower() == 'true'
# Optional: validate/prune hashtags via ig_hashtag_search (30 unique/week cap, so cached weekly).
INSTAGRAM_HASHTAG_SEARCH = os.environ.get('INSTAGRAM_HASHTAG_SEARCH', 'false').lower() == 'true'

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


# ----------------- DYNAMIC HASHTAGS -----------------
# PAST: a single hardcoded 11-tag block went out on every post.
# ISSUE: identical tags every time look spammy to the algorithm and never adapt to the topic,
#        so the post is not surfaced to the specific sub-audiences searching that theme.
# PRESENT: build a fresh, tiered mix per post (broad + mid-size + brand) PLUS topic tags derived
#          from THIS reel's section/title, shuffled so no two posts carry the same block.
# RATIONALE: mixing reach tiers and adding on-topic tags is the established discovery strategy;
#            doing it deterministically in code (no LLM) means zero hallucination and zero API cost.
# NOTE: these pools are deliberately FEMALE-CODED. We avoid gender-neutral/male-skewing tags
# (#mindset, #motivation, #success, #discipline, #selfimprovement) because they push the reel
# into mixed/male feeds. The goal is to bias Instagram toward surfacing this to women.
HASHTAGS_BROAD = [
    "#SelfCare", "#SelfLove", "#WomenSupportingWomen", "#GirlTalk", "#SoftGirlEra",
    "#FeminineEnergy", "#WomenEmpowerment", "#SelfWorth", "#ThatGirl",
]
HASHTAGS_MID = [
    "#EmotionalHealth", "#HealthyRelationships", "#PeoplePleaser", "#ReclaimYourPeace",
    "#HealingGirlEra", "#ToxicRelationships", "#SelfRespect", "#Sisterhood",
    "#HealingJourney", "#SoftLife", "#WomensWellness", "#DivineFeminine",
]
HASHTAGS_BRAND = [
    "#ProtectYourPeace", "#HeySis", "#SistersSupport", "#SayNoWithoutGuilt", "#MentalLoad",
]
# Keyword (lowercase substring of the section/title) -> extra on-topic tags.
HASHTAGS_TOPIC = {
    "money": ["#FinancialBoundaries", "#MoneyAndFriends"],
    "financ": ["#FinancialBoundaries", "#FinancialFreedomForWomen"],
    "gaslight": ["#Gaslighting", "#TrustYourself"],
    "guilt": ["#GuiltTrip", "#StopFeelingGuilty"],
    "love bomb": ["#LoveBombing", "#SlowDating"],
    "silent": ["#SilentTreatment", "#EmotionalNeglect"],
    "apolog": ["#StopApologizing", "#NoMoreSorry"],
    "sorry": ["#StopApologizing", "#NoMoreSorry"],
    "work": ["#WorkBoundaries", "#BurnoutRecovery"],
    "boss": ["#WorkBoundaries", "#CareerWomen"],
    "family": ["#FamilyBoundaries", "#ToxicFamily"],
    "in-law": ["#FamilyBoundaries", "#InLaws"],
    "text": ["#DigitalBoundaries", "#DatingAdvice"],
    "digital": ["#DigitalBoundaries", "#PrivacyMatters"],
    "privacy": ["#DigitalBoundaries", "#PrivacyMatters"],
    "backpack": ["#InvisibleLabor", "#EmotionalLabor"],
    "load": ["#InvisibleLabor", "#EmotionalLabor"],
    "no": ["#SayNo", "#BoundariesAreHealthy"],
}


def _extract_topic_text(md_path):
    """Pull the title + source-section line from the script md to derive topic tags."""
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        title = re.search(r'^#\s*(?:Ebook-Driven Marketing Script:\s*)?(.*)$', content, re.MULTILINE)
        # The real md line is "- **Ebook Source Section:** [Name](...)" — skip anything (incl. the
        # "** " bold markers) between the label and the bracketed section name.
        section = re.search(r'Ebook Source Section:[^\[]*\[(.*?)\]', content)
        return ((title.group(1) if title else "") + " " + (section.group(1) if section else "")).lower()
    except Exception:
        return ""


def _extract_script_hashtags(md_path):
    """Read the '## Hashtags' block the script generator wrote (tags derived from the actual script)."""
    try:
        with open(md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        m = re.search(r'##\s*Hashtags\s*\n(.*?)(?=\n\s*##|\Z)', content, re.DOTALL)
        if not m:
            return []
        # Keep only well-formed #tags (no spaces, alphanumeric/underscore).
        return re.findall(r'#\w+', m.group(1))
    except Exception:
        return []


def build_dynamic_hashtags(md_path):
    """
    Assemble the hashtag string for this reel.
    PRESENT: prefer the hashtags the LLM generated FROM this exact script (it knows the content),
             then guarantee the core brand tag and layer 2 broad reach tags. Fall back to the
             deterministic tiered+keyword mix only when the script provided none (older md).
    RATIONALE: script-derived tags are the most on-topic; brand + broad tiers protect reach and
               identity. No LLM call here and no hallucination risk — we only read what was written.
    """
    script_tags = _extract_script_hashtags(md_path)
    if script_tags:
        chosen = list(script_tags)
        if "#ProtectYourPeace" not in {t.lower() for t in chosen} and "#protectyourpeace" not in {t.lower() for t in chosen}:
            chosen.append("#ProtectYourPeace")
        for t in random.sample(HASHTAGS_BROAD, k=2):
            chosen.append(t)
        seen, deduped = set(), []
        for t in chosen:
            if t.lower() not in seen:
                seen.add(t.lower()); deduped.append(t)
        deduped = deduped[:20]
        if INSTAGRAM_HASHTAG_SEARCH:
            deduped = _validate_hashtags_via_search(deduped)
        return " ".join(deduped)

    # Fallback: deterministic tiered + section-keyword mix.
    topic_text = _extract_topic_text(md_path)

    topic_tags = []
    for keyword, tags in HASHTAGS_TOPIC.items():
        if keyword in topic_text:
            topic_tags.extend(tags)

    chosen = []
    chosen += random.sample(HASHTAGS_BROAD, k=min(3, len(HASHTAGS_BROAD)))
    chosen += random.sample(HASHTAGS_MID, k=min(4, len(HASHTAGS_MID)))
    chosen += random.sample(HASHTAGS_BRAND, k=min(2, len(HASHTAGS_BRAND)))
    # Always keep the core brand tag for consistency, then layer topic tags.
    if "#ProtectYourPeace" not in chosen:
        chosen.append("#ProtectYourPeace")
    # De-dupe topic tags against what we already have, then add up to 3.
    for t in topic_tags:
        if t not in chosen:
            chosen.append(t)

    # De-dupe (preserve order) and cap at 15 (clean, non-spammy).
    seen, deduped = set(), []
    for t in chosen:
        if t.lower() not in seen:
            seen.add(t.lower())
            deduped.append(t)
    deduped = deduped[:15]
    random.shuffle(deduped)

    if INSTAGRAM_HASHTAG_SEARCH:
        deduped = _validate_hashtags_via_search(deduped)

    return " ".join(deduped)


def _validate_hashtags_via_search(tags):
    """
    OPTIONAL: prune tags Instagram does not recognise, via ig_hashtag_search.
    The endpoint caps at 30 unique hashtag lookups per account per 7 days, so results are cached
    to disk and re-checked at most weekly, and we never exceed the weekly budget on a single run.
    Any failure returns the tags unchanged — this must never block a post.
    """
    if not (INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID):
        return tags
    cache_path = os.path.join(workspace, 'generated-audio', '.ig_hashtag_cache.json')
    now = time.time()
    week = 7 * 24 * 3600
    try:
        cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    except Exception:
        cache = {}

    lookups_this_week = sum(1 for v in cache.values() if now - v.get('ts', 0) < week)
    result = []
    for tag in tags:
        name = tag.lstrip('#').lower()
        entry = cache.get(name)
        fresh = entry and (now - entry.get('ts', 0) < week)
        if fresh:
            if entry.get('valid', True):
                result.append(tag)
            continue
        if lookups_this_week >= 28:  # stay safely under the 30/week cap
            result.append(tag)        # budget spent — keep the tag, validate it next week
            continue
        try:
            r = requests.get(
                f"https://graph.facebook.com/{INSTAGRAM_API_VERSION}/ig_hashtag_search",
                params={'user_id': INSTAGRAM_ACCOUNT_ID, 'q': name, 'access_token': INSTAGRAM_ACCESS_TOKEN},
                timeout=15,
            )
            valid = bool(r.json().get('data'))
            cache[name] = {'valid': valid, 'ts': now}
            lookups_this_week += 1
            if valid:
                result.append(tag)
        except Exception:
            result.append(tag)  # on any error, keep the tag
    try:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        json.dump(cache, open(cache_path, 'w'))
    except Exception:
        pass
    return result or tags


# ----------------- CAPTION GENERATION -----------------
def generate_female_targeted_caption(md_path, include_link=True, hashtags=None):
    """
    Parses the generated markdown script to extract the Hook and Core Value Point,
    and returns a clean, polished Instagram/Facebook/Threads caption targeted at a female audience.
    """
    # CTA line: with the raw store link, or link-free when the link goes in the first comment.
    cta_line = (
        f"👉 Hit Follow to join the sisterhood, and grab your Boundary Script Toolkit today at {STORE_URL} 🕊️"
        if include_link else
        "👉 Hit Follow to join the sisterhood — your Boundary Script Toolkit link is in the first comment 👇🕊️"
    )
    tags = hashtags or (
        "#MentalLoad #Boundaries #SelfCareForWomen #PeoplePleaser #ReclaimYourPeace "
        "#HeySis #WomenEmpowerment #MentalWellbeing #SayNoWithoutGuilt #SistersSupport #ProtectYourPeace"
    )

    if not os.path.exists(md_path):
        print(f"⚠️ Marketing script not found at {md_path}. Using a default caption.")
        return ("Hey sis, protecting your peace is not selfish—it is necessary. 💖\n\n"
                f"{cta_line}\n\n{tags}")

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
        # PAST: the first caption line was 'Hey sis, read this: "{hook}" 💖'.
        # ISSUE: the feed only shows the first ~1-2 lines before "... more"; a greeting
        #        ("Hey sis, read this:") burned that prime space and pushed the actual
        #        hook out of view — and the last 7 reels skipped 78-85% on weak openers.
        # PRESENT: lead with the raw hook itself; greeting removed.
        # RATIONALE: the hook is the scroll-stopper. Putting it in the first visible line
        #            mirrors the in-video hook and gives the caption the same job as the reel.
        if hook:
            caption_parts.append(f"\"{hook}\" 💖")
        else:
            caption_parts.append("Protecting your peace is not selfish — it is necessary. 💖")

        if lesson:
            caption_parts.append(lesson)

        # PRESENT: a save cue + a soft reply prompt before the CTA.
        # ISSUE: all 7 reels in the last batch got 0 comments and almost no saves because the
        #        caption never invited either; saves are the strongest buyer signal in this niche.
        # RATIONALE: one gentle, on-brand reply nudge (not "comment below" bait) + one save
        #            reason lifts the two engagement signals Instagram weights for distribution.
        caption_parts.append(
            "Save this for the next time the guilt creeps in. 🔖\n"
            "And tell me below — which one of you is this? 👇"
        )

        # Standard female-support Call to Action (link-aware)
        caption_parts.append(cta_line)

        # Per-post dynamic hashtags (passed in) or the default block
        caption_parts.append(tags)

        caption = "\n\n".join(caption_parts)
        return caption

    except Exception as e:
        print(f"⚠️ Error parsing markdown caption: {e}. Falling back to default.")
        return ("Hey sis, protecting your peace is not selfish—it is necessary. 💖\n\n"
                f"{cta_line}\n\n{tags}")


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
def post_instagram_comment(media_id, text):
    """Post a first comment on a published Reel (used to keep the store link out of the caption)."""
    try:
        url = f"https://graph.facebook.com/{INSTAGRAM_API_VERSION}/{media_id}/comments"
        res = requests.post(url, data={'message': text, 'access_token': INSTAGRAM_ACCESS_TOKEN}, timeout=30)
        if res.ok and 'id' in res.json():
            print(f"  💬 Posted link as the first comment.")
            return True
        print(f"  ⚠️ Could not post first comment: {res.json().get('error', {}).get('message', res.text)}")
    except Exception as e:
        print(f"  ⚠️ First-comment post failed: {e}")
    return False


def post_to_instagram_reel(video_path, caption, public_video_url, link_url=None):
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
            'share_to_feed': 'true',          # ensure the Reel also lands on the main feed/grid
            'access_token': INSTAGRAM_ACCESS_TOKEN
        }

        # Optional reach/discovery signals — only attached when configured in .env.
        collaborators = [u.strip() for u in INSTAGRAM_COLLABORATORS.split(',') if u.strip()][:3]
        if collaborators:
            container_payload['collaborators'] = json.dumps(collaborators)
            print(f"  🤝 Inviting collaborators: {', '.join(collaborators)}")
        if INSTAGRAM_THUMB_OFFSET_MS.strip().isdigit():
            container_payload['thumb_offset'] = INSTAGRAM_THUMB_OFFSET_MS.strip()
        if INSTAGRAM_LOCATION_ID.strip():
            container_payload['location_id'] = INSTAGRAM_LOCATION_ID.strip()

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
            # Keep the link out of the caption (reach) and drop it as the first comment instead.
            if INSTAGRAM_LINK_IN_COMMENT and link_url:
                post_instagram_comment(media_id, f"💖 Your Boundary Script Toolkit is here: {link_url}")
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

    # 2. Build per-post dynamic hashtags, then two caption variants:
    #    - Instagram: link-free (the store link goes in the first comment for better reach)
    #    - Facebook/Threads: link in caption (those platforms do not penalise outbound links)
    hashtags = build_dynamic_hashtags(SCRIPT_PATH)
    print(f"\n🏷️  Dynamic hashtags: {hashtags}")
    ig_link_free = INSTAGRAM_LINK_IN_COMMENT
    caption_ig = generate_female_targeted_caption(SCRIPT_PATH, include_link=not ig_link_free, hashtags=hashtags)
    caption_link = generate_female_targeted_caption(SCRIPT_PATH, include_link=True, hashtags=hashtags)
    print("\n📝 Generated Female-Targeted Caption (Instagram):")
    print("-" * 50)
    print(caption_ig)
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
    instagram_id = post_to_instagram_reel(VIDEO_PATH, caption_ig, public_video_url, link_url=STORE_URL)
    facebook_id = post_to_facebook_page(VIDEO_PATH, caption_link)
    threads_id = post_to_threads_profile(VIDEO_PATH, caption_link, public_video_url)

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

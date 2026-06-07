
import os
import sys
from dotenv import load_dotenv

# Load env before importing poster
load_dotenv()

from twitter_poster import post_to_twitter

def test_twitter_post():
    video_path = "instatest.mp4" # Reusing the test video
    
    if not os.path.exists(video_path):
        print(f"❌ Test video not found at {video_path}")
        return

    print("🎬 Starting Twitter test upload...")
    print("🐦 Sending request to Twitter (X)...")
    
    result = post_to_twitter(video_path, "Testing automatic video post to X! #Automation #Testing")
    
    if result['success']:
        print("✅ SUCCESS! Posted to Twitter.")
        print(f"   Tweet ID: {result['media_id']}")
        print(f"   Link: https://x.com/i/status/{result['media_id']}")
    else:
        print("❌ FAILED.")
        print(f"   Error: {result['error']}")

if __name__ == "__main__":
    # Check if credentials exist in env
    keys = ['TWITTER_API_KEY', 'TWITTER_API_SECRET', 'TWITTER_ACCESS_TOKEN', 'TWITTER_ACCESS_SECRET']
    missing = [k for k in keys if not os.environ.get(k)]
    
    if missing:
        print(f"⚠️ Missing environment variables: {', '.join(missing)}")
        print("Please configure them in your .env file first.")
    else:
        test_twitter_post()

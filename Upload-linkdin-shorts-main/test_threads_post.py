
import os
import sys
# Manually load .env BEFORE importing threads_poster
from dotenv import load_dotenv
load_dotenv()

# Debug: Print loaded vars (partially hidden)
token = os.environ.get('THREADS_ACCESS_TOKEN')
acct = os.environ.get('THREADS_ACCOUNT_ID')
print(f"Debug: Token loaded? {'Yes' if token else 'No'}")
print(f"Debug: Account ID loaded? {'Yes' if acct else 'No'}")

from threads_poster import post_to_threads

def test_single_post(video_path):
    print(f"🎬 Starting test upload to Threads for: {video_path}")
    
    if not os.path.exists(video_path):
        print(f"❌ Error: File not found at {video_path}")
        return

    # Post to Threads
    print("🧵 Posting to Threads...")
    # Using a simple test caption
    caption = "This is a test post from the API 🤖 #test #automation"
    
    try:
        # Pass variables directly if module logic is failing to pick them up
        result = post_to_threads(video_path, caption)
        
        if result['success']:
            print(f"✅ SUCCESS! Posted to Threads.")
            print(f"   Media ID: {result['media_id']}")
        else:
            print(f"❌ FAILED to post to Threads.")
            print(f"   Error: {result['error']}")
            
    except Exception as e:
        print(f"❌ Exception occurred: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Use the file mentioned by user
    video_file = "instatest.mp4"
    test_single_post(video_file)


import requests
import os
from dotenv import load_dotenv

load_dotenv()

# Configuration
APP_ID = "2669962123382032" # From your screenshot
SHORT_TOKEN = os.environ.get('THREADS_ACCESS_TOKEN')

def extend_threads_token(app_secret):
    print(f"🔄 Attempting to extend Threads token...")
    
    url = "https://graph.threads.net/access_token"
    params = {
        'grant_type': 'th_exchange_token',
        'client_secret': app_secret,
        'access_token': SHORT_TOKEN
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if 'access_token' in data:
            new_token = data['access_token']
            expires_in = data.get('expires_in', 0)
            days = expires_in / 86400
            
            print(f"\n✅ SUCCESS! New Long-Lived Token generated.")
            print(f"⏰ Valid for: {days:.1f} days")
            print(f"\n--- COPY THIS TOKEN INTO YOUR .env ---")
            print(new_token)
            print(f"----------------------------------------")
            
            return new_token
        else:
            print(f"❌ FAILED to extend token.")
            print(f"Error: {data.get('error', {}).get('message', 'Unknown error')}")
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
    
    return None

if __name__ == "__main__":
    secret = input("Please paste your App Secret here: ")
    extend_threads_token(secret.strip())

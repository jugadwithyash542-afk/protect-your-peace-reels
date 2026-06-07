
import os
import requests
from requests_oauthlib import OAuth1
from dotenv import load_dotenv

load_dotenv()

def debug_twitter_creds():
    api_key = os.environ.get('TWITTER_API_KEY')
    api_secret = os.environ.get('TWITTER_API_SECRET')
    access_token = os.environ.get('TWITTER_ACCESS_TOKEN')
    access_secret = os.environ.get('TWITTER_ACCESS_SECRET')
    
    print(f"Key: {api_key[:5]}...")
    print(f"Secret: {api_secret[:5]}...")
    print(f"Token: {access_token[:5]}...")
    print(f"Access Secret: {access_secret[:5]}...")

    auth = OAuth1(api_key, api_secret, access_token, access_secret)
    
    url = "https://api.twitter.com/2/users/me"
    resp = requests.get(url, auth=auth)
    
    print(f"\nStatus Code: {resp.status_code}")
    print(f"Response: {resp.text}")

if __name__ == "__main__":
    debug_twitter_creds()

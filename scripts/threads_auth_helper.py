#!/usr/bin/env python3
import os
import sys
import requests

def main():
    print("=" * 60)
    print("🧬 THREADS API AUTHENTICATION & SETUP HELPER")
    print("=" * 60)

    # 1. Determine workspace directory and .env path
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    workspace_dir = os.path.dirname(scripts_dir)
    env_path = os.path.join(workspace_dir, '.env')

    # 2. Check existing .env configuration
    existing_token = None
    existing_id = None
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line.startswith('THREADS_ACCESS_TOKEN='):
                    existing_token = line.split('=', 1)[1].strip()
                elif line.startswith('THREADS_ACCOUNT_ID='):
                    existing_id = line.split('=', 1)[1].strip()

    # If the token in .env is a placeholder, treat it as empty
    if existing_token and ('your_' in existing_token or existing_token == ''):
        existing_token = None
    if existing_id and ('your_' in existing_id or existing_id == ''):
        existing_id = None

    print(f"📁 .env File Detected: {env_path}")
    if existing_token:
        print("💡 Found an existing Threads Access Token in your .env file.")
        use_existing = input("Would you like to test and use this existing token? (y/n, default: y): ").strip().lower()
        if use_existing not in ('n', 'no'):
            token = existing_token
        else:
            token = input("\n🔑 Please enter your new Threads Access Token: ").strip()
    else:
        token = input("🔑 Please enter your Threads Access Token: ").strip()

    if not token:
        print("❌ Error: Access token cannot be empty.")
        sys.exit(1)

    # Clean token if copied with quotes
    token = token.strip('"\'')

    # 3. Test token against Threads Graph API
    print("\n🔍 Validating token and fetching profile info from Threads Graph API...")
    profile_url = "https://graph.threads.net/v1.0/me"
    params = {
        'fields': 'id,username,name',
        'access_token': token
    }

    try:
        res = requests.get(profile_url, params=params, timeout=15)
        if res.status_code == 200:
            profile_data = res.json()
            threads_id = profile_data.get('id')
            username = profile_data.get('username')
            name = profile_data.get('name', username)

            print("=" * 60)
            print("✅ SUCCESS! Successfully connected to your Threads profile:")
            print(f"   👤 Name:       {name}")
            print(f"   🏷️ Username:   @{username}")
            print(f"   🆔 Account ID: {threads_id}")
            print("=" * 60)
        else:
            print(f"\n❌ API request failed with status code: {res.status_code}")
            try:
                err = res.json().get('error', {})
                print(f"   Error Type:    {err.get('type')}")
                print(f"   Error Message: {err.get('message')}")
            except Exception:
                print(f"   Details: {res.text}")
            sys.exit(1)
    except Exception as e:
        print(f"\n❌ Network error while connecting to Threads: {e}")
        sys.exit(1)

    # 4. Ask to write/update .env file
    save_changes = input("\n💾 Do you want to save these credentials to your .env file? (y/n, default: y): ").strip().lower()
    if save_changes in ('n', 'no'):
        print("❌ Aborted. Credentials were not saved.")
        sys.exit(0)

    # Read all lines of the .env file
    lines = []
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

    # Track which fields we've successfully updated
    has_token_line = False
    has_id_line = False
    has_enabled_line = False

    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('THREADS_ACCESS_TOKEN='):
            new_lines.append(f"THREADS_ACCESS_TOKEN={token}\n")
            has_token_line = True
        elif stripped.startswith('THREADS_ACCOUNT_ID='):
            new_lines.append(f"THREADS_ACCOUNT_ID={threads_id}\n")
            has_id_line = True
        elif stripped.startswith('THREADS_ENABLED='):
            new_lines.append("THREADS_ENABLED=true\n")
            has_enabled_line = True
        else:
            new_lines.append(line)

    # Append fields if they weren't already present
    if not has_enabled_line or not has_token_line or not has_id_line:
        # Add a newline spacer if the file doesn't end with one
        if new_lines and not new_lines[-1].endswith('\n'):
            new_lines.append('\n')
        
        if not has_enabled_line:
            new_lines.append("THREADS_ENABLED=true\n")
        if not has_token_line:
            new_lines.append(f"THREADS_ACCESS_TOKEN={token}\n")
        if not has_id_line:
            new_lines.append(f"THREADS_ACCOUNT_ID={threads_id}\n")

    # Write changes back to .env
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print("\n🎉 Success! Your .env file has been updated with your Threads credentials.")
        print("   Make sure to check that THREADS_ENABLED=true is set to run uploads.")
    except Exception as e:
        print(f"\n❌ Failed to write to .env file: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()

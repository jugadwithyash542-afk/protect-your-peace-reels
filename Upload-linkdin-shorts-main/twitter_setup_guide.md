# Twitter (X) Setup Guide

To enable automatic posting to Twitter (X), you need to create a Developer App and obtain 4 specific keys.

## 1. Create a Developer Account
1.  Go to the [X Developer Portal](https://developer.x.com/).
2.  Sign in with your X account.
3.  If you don't have a developer account, you'll need to sign up for one (the **"Free"** tier is enough for posting).

## 2. Create an App
1.  Create a new project and a new App.
2.  Go to **"User authentication settings"** (inside your App settings).
3.  Click **"Edit"**.
4.  Switch **"OAuth 1.0a"** to **ON**.
5.  Set **"App permissions"** to **"Read and Write"** (CRITICAL).
6.  Set "Type of App" to "Web App, Android, iOS".
7.  Callback URL: `http://localhost` (not used by the bot, but required).
8.  Website URL: `http://localhost`.
9.  Click **"Save"**.

## 3. Get your Keys
1.  Go to the **"Keys and Tokens"** tab.
2.  **API Key & Secret**: Click "Regenerate" under "Consumer Keys" to get your `API Key` and `API Key Secret`.
3.  **Access Token & Secret**: Click "Create" or "Regenerate" under "Authentication Tokens" to get your `Access Token` and `Access Token Secret`.
4.  **IMPORTANT**: Make sure your Access Token has **"Created with Read and Write permissions"**.

## 4. Configure `.env`
Add these lines to your `.env` file:

```env
TWITTER_ENABLED=true
TWITTER_API_KEY=your_api_key_here
TWITTER_API_SECRET=your_api_secret_here
TWITTER_ACCESS_TOKEN=your_access_token_here
TWITTER_ACCESS_SECRET=your_access_secret_here
```

## 5. Verify
Once configured, you can test it by running the main app or a test script.
> [!NOTE]
> Twitter has a 280-character limit. The bot will automatically truncate longer descriptions.

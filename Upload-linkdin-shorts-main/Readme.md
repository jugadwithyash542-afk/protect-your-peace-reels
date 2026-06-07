# LinkedIn Video Automation

Flask app for automating LinkedIn video posts using Google Drive and Gemini AI.

## Deployed on Vercel

### Environment Variables Required

| Variable | Description |
|----------|-------------|
| `GEMINI_API_KEY` | Google Gemini API key |
| `LINKEDIN_ACCESS_TOKEN` | LinkedIn OAuth access token |
| `LINKEDIN_OWNER_URN` | LinkedIn user URN |
| `GOOGLE_DRIVE_FOLDER_ID` | Source folder for videos |
| `GOOGLE_CREDENTIALS_JSON` | Base64 encoded service account credentials |
| `AUTOPOST_API_KEY` | API key for authentication |
| `FLASK_SECRET_KEY` | Session secret key |

### Features

- Random video selection from Google Drive
- AI-generated descriptions via Gemini
- Automatic LinkedIn posting
- Manual accept/reject workflow
- Autopost API for scheduled posts

### Core Files

- `app.py` - Main Flask application
- `google_drive_helper.py` - Google Drive integration
- `device_manager.py` - Device whitelist management

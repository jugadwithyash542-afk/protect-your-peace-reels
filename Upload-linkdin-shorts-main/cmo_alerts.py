"""
CMO Alert Module
Sends alerts to CMO when auto-posting fails after all retries.
"""

import os
import requests
from typing import Optional, List, Dict
from dotenv import load_dotenv

load_dotenv()

# Configuration from environment
CMO_ALERT_EMAIL = os.environ.get('CMO_ALERT_EMAIL')
CMO_ALERT_WEBHOOK = os.environ.get('CMO_ALERT_WEBHOOK')
CMO_ALERT_ENABLED = os.environ.get('CMO_ALERT_ENABLED', 'true').lower() == 'true'
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY')
SENDGRID_FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL', 'noreply@memorystore.in')


class CMOAlertManager:
    """Manages sending alerts to CMO when auto-posting fails."""
    
    def __init__(self):
        self.email = CMO_ALERT_EMAIL
        self.webhook = CMO_ALERT_WEBHOOK
        self.enabled = CMO_ALERT_ENABLED
        self.sendgrid_key = SENDGRID_API_KEY
        self.from_email = SENDGRID_FROM_EMAIL
    
    def send_alert(
        self,
        error_message: str,
        video_id: Optional[str] = None,
        video_name: Optional[str] = None,
        platform: Optional[str] = None,
        retry_attempts: int = 3,
        timestamp: Optional[str] = None
    ) -> Dict[str, bool]:
        """
        Send alert to CMO about auto-posting failure.
        
        Args:
            error_message: Description of the error
            video_id: Google Drive video ID
            video_name: Name of the video file
            platform: Platform where posting failed (linkedin, instagram, etc.)
            retry_attempts: Number of retry attempts made
            timestamp: ISO timestamp of the failure
        
        Returns:
            Dict with success status for each alert channel
        """
        if not self.enabled:
            print("ℹ️  CMO alerts disabled")
            return {'email': False, 'webhook': False, 'enabled': False}
        
        import datetime
        if not timestamp:
            timestamp = datetime.datetime.utcnow().isoformat() + 'Z'
        
        results = {
            'email': False,
            'webhook': False,
            'enabled': True
        }
        
        # Send email alert
        if self.email and self.sendgrid_key:
            results['email'] = self._send_email_alert(
                error_message, video_id, video_name, platform, retry_attempts, timestamp
            )
        
        # Send webhook alert (e.g., to Slack, Teams, etc.)
        if self.webhook:
            results['webhook'] = self._send_webhook_alert(
                error_message, video_id, video_name, platform, retry_attempts, timestamp
            )
        
        # Fallback: print to console if no channels configured
        if not self.email and not self.webhook:
            print(f"🚨 CMO ALERT: Auto-posting failed")
            print(f"   Video: {video_name or video_id or 'Unknown'}")
            print(f"   Platform: {platform or 'Unknown'}")
            print(f"   Error: {error_message}")
            print(f"   Timestamp: {timestamp}")
            print(f"   Retry attempts: {retry_attempts}")
            results['console'] = True
        
        return results
    
    def _send_email_alert(
        self,
        error_message: str,
        video_id: Optional[str],
        video_name: Optional[str],
        platform: Optional[str],
        retry_attempts: int,
        timestamp: str
    ) -> bool:
        """Send email alert via SendGrid."""
        try:
            from_email = self.from_email or self.email
            subject = f"🚨 Auto-Posting Failed - {platform or 'Unknown Platform'}"
            
            body = f"""
<h2>Auto-Posting Failure Alert</h2>

<p><strong>Video:</strong> {video_name or video_id or 'Unknown'}</p>
<p><strong>Platform:</strong> {platform or 'Unknown'}</p>
<p><strong>Timestamp:</strong> {timestamp}</p>
<p><strong>Retry Attempts:</strong> {retry_attempts}</p>

<h3>Error Details:</h3>
<p>{error_message}</p>

<hr>
<p><em>This is an automated alert from the MemoryStore auto-posting system.</em></p>
            """.strip()
            
            if self.sendgrid_key:
                # Send via SendGrid
                headers = {
                    'Authorization': f'Bearer {self.sendgrid_key}',
                    'Content-Type': 'application/json'
                }
                
                payload = {
                    'personalizations': [{
                        'to': [{'email': self.email}],
                        'subject': subject
                    }],
                    'from': {'email': from_email},
                    'subject': subject,
                    'content': [{
                        'type': 'text/html',
                        'value': body
                    }]
                }
                
                response = requests.post(
                    'https://api.sendgrid.com/v3/mail/send',
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code in [200, 202]:
                    print(f"✅ CMO email alert sent to {self.email}")
                    return True
                else:
                    print(f"⚠️  SendGrid API error: {response.status_code} - {response.text}")
                    return False
            else:
                print("⚠️  SendGrid API key not configured")
                return False
                
        except Exception as e:
            print(f"⚠️  Failed to send CMO email alert: {str(e)}")
            return False
    
    def _send_webhook_alert(
        self,
        error_message: str,
        video_id: Optional[str],
        video_name: Optional[str],
        platform: Optional[str],
        retry_attempts: int,
        timestamp: str
    ) -> bool:
        """Send webhook alert (e.g., to Slack, Teams, Discord)."""
        try:
            # Detect webhook type and format accordingly
            if 'hooks.slack.com' in self.webhook:
                return self._send_slack_alert(
                    error_message, video_id, video_name, platform, retry_attempts, timestamp
                )
            elif 'discord.com' in self.webhook:
                return self._send_discord_alert(
                    error_message, video_id, video_name, platform, retry_attempts, timestamp
                )
            else:
                # Generic webhook
                return self._send_generic_webhook(
                    error_message, video_id, video_name, platform, retry_attempts, timestamp
                )
                
        except Exception as e:
            print(f"⚠️  Failed to send webhook alert: {str(e)}")
            return False
    
    def _send_slack_alert(
        self,
        error_message: str,
        video_id: Optional[str],
        video_name: Optional[str],
        platform: Optional[str],
        retry_attempts: int,
        timestamp: str
    ) -> bool:
        """Send alert to Slack."""
        payload = {
            'text': '🚨 Auto-Posting Failed',
            'attachments': [{
                'color': 'danger',
                'fields': [
                    {'title': 'Video', 'value': video_name or video_id or 'Unknown', 'short': True},
                    {'title': 'Platform', 'value': platform or 'Unknown', 'short': True},
                    {'title': 'Retry Attempts', 'value': str(retry_attempts), 'short': True},
                    {'title': 'Timestamp', 'value': timestamp, 'short': True},
                    {'title': 'Error', 'value': error_message, 'short': False}
                ]
            }]
        }
        
        response = requests.post(
            self.webhook,
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            print("✅ CMO Slack alert sent")
            return True
        else:
            print(f"⚠️  Slack webhook error: {response.status_code}")
            return False
    
    def _send_discord_alert(
        self,
        error_message: str,
        video_id: Optional[str],
        video_name: Optional[str],
        platform: Optional[str],
        retry_attempts: int,
        timestamp: str
    ) -> bool:
        """Send alert to Discord."""
        payload = {
            'embeds': [{
                'title': '🚨 Auto-Posting Failed',
                'color': 15158332,  # Red
                'fields': [
                    {'name': 'Video', 'value': video_name or video_id or 'Unknown', 'inline': True},
                    {'name': 'Platform', 'value': platform or 'Unknown', 'inline': True},
                    {'name': 'Retry Attempts', 'value': str(retry_attempts), 'inline': True},
                    {'name': 'Timestamp', 'value': timestamp, 'inline': True},
                    {'name': 'Error', 'value': error_message, 'inline': False}
                ],
                'timestamp': timestamp
            }]
        }
        
        response = requests.post(
            self.webhook,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 204]:
            print("✅ CMO Discord alert sent")
            return True
        else:
            print(f"⚠️  Discord webhook error: {response.status_code}")
            return False
    
    def _send_generic_webhook(
        self,
        error_message: str,
        video_id: Optional[str],
        video_name: Optional[str],
        platform: Optional[str],
        retry_attempts: int,
        timestamp: str
    ) -> bool:
        """Send generic webhook alert."""
        payload = {
            'alert_type': 'auto_posting_failure',
            'video_id': video_id,
            'video_name': video_name,
            'platform': platform,
            'error_message': error_message,
            'retry_attempts': retry_attempts,
            'timestamp': timestamp
        }
        
        response = requests.post(
            self.webhook,
            json=payload,
            timeout=30
        )
        
        if response.status_code in [200, 201, 202, 204]:
            print("✅ CMO webhook alert sent")
            return True
        else:
            print(f"⚠️  Generic webhook error: {response.status_code}")
            return False


# Global alert manager instance
cmo_alert_manager = CMOAlertManager()


def send_cmo_alert(
    error_message: str,
    video_id: Optional[str] = None,
    video_name: Optional[str] = None,
    platform: Optional[str] = None,
    retry_attempts: int = 3
) -> Dict[str, bool]:
    """
    Convenience function to send CMO alert.
    
    Args:
        error_message: Description of the error
        video_id: Google Drive video ID
        video_name: Name of the video file
        platform: Platform where posting failed
        retry_attempts: Number of retry attempts made
    
    Returns:
        Dict with success status for each alert channel
    """
    return cmo_alert_manager.send_alert(
        error_message=error_message,
        video_id=video_id,
        video_name=video_name,
        platform=platform,
        retry_attempts=retry_attempts
    )

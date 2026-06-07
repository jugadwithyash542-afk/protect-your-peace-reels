"""
Device Restriction Manager
Only allows whitelisted devices (your Mac and mobile) to access the app
"""

import hashlib
import json
import os
from datetime import datetime

class DeviceManager:
    def __init__(self, whitelist_file='device_whitelist.json'):
        self.whitelist_file = whitelist_file
        self.whitelist = self._load_whitelist()
    
    def _load_whitelist(self):
        """Load whitelisted devices from file or environment"""
        # Try environment variable first (for Vercel)
        env_whitelist = os.environ.get('DEVICE_WHITELIST')
        if env_whitelist:
            try:
                return json.loads(env_whitelist)
            except:
                pass
        
        # Try local file
        if os.path.exists(self.whitelist_file):
            try:
                with open(self.whitelist_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        
        # Default empty whitelist
        return {
            'devices': [],
            'created_at': datetime.now().isoformat()
        }
    
    def _save_whitelist(self):
        """Save whitelist to file (for local development)"""
        try:
            with open(self.whitelist_file, 'w') as f:
                json.dump(self.whitelist, f, indent=2)
            print(f"✓ Whitelist saved to {self.whitelist_file}")
            return True
        except Exception as e:
            print(f"⚠️  Could not save whitelist: {e}")
            return False
    
    def get_device_fingerprint(self, request):
        """
        Generate unique device fingerprint from request
        Combines multiple factors for better uniqueness
        """
        # Get User-Agent
        user_agent = request.headers.get('User-Agent', 'unknown')
        
        # Get IP address (fallback chain for different deployment scenarios)
        ip = (
            request.headers.get('X-Forwarded-For', '').split(',')[0].strip() or
            request.headers.get('X-Real-IP', '') or
            request.remote_addr or
            'unknown'
        )
        
        # Get Accept-Language for additional uniqueness
        accept_language = request.headers.get('Accept-Language', 'unknown')
        
        # Create fingerprint string
        fingerprint_data = f"{user_agent}|{accept_language}"
        
        # Hash it for privacy and consistency
        fingerprint_hash = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]
        
        return {
            'fingerprint': fingerprint_hash,
            'user_agent': user_agent,
            'ip': ip,
            'accept_language': accept_language
        }
    
    def get_device_info(self, request):
        """Get human-readable device information"""
        user_agent = request.headers.get('User-Agent', 'unknown')
        
        # Detect device type
        ua_lower = user_agent.lower()
        if 'macintosh' in ua_lower or 'mac os x' in ua_lower:
            device_type = 'Mac'
        elif 'iphone' in ua_lower:
            device_type = 'iPhone'
        elif 'ipad' in ua_lower:
            device_type = 'iPad'
        elif 'android' in ua_lower:
            device_type = 'Android'
        elif 'windows' in ua_lower:
            device_type = 'Windows'
        elif 'linux' in ua_lower:
            device_type = 'Linux'
        else:
            device_type = 'Unknown'
        
        # Detect browser
        if 'chrome' in ua_lower and 'edg' not in ua_lower:
            browser = 'Chrome'
        elif 'safari' in ua_lower and 'chrome' not in ua_lower:
            browser = 'Safari'
        elif 'firefox' in ua_lower:
            browser = 'Firefox'
        elif 'edg' in ua_lower:
            browser = 'Edge'
        else:
            browser = 'Unknown'
        
        return {
            'device_type': device_type,
            'browser': browser,
            'full_ua': user_agent
        }
    
    def is_device_allowed(self, request):
        """Check if device is in whitelist"""
        device_data = self.get_device_fingerprint(request)
        fingerprint = device_data['fingerprint']
        
        # Check if fingerprint is in whitelist
        for device in self.whitelist.get('devices', []):
            if device.get('fingerprint') == fingerprint:
                # Update last seen
                device['last_seen'] = datetime.now().isoformat()
                device['last_ip'] = device_data['ip']
                self._save_whitelist()
                return True, device
        
        return False, None
    
    def add_device(self, request, name=None):
        """Add current device to whitelist"""
        device_data = self.get_device_fingerprint(request)
        device_info = self.get_device_info(request)
        
        fingerprint = device_data['fingerprint']
        
        # Check if already exists
        for device in self.whitelist.get('devices', []):
            if device.get('fingerprint') == fingerprint:
                return False, "Device already whitelisted"
        
        # Add new device
        new_device = {
            'fingerprint': fingerprint,
            'name': name or f"{device_info['device_type']} - {device_info['browser']}",
            'device_type': device_info['device_type'],
            'browser': device_info['browser'],
            'user_agent': device_data['user_agent'],
            'added_at': datetime.now().isoformat(),
            'last_seen': datetime.now().isoformat(),
            'last_ip': device_data['ip']
        }
        
        self.whitelist['devices'].append(new_device)
        self._save_whitelist()
        
        return True, new_device
    
    def remove_device(self, fingerprint):
        """Remove device from whitelist"""
        original_count = len(self.whitelist.get('devices', []))
        self.whitelist['devices'] = [
            d for d in self.whitelist.get('devices', [])
            if d.get('fingerprint') != fingerprint
        ]
        
        if len(self.whitelist['devices']) < original_count:
            self._save_whitelist()
            return True
        return False
    
    def list_devices(self):
        """List all whitelisted devices"""
        return self.whitelist.get('devices', [])
    
    def get_whitelist_json(self):
        """Get whitelist as JSON string (for environment variable)"""
        return json.dumps(self.whitelist)

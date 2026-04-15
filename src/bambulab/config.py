"""
Configuration Manager
=====================

Loads authentication and configuration from common folder.
Provides centralized access to credentials for all services.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Tuple, Optional


class ConfigManager:
    """
    Manages configuration and credentials from common folder.
    
    Provides easy access to:
    - Bambu Lab credentials (account, password, token)
    - Google OAuth credentials
    - Email tokens
    - MQTT credentials
    """
    
    COMMON_DIR = Path(__file__).parent.parent.parent / "common"
    
    @classmethod
    def get_common_dir(cls) -> Path:
        """Get path to common directory"""
        return cls.COMMON_DIR
    
    @classmethod
    def _load_json(cls, filename: str) -> Dict[str, Any]:
        """Load JSON file from common directory"""
        filepath = cls.COMMON_DIR / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Config file not found: {filepath}")
        
        try:
            with open(filepath) as f:
                return json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {filename}: {e}")
        except Exception as e:
            raise RuntimeError(f"Error loading {filename}: {e}")
    
    @classmethod
    def _save_json(cls, filename: str, data: Dict[str, Any]) -> None:
        """Save JSON file to common directory"""
        filepath = cls.COMMON_DIR / filename
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            raise RuntimeError(f"Error saving {filename}: {e}")
    
    @classmethod
    def get_bambu_credentials(cls) -> Tuple[str, str]:
        """
        Get Bambu Lab credentials (email, password).
        
        Returns:
            Tuple of (email, password)
            
        Raises:
            FileNotFoundError: If bambu.json not found
            ValueError: If required fields missing
        """
        config = cls._load_json("bambu.json")
        
        email = config.get("account", "slugworks@ucsc.edu")
        password = config.get("bambu", "")
        
        if not password:
            raise ValueError("No password found in common/bambu.json")
        
        return email, password
    
    @classmethod
    def get_bambu_token(cls) -> Optional[str]:
        """Get saved Bambu Lab token from config"""
        try:
            config = cls._load_json("bambu.json")
            return config.get("token")
        except:
            return None
    
    @classmethod
    def save_bambu_token(cls, token: str) -> None:
        """Save Bambu Lab token to config"""
        config = cls._load_json("bambu.json")
        config["token"] = token
        cls._save_json("bambu.json", config)
    
    @classmethod
    def get_google_credentials_path(cls) -> Path:
        """Get path to Google credentials.json"""
        path = cls.COMMON_DIR / "credentials.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Google credentials not found at: {path}\n"
                "To setup Gmail integration:\n"
                "1. Create OAuth2 credentials in Google Cloud Console\n"
                "2. Download credentials.json\n"
                f"3. Place at: {path}"
            )
        return path
    
    @classmethod
    def get_gmail_token_path(cls) -> Path:
        """Get path to Gmail token storage"""
        return cls.COMMON_DIR / "emailtoken.json"
    
    @classmethod
    def get_mqtt_credentials(cls) -> Dict[str, str]:
        """
        Get MQTT credentials.
        
        Returns:
            Dictionary with mqtt username, password, and clientId
        """
        config = cls._load_json("bambu.json")
        
        # Try different field names
        mqtt = config.get("mqtt", {})
        if not mqtt:
            mqtt = {
                "username": config.get("mqttUsername", ""),
                "password": config.get("mqttPassword", ""),
                "clientId": config.get("mqttClientId", "")
            }
        
        return mqtt
    
    @classmethod
    def get_all_bambu_config(cls) -> Dict[str, Any]:
        """Get complete Bambu Lab configuration"""
        return cls._load_json("bambu.json")
    
    @classmethod
    def verify_gmail_setup(cls) -> bool:
        """
        Check if Gmail is properly set up.
        
        Returns:
            True if both credentials.json and emailtoken.json exist
        """
        creds_path = cls.COMMON_DIR / "credentials.json"
        token_path = cls.COMMON_DIR / "emailtoken.json"
        
        # At minimum, need credentials
        return creds_path.exists()
    
    @classmethod
    def verify_bambu_config(cls) -> bool:
        """
        Check if Bambu Lab config is properly set up.
        
        Returns:
            True if bambu.json has required fields
        """
        try:
            email, password = cls.get_bambu_credentials()
            return bool(email and password)
        except:
            return False


if __name__ == "__main__":
    # Test the configuration manager
    print("="*60)
    print("CONFIGURATION MANAGER TEST")
    print("="*60)
    
    print("\nCommon directory:", ConfigManager.get_common_dir())
    
    # Test Bambu credentials
    print("\n1. Bambu Lab Credentials:")
    try:
        email, password = ConfigManager.get_bambu_credentials()
        print(f"  Email: {email}")
        print(f"  Password: {'*' * len(password)}")
        print(f"  ✓ Valid")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test token
    print("\n2. Bambu Lab Token:")
    try:
        token = ConfigManager.get_bambu_token()
        if token:
            print(f"  Found: {token[:20]}...{token[-20:]}")
            print(f"  ✓ Valid")
        else:
            print("  Not set yet")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    # Test Gmail setup
    print("\n3. Gmail Setup:")
    try:
        creds_path = ConfigManager.get_google_credentials_path()
        print(f"  Credentials: {creds_path}")
        print(f"  ✓ Found")
    except Exception as e:
        print(f"  - Not configured (optional)")
    
    # Test MQTT
    print("\n4. MQTT Credentials:")
    try:
        mqtt = ConfigManager.get_mqtt_credentials()
        if mqtt.get("username"):
            print(f"  Username: {mqtt.get('username')}")
            print(f"  ✓ Configured")
        else:
            print("  Not configured")
    except Exception as e:
        print(f"  ✗ Error: {e}")
    
    print("\n" + "="*60)

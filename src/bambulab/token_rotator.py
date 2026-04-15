"""
Token Rotation Service
======================

Automatically rotates Bambu Lab API tokens every 30 days.

This service monitors token age and automatically logs in to retrieve
new tokens, using email-based verification code retrieval.
"""

import json
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Callable
from pathlib import Path

from .auth import BambuAuthenticator, BambuAuthError
from .email_code_retriever import EmailCodeRetriever


class TokenRotationService:
    """
    Manages automatic token rotation for Bambu Lab API.
    
    Features:
    - Monitors token age
    - Automatically retrieves new tokens every 30 days
    - Uses email verification code retrieval
    - Maintains token history
    - Configurable rotation intervals
    """
    
    DEFAULT_ROTATION_INTERVAL_DAYS = 30
    
    def __init__(
        self,
        username: str,
        password: str,
        region: str = "global",
        token_file: Optional[str] = None,
        rotation_interval_days: int = DEFAULT_ROTATION_INTERVAL_DAYS,
        credentials_file: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize token rotation service.
        
        Args:
            username: Bambu Lab account email
            password: Bambu Lab account password
            region: API region - "global" or "china" (default: "global")
            token_file: Path to token file (default: ~/.bambu_token)
            rotation_interval_days: Days between token rotations (default: 30)
            credentials_file: Path to Google credentials.json for email retrieval
            log_callback: Optional callback function for logging messages
            
        Example:
            >>> service = TokenRotationService(
            ...     username="user@email.com",
            ...     password="password",
            ...     rotation_interval_days=30
            ... )
            >>> service.check_and_rotate_if_needed()
        """
        self.username = username
        self.password = password
        self.region = region
        self.rotation_interval_days = rotation_interval_days
        self.log_callback = log_callback or self._default_log
        
        # Initialize authenticator
        self.authenticator = BambuAuthenticator(
            region=region,
            token_file=token_file
        )
        
        # Initialize email code retriever
        self.code_retriever = None
        try:
            self.code_retriever = EmailCodeRetriever(
                credentials_file=credentials_file
            )
            self.log("Email code retriever initialized successfully")
        except ImportError as e:
            self.log(f"Warning: Gmail libraries not installed: {e}")
            self.log("Install with: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client")
        except Exception as e:
            self.log(f"Warning: Email code retriever initialization failed: {e}")
            self.log("Token rotation will require manual code entry")
    
    def _default_log(self, message: str):
        """Default logging function"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] TokenRotation: {message}")
    
    def log(self, message: str):
        """Log a message"""
        self.log_callback(message)
    
    def get_token_age_info(self) -> dict:
        """
        Get information about current token age.
        
        Returns:
            Dictionary with:
            - has_token: Whether token exists
            - age_days: Age of token in days (or None)
            - created_time: When token was created (or None)
            - is_expired: Whether token is past rotation interval
            - days_until_rotation: Days until next rotation (or None)
        """
        token = self.authenticator.load_token()
        
        info = {
            'has_token': token is not None,
            'age_days': None,
            'created_time': None,
            'is_expired': False,
            'days_until_rotation': None
        }
        
        if not token:
            return info
        
        # Try to get token metadata
        try:
            token_file = self.authenticator.token_file
            if os.path.exists(token_file):
                creation_time = os.path.getctime(token_file)
                created_datetime = datetime.fromtimestamp(creation_time)
                age = datetime.now() - created_datetime
                
                info['created_time'] = created_datetime.isoformat()
                info['age_days'] = age.days
                info['is_expired'] = age.days >= self.rotation_interval_days
                info['days_until_rotation'] = self.rotation_interval_days - age.days
        
        except Exception as e:
            self.log(f"Error getting token age: {e}")
        
        return info
    
    def is_token_expired(self) -> bool:
        """
        Check if token needs rotation.
        
        Returns:
            True if token is past rotation interval or doesn't exist
        """
        info = self.get_token_age_info()
        return not info['has_token'] or info['is_expired']
    
    def rotate_token_auto(self) -> bool:
        """
        Rotate token automatically using email code retrieval.
        
        Attempts to get verification code from Gmail automatically.
        
        Returns:
            True if token was successfully rotated, False otherwise
        """
        if not self.code_retriever:
            self.log("Email code retriever not available for automatic rotation")
            return False
        
        def get_code_from_email():
            self.log("Waiting for verification code from email...")
            code = self.code_retriever.wait_for_code(timeout_seconds=600)
            if code:
                self.log(f"Code retrieved from email: {code}")
            return code
        
        return self.rotate_token(code_callback=get_code_from_email)
    
    def rotate_token(
        self,
        code_callback: Optional[Callable[[], str]] = None
    ) -> bool:
        """
        Rotate token by logging in again. Retries up to 3 times with 5-minute waits.
        On final failure, sends error email.
        
        Args:
            code_callback: Optional callback to get verification code
                          (if not provided, will prompt for input)
        
        Returns:
            True if rotation successful, False otherwise
        """
        self.log(f"Starting token rotation for: {self.username}")
        
        max_retries = 3
        retry_delay = 300  # 5 minutes in seconds
        
        for attempt in range(1, max_retries + 1):
            try:
                # Reset email code retriever for each attempt
                if self.code_retriever:
                    self.code_retriever.request_timestamp = None
                
                # Perform login to get new token
                token = self.authenticator.login(
                    username=self.username,
                    password=self.password,
                    code_callback=code_callback
                )
                
                self.log("✓ Token rotation successful!")
                self.log(f"  New token: {token[:20]}...{token[-20:]}")
                
                # Log token age info
                info = self.get_token_age_info()
                self.log(f"  Token status: {info}")
                
                return True
            
            except BambuAuthError as e:
                error_msg = f"Token rotation failed: {e}"
                self.log(f"✗ {error_msg} (Attempt {attempt}/{max_retries})")
                
                # If this was the last attempt, send error email
                if attempt == max_retries:
                    self._send_error_email(error_msg, attempt)
                    return False
                
                # Wait before retrying
                if attempt < max_retries:
                    self.log(f"Waiting 5 minutes before retry...")
                    time.sleep(retry_delay)
                    
            except Exception as e:
                error_msg = f"Unexpected error during rotation: {e}"
                self.log(f"✗ {error_msg} (Attempt {attempt}/{max_retries})")
                
                # If this was the last attempt, send error email
                if attempt == max_retries:
                    self._send_error_email(error_msg, attempt)
                    return False
                
                # Wait before retrying
                if attempt < max_retries:
                    self.log(f"Waiting 5 minutes before retry...")
                    time.sleep(retry_delay)
        
        return False
    
    def _send_error_email(self, error_msg: str, attempt: int) -> None:
        """
        Send error notification email using Gmail.
        
        Args:
            error_msg: Error message to include in email
            attempt: The attempt number that failed
        """
        try:
            # Import here to avoid circular imports
            from src.bambu_printers.gmail import gmail_send_message
            from src.config_manager import ConfigManager
            
            email_address = self.username  # Use the configured email
            
            subject = f"Bambu Lab Token Rotation Failed - {self.username}"
            body = f"""
Token rotation for {self.username} failed after {attempt} attempts.

Error Details:
{error_msg}

Please check the system and manually rotate the token if necessary.
You can run: python3 token_rotator_cli.py rotate --auto

Technical Details:
- Username: {self.username}
- Timestamp: {datetime.now().isoformat()}
- Attempts made: {attempt}

Token rotation is critical for maintaining API access. 
Please address this issue promptly.
"""
            
            gmail_send_message(
                recipient=email_address,
                sender=email_address,
                subject=subject,
                body=body,
                cc=None,
                reply_to=None
            )
            self.log(f"Error notification email sent to {email_address}")
            
        except Exception as e:
            self.log(f"Failed to send error email: {e}")
    
    def check_and_rotate_if_needed(self) -> bool:
        """
        Check if token needs rotation and rotate if necessary.
        
        Returns:
            True if token was rotated or didn't need rotation, False if rotation failed
            
        Example:
            >>> service = TokenRotationService("user@email.com", "password")
            >>> if service.check_and_rotate_if_needed():
            ...     print("Token is valid")
            ... else:
            ...     print("Token rotation failed")
        """
        info = self.get_token_age_info()
        
        self.log(f"Token status: {info}")
        
        if not info['has_token']:
            self.log("No token found, performing initial login...")
            return self.rotate_token_auto()
        
        if info['is_expired']:
            self.log(f"Token is {info['age_days']} days old (limit: {self.rotation_interval_days} days)")
            self.log("Token rotation needed!")
            return self.rotate_token_auto()
        else:
            days_left = info['days_until_rotation']
            self.log(f"Token is {info['age_days']} days old ({days_left} days remaining)")
            return True
    
    def rotate_token_with_refresh(self, refresh_token: str) -> bool:
        """
        Rotate token using refresh token (no email verification needed).
        
        This is the most reliable method as it doesn't require
        receiving a new verification code via email.
        
        Args:
            refresh_token: Valid refresh token from config
            
        Returns:
            True if successful, False otherwise
            
        Example:
            >>> from src.bambulab import ConfigManager
            >>> config = ConfigManager.get_all_bambu_config()
            >>> service.rotate_token_with_refresh(config['refreshToken'])
        """
        try:
            self.log("Rotating token using refresh token...")
            new_token = self.authenticator.refresh_token(refresh_token)
            
            if new_token:
                self.log("✓ Token rotated successfully via refresh!")
                self.log(f"  New token: {new_token[:20]}...{new_token[-20:]}")
                return True
            else:
                self.log("✗ Refresh returned empty token")
                return False
                
        except BambuAuthError as e:
            self.log(f"✗ Token refresh failed: {e}")
            return False
        except Exception as e:
            self.log(f"✗ Unexpected error during refresh: {e}")
            return False
    
    def force_rotate(self) -> bool:
        """
        Force token rotation regardless of age.
        
        Returns:
            True if rotation successful, False otherwise
        """
        self.log("Force rotating token...")
        return self.rotate_token_auto()


class TokenRotationScheduler:
    """
    Runs token rotation on a schedule using APScheduler.
    
    Requires: pip install apscheduler
    """
    
    def __init__(
        self,
        username: str,
        password: str,
        region: str = "global",
        token_file: Optional[str] = None,
        rotation_interval_days: int = TokenRotationService.DEFAULT_ROTATION_INTERVAL_DAYS,
        credentials_file: Optional[str] = None,
        log_callback: Optional[Callable[[str], None]] = None
    ):
        """
        Initialize token rotation scheduler.
        
        Args:
            username: Bambu Lab account email
            password: Bambu Lab account password
            region: API region
            token_file: Path to token file
            rotation_interval_days: Days between rotations
            credentials_file: Path to Google credentials
            log_callback: Optional logging callback
        """
        self.service = TokenRotationService(
            username=username,
            password=password,
            region=region,
            token_file=token_file,
            rotation_interval_days=rotation_interval_days,
            credentials_file=credentials_file,
            log_callback=log_callback
        )
        self.scheduler = None
        self.job = None
    
    def start(self, check_interval_hours: int = 1):
        """
        Start the token rotation scheduler.
        
        Args:
            check_interval_hours: How often to check for rotation (default: 1 hour)
            
        Returns:
            True if scheduler started, False if APScheduler not available
            
        Example:
            >>> scheduler = TokenRotationScheduler("user@email.com", "password")
            >>> scheduler.start(check_interval_hours=1)
            >>> # ... service runs in background ...
            >>> scheduler.stop()
        """
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError:
            self.service.log("APScheduler not installed. Install with: pip install apscheduler")
            return False
        
        self.scheduler = BackgroundScheduler()
        
        # Add job to check and rotate every check_interval_hours
        self.job = self.scheduler.add_job(
            self.service.check_and_rotate_if_needed,
            IntervalTrigger(hours=check_interval_hours),
            id='bambu_token_rotation',
            name='Bambu Lab Token Rotation',
            replace_existing=True
        )
        
        self.scheduler.start()
        self.service.log(f"Token rotation scheduler started (checking every {check_interval_hours} hours)")
        
        return True
    
    def stop(self):
        """Stop the token rotation scheduler"""
        if self.scheduler:
            self.scheduler.shutdown()
            self.service.log("Token rotation scheduler stopped")
    
    def get_status(self) -> dict:
        """
        Get scheduler status.
        
        Returns:
            Dictionary with scheduler information
        """
        if not self.scheduler:
            return {'running': False, 'message': 'Scheduler not started'}
        
        return {
            'running': self.scheduler.running,
            'job_count': len(self.scheduler.get_jobs()),
            'token_status': self.service.get_token_age_info()
        }


if __name__ == "__main__":
    # Example usage
    import sys
    from pathlib import Path
    
    # Get credentials from common/bambu.json
    try:
        config_file = Path(__file__).parent.parent.parent / "common" / "bambu.json"
        with open(config_file) as f:
            bambu_config = json.load(f)
            username = bambu_config.get("account", "slugworks@ucsc.edu")
            password = bambu_config.get("bambu", "")
    except Exception as e:
        print(f"Could not load Bambu credentials: {e}")
        sys.exit(1)
    
    if not password:
        print("No password found in common/bambu.json")
        sys.exit(1)
    
    # Create service with automatic email code retrieval
    service = TokenRotationService(
        username=username,
        password=password
    )
    
    # Check and rotate if needed
    service.check_and_rotate_if_needed()

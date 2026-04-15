"""
Email Code Retriever
====================

Retrieves verification codes from Gmail automatically for Bambu Lab authentication.

Requires: pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client
"""

import os
import re
import time
import base64
from typing import Optional

# Gmail imports are optional - only import when needed
try:
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    GMAIL_AVAILABLE = True
except ImportError:
    GMAIL_AVAILABLE = False


class EmailCodeRetriever:
    """
    Retrieves Bambu Lab verification codes from Gmail automatically.
    
    Searches recent emails for verification codes sent by Bambu Lab
    and extracts the numeric code.
    """
    
    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
    CREDENTIALS_FILE = None
    TOKEN_FILE = None
    
    def __init__(self, credentials_file: Optional[str] = None, token_file: Optional[str] = None):
        """
        Initialize email code retriever.
        
        Args:
            credentials_file: Path to Google credentials.json file
                            (default: common/credentials.json)
            token_file: Path to token storage file
                       (default: common/gmail_token.json)
        
        Raises:
            ImportError: If Gmail libraries are not installed
        """
        if not GMAIL_AVAILABLE:
            raise ImportError(
                "Gmail libraries not installed. Install with:\n"
                "  pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client"
            )
        if credentials_file is None:
            # Try to find credentials.json in common directory
            base_path = os.path.dirname(os.path.abspath(__file__))
            credentials_file = os.path.join(base_path, "..", "..", "common", "credentials.json")
        
        if token_file is None:
            # Try to find token.json in common directory
            base_path = os.path.dirname(os.path.abspath(__file__))
            token_file = os.path.join(base_path, "..", "..", "common", "gmail_token.json")
        
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = None
        self.creds = None
        self._authenticate()
    
    def _authenticate(self):
        """Authenticate with Gmail API"""
        # Load existing credentials if available
        if os.path.exists(self.token_file):
            self.creds = Credentials.from_authorized_user_file(self.token_file, self.SCOPES)
        
        # If no valid credentials, create new ones
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not os.path.exists(self.credentials_file):
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self.credentials_file}\n"
                        "Please place credentials.json in the common/ directory"
                    )
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES
                )
                self.creds = flow.run_local_server(port=0)
            
            # Save credentials for next time
            os.makedirs(os.path.dirname(self.token_file), exist_ok=True)
            with open(self.token_file, 'w') as token:
                token.write(self.creds.to_json())
        
        # Build Gmail service
        self.service = build("gmail", "v1", credentials=self.creds)
    
    def get_latest_verification_code(
        self,
        max_age_seconds: int = 300,
        max_attempts: int = 30,
        attempt_delay: int = 2
    ) -> Optional[str]:
        """
        Get latest verification code from Gmail.
        
        Searches for recent emails from Bambu Lab and extracts the verification code.
        Waits for email to arrive if not found immediately.
        
        Args:
            max_age_seconds: Maximum age of email in seconds (default: 300s = 5min)
            max_attempts: Maximum number of attempts to check for email (default: 30)
            attempt_delay: Seconds to wait between attempts (default: 2)
        
        Returns:
            6-digit verification code as string, or None if not found
            
        Example:
            >>> retriever = EmailCodeRetriever()
            >>> code = retriever.get_latest_verification_code()
            >>> print(f"Got code: {code}")
        """
        current_time = int(time.time())
        min_timestamp = current_time - max_age_seconds
        
        for attempt in range(max_attempts):
            try:
                # Search for recent emails from Bambu Lab
                # Look for verification code in subject or body
                query = (
                    'from:"noreply@bambulab.com" OR from:"bambu@bambulab.com" '
                    'subject:("verification" OR "code" OR "verify" OR "authenticate") '
                    f'newer_than:{max_age_seconds // 86400}d'
                )
                
                results = self.service.users().messages().list(
                    userId='me',
                    q=query,
                    maxResults=5
                ).execute()
                
                messages = results.get('messages', [])
                
                if not messages:
                    # Try without sender filter in case email comes from different address
                    query = (
                        'subject:("Bambu" OR "verification" OR "verify") '
                        'subject:("code" OR "verify" OR "authenticate")'
                    )
                    results = self.service.users().messages().list(
                        userId='me',
                        q=query,
                        maxResults=5
                    ).execute()
                    messages = results.get('messages', [])
                
                # Check messages from newest to oldest
                for msg in messages:
                    code = self._extract_code_from_message(msg['id'])
                    if code:
                        return code
                
                # If code not found and we have more attempts, wait and try again
                if attempt < max_attempts - 1:
                    print(f"Code not found yet, waiting {attempt_delay}s (attempt {attempt + 1}/{max_attempts})...")
                    time.sleep(attempt_delay)
            
            except Exception as e:
                print(f"Error searching for code: {e}")
                if attempt < max_attempts - 1:
                    time.sleep(attempt_delay)
        
        return None
    
    def _extract_code_from_message(self, message_id: str) -> Optional[str]:
        """
        Extract verification code from a Gmail message.
        
        Searches message body for numeric codes (usually 6 digits).
        
        Args:
            message_id: Gmail message ID
            
        Returns:
            6-digit code string, or None if not found
        """
        try:
            message = self.service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            # Get message body
            if 'parts' in message['payload']:
                parts = message['payload']['parts']
                body = ''
                for part in parts:
                    if part['mimeType'] == 'text/plain':
                        if 'data' in part['body']:
                            body = base64.urlsafe_b64decode(part['body']['data']).decode()
                        elif 'attachmentId' in part['body']:
                            # Handle attachments if needed
                            pass
            else:
                # Simple message without parts
                if 'data' in message['payload']['body']:
                    body = base64.urlsafe_b64decode(message['payload']['body']['data']).decode()
                else:
                    body = ''
            
            # Extract numeric codes (usually 6 digits)
            # Look for patterns like "123456" or "code: 123456"
            codes = re.findall(r'\b(\d{6})\b', body)
            
            if codes:
                # Return first (most likely) code
                return codes[0]
            
            # Try extracting any numeric sequence from body
            codes = re.findall(r'(?:code|verification|verify).*?(\d{4,8})', body, re.IGNORECASE)
            if codes:
                return str(codes[0])[-6:]  # Take last 6 digits
            
        except Exception as e:
            print(f"Error extracting code from message: {e}")
        
        return None
    
    def wait_for_code(
        self,
        timeout_seconds: int = 600,
        check_interval: int = 5
    ) -> Optional[str]:
        """
        Wait for verification code to arrive in email.
        
        Polls Gmail until code is found or timeout is reached.
        
        Args:
            timeout_seconds: Total time to wait in seconds (default: 600 = 10min)
            check_interval: Seconds between checks (default: 5)
            
        Returns:
            Verification code if found, None if timeout
            
        Example:
            >>> retriever = EmailCodeRetriever()
            >>> code = retriever.wait_for_code(timeout_seconds=600)
            >>> if code:
            ...     print(f"Got verification code: {code}")
        """
        max_attempts = timeout_seconds // check_interval
        return self.get_latest_verification_code(
            max_age_seconds=timeout_seconds,
            max_attempts=max_attempts,
            attempt_delay=check_interval
        )


if __name__ == "__main__":
    # Test the code retriever
    retriever = EmailCodeRetriever()
    print("Waiting for verification code from Bambu Lab...")
    code = retriever.wait_for_code(timeout_seconds=300)
    if code:
        print(f"✓ Found code: {code}")
    else:
        print("✗ No code found")

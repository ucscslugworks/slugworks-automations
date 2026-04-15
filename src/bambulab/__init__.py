"""
Bambu Lab Cloud API Library
=====================

A unified Python library for interacting with Bambu Lab 3D printers via Cloud API and MQTT.

Modules:
    client: HTTP API client for Bambu Lab Cloud API
    auth: Authentication and token management
    config: Configuration manager for common folder credentials
    email_code_retriever: Automatic verification code retrieval from Gmail
    token_rotator: Automatic token rotation service
    
Example usage:

    from bambulab import BambuClient, BambuAuthenticator, ConfigManager
    
    # Get credentials from common folder
    config = ConfigManager()
    email, password = config.get_bambu_credentials()
    
    # HTTP API
    client = BambuClient(token="your_token")
    devices = client.get_devices()
    
    # Authentication
    auth = BambuAuthenticator()
    token = auth.login(email, password)
    
    # Automatic token rotation
    from bambulab import TokenRotationService
    service = TokenRotationService(email, password)
    service.check_and_rotate_if_needed()

"""

__version__ = "1.0.0"
__author__ = "Coela (Bambu Lab)"

from .client import BambuClient, BambuAPIError
from .auth import TokenManager, BambuAuthenticator, BambuAuthError
from .config import ConfigManager
from .email_code_retriever import EmailCodeRetriever
from .token_rotator import TokenRotationService, TokenRotationScheduler

__all__ = [
    'BambuClient',
    'BambuAPIError',
    'TokenManager',
    'BambuAuthenticator',
    'BambuAuthError',
    'ConfigManager',
    'EmailCodeRetriever',
    'TokenRotationService',
    'TokenRotationScheduler',
]

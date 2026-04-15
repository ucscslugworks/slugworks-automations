#!/usr/bin/env python3
"""
Token Rotation CLI
==================

Command-line tool for managing automatic token rotation.

Usage:
    python token_rotator_cli.py status              # Show current token status
    python token_rotator_cli.py rotate              # Rotate token now
    python token_rotator_cli.py rotate --auto       # Auto-rotate with email code
    python token_rotator_cli.py scheduler start     # Start background scheduler
    python token_rotator_cli.py scheduler status    # Check scheduler status
"""

import argparse
import sys
import json
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bambulab import BambuAuthenticator, BambuAuthError
from bambulab.token_rotator import TokenRotationService, TokenRotationScheduler
from bambulab.email_code_retriever import EmailCodeRetriever


def load_config():
    """Load Bambu Lab configuration from common/bambu.json"""
    config_file = Path(__file__).parent / ".." / ".." / "common" / "bambu.json"
    if not config_file.exists():
        print(f"Error: Config file not found: {config_file}")
        sys.exit(1)
    
    try:
        with open(config_file) as f:
            config = json.load(f)
            return config
    except Exception as e:
        print(f"Error loading config: {e}")
        sys.exit(1)

def get_credentials():
    """Get Bambu Lab email and password from common/bambu.json"""
    config = load_config()
    # Get email - try 'account' field first, then fallback to default
    email = config.get("account", "slugworks@ucsc.edu")
    password = config.get("bambu", "")
    
    if not password:
        print("Error: No password found in common/bambu.json")
        sys.exit(1)
    
    return email, password


def cmd_status(args):
    """Show token status"""
    username, password = get_credentials()
    
    service = TokenRotationService(
        username=username,
        password=password
    )
    
    info = service.get_token_age_info()
    
    print("\n" + "=" * 60)
    print("BAMBU LAB TOKEN STATUS")
    print("=" * 60)
    print(f"Username: {username}")
    print(f"Has token: {'Yes' if info['has_token'] else 'No'}")
    
    if info['has_token']:
        print(f"Created: {info['created_time']}")
        print(f"Age: {info['age_days']} days")
        print(f"Rotation interval: {service.rotation_interval_days} days")
        print(f"Days until rotation: {info['days_until_rotation']}")
        print(f"Needs rotation: {'Yes ⚠️' if info['is_expired'] else 'No ✓'}")
    
    print("=" * 60 + "\n")


def cmd_rotate(args):
    """Rotate token"""
    username, password = get_credentials()
    
    service = TokenRotationService(
        username=username,
        password=password
    )
    
    print("\n" + "=" * 60)
    print("BAMBU LAB TOKEN ROTATION")
    print("=" * 60)
    
    if args.auto:
        print("Attempting automatic rotation with email code retrieval...")
        success = service.rotate_token_auto()
    else:
        print("Manual rotation - you will be prompted for verification code:")
        success = service.rotate_token(
            code_callback=lambda: input("\nEnter verification code from email: ")
        )
    
    print("=" * 60)
    if success:
        print("✓ Token rotation successful!")
        sys.exit(0)
    else:
        print("✗ Token rotation failed!")
        sys.exit(1)


def cmd_rotate_refresh(args):
    """Rotate token using refresh token (no email verification needed)"""
    config = load_config()
    refresh_token = config.get("refreshToken")
    
    if not refresh_token:
        print("\n✗ Error: No refresh token found in common/bambu.json")
        sys.exit(1)
    
    username, password = get_credentials()
    
    service = TokenRotationService(
        username=username,
        password=password
    )
    
    print("\n" + "=" * 60)
    print("BAMBU LAB TOKEN ROTATION (Refresh Method)")
    print("=" * 60)
    print(f"Using refresh token to get new access token...")
    
    success = service.rotate_token_with_refresh(refresh_token)
    
    print("=" * 60)
    if success:
        print("✓ Token rotation successful!")
        sys.exit(0)
    else:
        print("✗ Token rotation failed!")
        sys.exit(1)


def cmd_check(args):
    """Check and rotate if needed"""
    username, password = get_credentials()
    
    service = TokenRotationService(
        username=username,
        password=password
    )
    
    print("\n" + "=" * 60)
    print("CHECKING TOKEN...")
    print("=" * 60)
    
    success = service.check_and_rotate_if_needed()
    
    print("=" * 60)
    if success:
        print("✓ Token check passed!")
        sys.exit(0)
    else:
        print("✗ Token check failed!")
        sys.exit(1)


def cmd_scheduler_start(args):
    """Start background scheduler"""
    username, password = get_credentials()
    
    scheduler = TokenRotationScheduler(
        username=username,
        password=password
    )
    
    print("\n" + "=" * 60)
    print("STARTING TOKEN ROTATION SCHEDULER")
    print("=" * 60)
    
    check_interval = args.interval
    success = scheduler.start(check_interval_hours=check_interval)
    
    if success:
        print(f"✓ Scheduler started!")
        print(f"  Checking every {check_interval} hour(s)")
        print(f"  Rotation interval: {scheduler.service.rotation_interval_days} days")
        print("\nScheduler is running in background. Use Ctrl+C to stop.")
        print("=" * 60 + "\n")
        
        # Keep running
        try:
            import time
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopping scheduler...")
            scheduler.stop()
            print("✓ Scheduler stopped")
    else:
        print("✗ Failed to start scheduler!")
        sys.exit(1)


def cmd_scheduler_status(args):
    """Check scheduler status"""
    # Note: This only shows status if scheduler is running as subprocess
    print("\nTo check scheduler status, use:")
    print("  ps aux | grep token_rotator")
    print("\nFor persistent background service, use cron or systemd")


def cmd_test_email(args):
    """Test email code retrieval"""
    print("\n" + "=" * 60)
    print("TESTING EMAIL CODE RETRIEVAL")
    print("=" * 60)
    
    # Check if Gmail credentials exist
    creds_path = Path(__file__).parent.parent.parent / "common" / "credentials.json"
    if not creds_path.exists():
        print(f"\n✗ Google credentials not found at: {creds_path}")
        print("\nTo setup automatic email retrieval:")
        print("1. Create OAuth2 credentials in Google Cloud Console")
        print("2. Download credentials.json")
        print(f"3. Place at: {creds_path}")
        sys.exit(1)
    
    try:
        retriever = EmailCodeRetriever()
        print("✓ Email retriever initialized with common/credentials.json")
        print("\nWaiting for verification code (60 seconds)...")
        print("Please check your email for a Bambu Lab verification code...")
        
        code = retriever.wait_for_code(timeout_seconds=60, check_interval=2)
        
        if code:
            print(f"\n✓ Code retrieved: {code}")
            print(f"✓ Gmail token saved to: common/emailtoken.json")
        else:
            print("\n✗ No code found within timeout")
            sys.exit(1)
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)
    
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Bambu Lab Token Rotation Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show current token status
  python token_rotator_cli.py status
  
  # Rotate token now (manual verification code)
  python token_rotator_cli.py rotate
  
  # Rotate with automatic email code retrieval
  python token_rotator_cli.py rotate --auto
  
  # Check and rotate if needed
  python token_rotator_cli.py check
  
  # Start background scheduler
  python token_rotator_cli.py scheduler start --interval 1
  
  # Test email code retrieval
  python token_rotator_cli.py test-email
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Status command
    subparsers.add_parser('status', help='Show token status')
    
    # Rotate command
    rotate_parser = subparsers.add_parser('rotate', help='Rotate token')
    rotate_parser.add_argument(
        '--auto', '-a',
        action='store_true',
        help='Use automatic email code retrieval'
    )
    
    # Rotate with refresh command (new - preferred method)
    subparsers.add_parser(
        'rotate-refresh',
        help='Rotate token using refresh token (no email needed)'
    )
    
    # Check command
    subparsers.add_parser('check', help='Check and rotate if needed')
    
    # Scheduler commands
    scheduler_parser = subparsers.add_parser('scheduler', help='Manage scheduler')
    scheduler_subparsers = scheduler_parser.add_subparsers(dest='scheduler_cmd')
    
    start_parser = scheduler_subparsers.add_parser('start', help='Start scheduler')
    start_parser.add_argument(
        '--interval', '-i',
        type=int,
        default=1,
        help='Inactivity check interval in hours (default: 1)'
    )
    
    scheduler_subparsers.add_parser('status', help='Check scheduler status')
    
    # Test email command
    subparsers.add_parser(
        'test-email',
        help='Test email code retrieval'
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Route to appropriate command
    if args.command == 'status':
        cmd_status(args)
    elif args.command == 'rotate':
        cmd_rotate(args)
    elif args.command == 'rotate-refresh':
        cmd_rotate_refresh(args)
    elif args.command == 'check':
        cmd_check(args)
    elif args.command == 'scheduler':
        if args.scheduler_cmd == 'start':
            cmd_scheduler_start(args)
        elif args.scheduler_cmd == 'status':
            cmd_scheduler_status(args)
        else:
            scheduler_parser.print_help()
    elif args.command == 'test-email':
        cmd_test_email(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()

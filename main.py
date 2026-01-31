#!/usr/bin/env python3
"""
Kalshi Portfolio Tracker

A command-line tool to view your Kalshi portfolio value and positions.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from kalshi_client import KalshiClient
from portfolio_reporter import PortfolioReporter


def load_config() -> tuple[str, str, bool]:
    """
    Load configuration from environment variables or .env file.

    Returns:
        Tuple of (api_key_id, private_key_path, demo_mode)
    """
    load_dotenv()

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    demo_mode = os.getenv("KALSHI_DEMO_MODE", "false").lower() == "true"

    if not api_key_id:
        print("Error: KALSHI_API_KEY_ID environment variable not set")
        print("Set it in your .env file or export it in your shell")
        sys.exit(1)

    if not private_key_path:
        print("Error: KALSHI_PRIVATE_KEY_PATH environment variable not set")
        print("Set it in your .env file or export it in your shell")
        sys.exit(1)

    if not Path(private_key_path).exists():
        print(f"Error: Private key file not found: {private_key_path}")
        sys.exit(1)

    return api_key_id, private_key_path, demo_mode


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="View your Kalshi portfolio value and positions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                    # Show full portfolio report
  python main.py --balance-only     # Show only balance info
  python main.py --json             # Output as JSON
  python main.py --sheets           # Export to Google Sheets
  python main.py --demo             # Use demo API endpoint

Environment Variables:
  KALSHI_API_KEY_ID         Your Kalshi API key ID
  KALSHI_PRIVATE_KEY_PATH   Path to your RSA private key file
  KALSHI_DEMO_MODE          Set to 'true' to use demo API (optional)
        """,
    )

    parser.add_argument(
        "--balance-only",
        action="store_true",
        help="Only show balance information, skip positions",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output report as JSON",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Use demo API endpoint instead of production",
    )

    parser.add_argument(
        "--api-key",
        type=str,
        help="API key ID (overrides environment variable)",
    )

    parser.add_argument(
        "--private-key",
        type=str,
        help="Path to private key file (overrides environment variable)",
    )

    parser.add_argument(
        "--sheets",
        action="store_true",
        help="Export portfolio to Google Sheets",
    )

    parser.add_argument(
        "--spreadsheet-id",
        type=str,
        help="Existing Google Sheets spreadsheet ID to update (creates new if not provided)",
    )

    parser.add_argument(
        "--credentials",
        type=str,
        default="credentials.json",
        help="Path to Google OAuth credentials file (default: credentials.json)",
    )

    args = parser.parse_args()

    # Load config from environment
    env_api_key, env_private_key_path, env_demo_mode = load_config()

    # Allow command-line arguments to override
    api_key_id = args.api_key or env_api_key
    private_key_path = args.private_key or env_private_key_path
    demo_mode = args.demo or env_demo_mode

    try:
        # Initialize client
        client = KalshiClient(
            api_key_id=api_key_id,
            private_key_path=private_key_path,
            demo=demo_mode,
        )

        # Generate report
        reporter = PortfolioReporter(client)

        if args.sheets:
            from sheets_exporter import export_to_sheets

            print("Exporting to Google Sheets...")
            url = export_to_sheets(
                reporter,
                spreadsheet_id=args.spreadsheet_id,
                credentials_path=args.credentials,
            )
            print(f"Portfolio exported successfully!")
            print(f"View it here: {url}")
        elif args.json:
            report = reporter.generate_json_report()
            print(json.dumps(report, indent=2))
        else:
            report = reporter.generate_report(include_positions=not args.balance_only)
            print(report)

    except FileNotFoundError as e:
        print(f"Error: Could not find file - {e}")
        sys.exit(1)
    except PermissionError as e:
        print(f"Error: Permission denied - {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        if "401" in str(e):
            print("\nAuthentication failed. Please check:")
            print("  1. Your API key ID is correct")
            print("  2. Your private key file matches the public key registered with Kalshi")
            print("  3. Your system clock is accurate (timestamp verification)")
        elif "403" in str(e):
            print("\nAccess denied. Your API key may not have the required permissions.")
        sys.exit(1)


if __name__ == "__main__":
    main()

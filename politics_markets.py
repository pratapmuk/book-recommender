#!/usr/bin/env python3
"""
Politics Markets Exporter

Fetches all Politics category markets from Kalshi and exports them
to a Google Sheet with the highest probability choice for each.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from kalshi_client import KalshiClient

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def authenticate_sheets(credentials_path: str = "credentials.json", token_path: str = "token.json"):
    """Authenticate with Google Sheets API."""
    creds = None

    if Path(token_path).exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not Path(credentials_path).exists():
                raise FileNotFoundError(
                    f"Google credentials file not found: {credentials_path}"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_path, "w") as token:
            token.write(creds.to_json())

    return build("sheets", "v4", credentials=creds)


def fetch_markets(client: KalshiClient, limit: int = 100, min_liquidity: float = 50000) -> list[dict]:
    """
    Fetch open markets from Kalshi, excluding certain market types.

    Args:
        client: KalshiClient instance
        limit: Number of filtered markets to return
        min_liquidity: Minimum liquidity in dollars

    Returns:
        List of market dictionaries
    """
    print(f"  Fetching {limit} markets (liquidity > ${min_liquidity:,.0f}, excluding SPORTSMULTIGAMEEXTENDED)...")

    all_markets = []
    cursor = None
    page = 0

    while len(all_markets) < limit:
        page += 1
        result = client.get_markets(limit=100, cursor=cursor, status="open")
        markets = result.get("markets", [])

        if not markets:
            break

        for market in markets:
            if len(all_markets) >= limit:
                break

            event_ticker = market.get("event_ticker", "")
            ticker = market.get("ticker", "")
            title = market.get("title", "Unknown")

            # Skip multi-game extended sports markets
            if "SPORTSMULTIGAMEEXTENDED" in event_ticker or "SPORTSMULTIGAMEEXTENDED" in ticker:
                continue

            # Check liquidity (liquidity_dollars is a string like "50000.0000")
            liquidity_str = market.get("liquidity_dollars", "0")
            try:
                liquidity = float(liquidity_str)
            except (ValueError, TypeError):
                liquidity = 0

            if liquidity < min_liquidity:
                continue

            # Get the yes/no probabilities
            yes_price = market.get("yes_ask", 0) or market.get("last_price", 50)
            no_price = 100 - yes_price if yes_price else 50

            # Determine highest probability choice
            if yes_price >= no_price:
                best_choice = "YES"
                probability = yes_price
            else:
                best_choice = "NO"
                probability = no_price

            all_markets.append({
                "event_ticker": event_ticker,
                "title": title,
                "best_choice": best_choice,
                "probability": probability / 100,  # Convert to decimal
            })

        cursor = result.get("cursor")
        if not cursor:
            break

        print(f"    Page {page}: found {len(all_markets)} markets so far...")

    return all_markets


def export_to_sheets(
    markets: list[dict],
    spreadsheet_id: Optional[str] = None,
    credentials_path: str = "credentials.json",
) -> str:
    """
    Export markets to Google Sheets.

    Args:
        markets: List of market data dictionaries
        spreadsheet_id: Existing spreadsheet ID to append to, or None to create new
        credentials_path: Path to Google OAuth credentials

    Returns:
        URL to the spreadsheet
    """
    service = authenticate_sheets(credentials_path)

    # Create new spreadsheet if needed
    is_new = False
    if not spreadsheet_id:
        spreadsheet = {"properties": {"title": f"Kalshi Markets - {datetime.now().strftime('%Y-%m-%d')}"}}
        result = service.spreadsheets().create(body=spreadsheet, fields="spreadsheetId").execute()
        spreadsheet_id = result.get("spreadsheetId")
        is_new = True

    # Prepare the data rows (no header when appending)
    values = []

    for market in markets:
        values.append([
            market["event_ticker"],
            market["title"],
            market["best_choice"],
            market["probability"],
        ])

    body = {"values": values}

    if is_new:
        # Add header row for new sheet
        header = [["Event Ticker", "Market Name", "Best Choice", "Probability"]]
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            body={"values": header},
        ).execute()

        # Write data starting at row 2
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="A2",
            valueInputOption="RAW",
            body=body,
        ).execute()

        # Format the spreadsheet
        requests = [
            # Bold header row
            {
                "repeatCell": {
                    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                    "fields": "userEnteredFormat.textFormat",
                }
            },
            # Auto-resize columns
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": 0,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 4,
                    }
                }
            },
        ]

        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()
    else:
        # Append to existing sheet
        service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body=body,
        ).execute()

    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"


def main():
    """Main entry point."""
    load_dotenv()

    api_key_id = os.getenv("KALSHI_API_KEY_ID")
    private_key_path = os.getenv("KALSHI_PRIVATE_KEY_PATH")
    demo_mode = os.getenv("KALSHI_DEMO_MODE", "false").lower() == "true"

    if not api_key_id or not private_key_path:
        print("Error: KALSHI_API_KEY_ID and KALSHI_PRIVATE_KEY_PATH must be set in .env")
        sys.exit(1)

    try:
        # Initialize Kalshi client
        print("Connecting to Kalshi API...")
        client = KalshiClient(
            api_key_id=api_key_id,
            private_key_path=private_key_path,
            demo=demo_mode,
        )

        # Fetch markets
        print("Fetching markets...")
        markets = fetch_markets(client, limit=100, min_liquidity=50000)
        print(f"Found {len(markets)} markets")

        # Get spreadsheet ID from environment (to append to existing sheet)
        spreadsheet_id = os.getenv("KALSHI_MARKETS_SPREADSHEET_ID")

        # Export to Google Sheets
        if spreadsheet_id:
            print(f"Appending to existing Google Sheet...")
        else:
            print("Creating new Google Sheet...")

        url = export_to_sheets(markets, spreadsheet_id=spreadsheet_id)
        print(f"Exported successfully!")
        print(f"View it here: {url}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

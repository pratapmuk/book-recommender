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


def fetch_politics_markets(client: KalshiClient) -> list[dict]:
    """
    Fetch all open Politics markets from Kalshi.

    Returns:
        List of market dictionaries with name, best choice, and probability
    """
    all_markets = []
    cursor = None
    page = 0

    # Fetch all open markets (we'll filter for politics)
    while True:
        page += 1
        print(f"  Fetching page {page}...", end=" ", flush=True)

        result = client.get_markets(limit=100, cursor=cursor, status="open")
        markets = result.get("markets", [])

        politics_count = 0

        for market in markets:
            # Check if this is a politics market
            # Politics markets typically have category "Politics" or series starting with certain prefixes
            category = market.get("category", "")
            series_ticker = market.get("series_ticker", "")
            event_ticker = market.get("event_ticker", "")

            # Filter for politics-related markets
            is_politics = (
                "politic" in category.lower()
                or "election" in category.lower()
                or "congress" in category.lower()
                or "president" in category.lower()
                or "senate" in category.lower()
                or "house" in category.lower()
                or series_ticker.startswith("PRES")
                or series_ticker.startswith("SENATE")
                or series_ticker.startswith("HOUSE")
                or series_ticker.startswith("GOV")
                or "KXPOLITICS" in series_ticker.upper()
                or "KXPOLITICS" in event_ticker.upper()
            )

            if is_politics:
                politics_count += 1
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
                    "ticker": market.get("ticker", ""),
                    "title": market.get("title", "Unknown"),
                    "subtitle": market.get("subtitle", ""),
                    "best_choice": best_choice,
                    "probability": probability / 100,  # Convert to decimal
                    "yes_price": yes_price / 100,
                    "no_price": no_price / 100,
                })

        print(f"found {politics_count} politics markets")

        cursor = result.get("cursor")
        if not cursor or not markets:
            break

    return all_markets


def export_to_sheets(
    markets: list[dict],
    spreadsheet_id: Optional[str] = None,
    credentials_path: str = "credentials.json",
) -> str:
    """
    Export politics markets to Google Sheets.

    Args:
        markets: List of market data dictionaries
        spreadsheet_id: Existing spreadsheet ID, or None to create new
        credentials_path: Path to Google OAuth credentials

    Returns:
        URL to the spreadsheet
    """
    service = authenticate_sheets(credentials_path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Create new spreadsheet if needed
    if not spreadsheet_id:
        spreadsheet = {"properties": {"title": f"Kalshi Politics Markets - {datetime.now().strftime('%Y-%m-%d')}"}}
        result = service.spreadsheets().create(body=spreadsheet, fields="spreadsheetId").execute()
        spreadsheet_id = result.get("spreadsheetId")

    # Prepare the data rows
    values = []

    # Header row
    values.append(["Market Name", "Best Choice", "Probability", "Last Updated"])

    # Market rows
    for market in markets:
        title = market["title"]
        if market["subtitle"]:
            title = f"{title} - {market['subtitle']}"

        values.append([
            title,
            market["best_choice"],
            market["probability"],
            timestamp,
        ])

    # Write to sheet
    body = {"values": values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1",
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
        # Format probability column as percentage
        {
            "repeatCell": {
                "range": {"sheetId": 0, "startRowIndex": 1, "endRowIndex": len(values), "startColumnIndex": 2, "endColumnIndex": 3},
                "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0.0%"}}},
                "fields": "userEnteredFormat.numberFormat",
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests}
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

        # Fetch politics markets
        print("Fetching politics markets...")
        markets = fetch_politics_markets(client)
        print(f"Found {len(markets)} politics markets")

        if not markets:
            print("No politics markets found.")
            sys.exit(0)

        # Export to Google Sheets
        print("Exporting to Google Sheets...")
        url = export_to_sheets(markets)
        print(f"Exported successfully!")
        print(f"View it here: {url}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

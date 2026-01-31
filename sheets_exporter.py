"""
Google Sheets Exporter Module

Exports Kalshi portfolio data to a Google Sheets spreadsheet.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from portfolio_reporter import PortfolioReporter

# If modifying scopes, delete token.json
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsExporter:
    """Exports portfolio data to Google Sheets."""

    def __init__(
        self,
        credentials_path: str = "credentials.json",
        token_path: str = "token.json",
    ):
        """
        Initialize the exporter.

        Args:
            credentials_path: Path to Google OAuth credentials JSON file
            token_path: Path to store/load the user token
        """
        self.credentials_path = credentials_path
        self.token_path = token_path
        self.creds = None
        self.service = None

    def authenticate(self) -> None:
        """Authenticate with Google Sheets API."""
        # Load existing token if available
        if Path(self.token_path).exists():
            self.creds = Credentials.from_authorized_user_file(
                self.token_path, SCOPES
            )

        # Refresh or get new credentials if needed
        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not Path(self.credentials_path).exists():
                    raise FileNotFoundError(
                        f"Google credentials file not found: {self.credentials_path}\n"
                        "Download it from Google Cloud Console:\n"
                        "1. Go to https://console.cloud.google.com/apis/credentials\n"
                        "2. Create OAuth 2.0 Client ID (Desktop app)\n"
                        "3. Download JSON and save as 'credentials.json'"
                    )

                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, SCOPES
                )
                self.creds = flow.run_local_server(port=0)

            # Save credentials for next run
            with open(self.token_path, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("sheets", "v4", credentials=self.creds)

    def create_spreadsheet(self, title: str) -> str:
        """
        Create a new Google Sheets spreadsheet.

        Args:
            title: Title for the new spreadsheet

        Returns:
            Spreadsheet ID
        """
        spreadsheet = {"properties": {"title": title}}
        result = (
            self.service.spreadsheets()
            .create(body=spreadsheet, fields="spreadsheetId")
            .execute()
        )
        return result.get("spreadsheetId")

    def export_portfolio(
        self,
        reporter: PortfolioReporter,
        spreadsheet_id: Optional[str] = None,
        append: bool = False,
    ) -> str:
        """
        Export portfolio data to Google Sheets.

        Args:
            reporter: PortfolioReporter instance with data
            spreadsheet_id: Existing spreadsheet ID, or None to create new
            append: If True, append data below existing content

        Returns:
            URL to the spreadsheet
        """
        if not self.service:
            self.authenticate()

        # Get portfolio data
        data = reporter.generate_json_report()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Create new spreadsheet if needed
        if not spreadsheet_id:
            title = f"Kalshi Portfolio - {datetime.now().strftime('%Y-%m-%d')}"
            spreadsheet_id = self.create_spreadsheet(title)
            append = False  # New sheet, no need to append

        # Prepare the data rows
        values = []

        if append:
            # Add separator and timestamp for appended data
            values.append([])
            values.append(["---"])
            values.append([f"UPDATE: {timestamp}"])
        else:
            # Header section for new sheet
            values.append(["KALSHI PORTFOLIO REPORT"])
            values.append([f"Generated: {timestamp}"])
        values.append([])

        # Balance section
        values.append(["ACCOUNT BALANCE"])
        values.append(["Available Balance", f"${data['balance']['available_balance_dollars']:,.2f}"])
        values.append(["Portfolio Value", f"${data['balance']['portfolio_value_dollars']:,.2f}"])
        values.append(["Total Value", f"${data['balance']['total_value_dollars']:,.2f}"])
        values.append([])

        # Positions section
        values.append([f"OPEN POSITIONS ({data['position_count']})"])

        if data["positions"]:
            # Header row
            values.append(["Ticker", "Market", "Position", "Contracts", "Exposure", "Realized P&L"])

            # Position rows
            for pos in data["positions"]:
                pnl = pos["realized_pnl_dollars"]
                pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

                values.append([
                    pos["ticker"],
                    pos["market_title"],
                    pos["position_type"],
                    pos["contracts"],
                    f"${pos['market_exposure_dollars']:,.2f}",
                    pnl_str,
                ])
        else:
            values.append(["No open positions"])

        # Write to sheet
        body = {"values": values}

        if append:
            # Append below existing data
            self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
        else:
            # Overwrite from the beginning
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="A1",
                valueInputOption="RAW",
                body=body,
            ).execute()

            # Format the spreadsheet (only on new sheets)
            self._apply_formatting(spreadsheet_id, len(values))

        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    def _apply_formatting(self, spreadsheet_id: str, num_rows: int) -> None:
        """Apply basic formatting to the spreadsheet."""
        requests = [
            # Bold the title
            {
                "repeatCell": {
                    "range": {"sheetId": 0, "startRowIndex": 0, "endRowIndex": 1},
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True, "fontSize": 14}
                        }
                    },
                    "fields": "userEnteredFormat.textFormat",
                }
            },
            # Bold section headers
            {
                "repeatCell": {
                    "range": {"sheetId": 0, "startRowIndex": 3, "endRowIndex": 4},
                    "cell": {
                        "userEnteredFormat": {"textFormat": {"bold": True}}
                    },
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
                        "endIndex": 6,
                    }
                }
            },
        ]

        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id, body={"requests": requests}
        ).execute()


def export_to_sheets(
    reporter: PortfolioReporter,
    spreadsheet_id: Optional[str] = None,
    credentials_path: str = "credentials.json",
    append: bool = False,
) -> str:
    """
    Convenience function to export portfolio to Google Sheets.

    Args:
        reporter: PortfolioReporter instance
        spreadsheet_id: Existing spreadsheet ID, or None to create new
        credentials_path: Path to Google OAuth credentials
        append: If True, append data below existing content

    Returns:
        URL to the spreadsheet
    """
    exporter = SheetsExporter(credentials_path=credentials_path)
    exporter.authenticate()
    return exporter.export_portfolio(reporter, spreadsheet_id, append=append)

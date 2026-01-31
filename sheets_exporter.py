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

        # Calculate total exposure
        total_exposure = sum(pos["market_exposure_dollars"] for pos in data["positions"])

        # Create new spreadsheet if needed
        is_new_sheet = False
        if not spreadsheet_id:
            title = f"Kalshi Portfolio - {datetime.now().strftime('%Y-%m-%d')}"
            spreadsheet_id = self.create_spreadsheet(title)
            append = False  # New sheet, no need to append
            is_new_sheet = True

        # Prepare the data rows - only position rows
        values = []

        for pos in data["positions"]:
            pnl = pos["realized_pnl_dollars"]
            pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"

            values.append([
                pos["ticker"],
                pos["market_title"],
                pos["position_type"],
                pos["contracts"],
                pos["market_exposure_dollars"],
                pnl_str,
                timestamp,
            ])

        # Write to sheet
        body = {"values": values}

        if append:
            # Append below existing data
            self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
        else:
            # Overwrite from the beginning
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Sheet1!A1",
                valueInputOption="RAW",
                body=body,
            ).execute()

            # Format the spreadsheet (only on new sheets)
            self._apply_formatting(spreadsheet_id, len(values))

        # Update summary sheet with total exposure
        self._update_summary_sheet(spreadsheet_id, timestamp, total_exposure, is_new_sheet)

        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"

    def _get_or_create_summary_sheet(self, spreadsheet_id: str) -> int:
        """Get the Summary sheet ID, creating it if it doesn't exist."""
        # Get spreadsheet metadata
        spreadsheet = self.service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()

        # Check if Summary sheet exists
        for sheet in spreadsheet.get("sheets", []):
            if sheet["properties"]["title"] == "Summary":
                return sheet["properties"]["sheetId"]

        # Create Summary sheet
        requests = [{
            "addSheet": {
                "properties": {
                    "title": "Summary",
                    "index": 1,
                }
            }
        }]

        result = self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

        return result["replies"][0]["addSheet"]["properties"]["sheetId"]

    def _update_summary_sheet(
        self,
        spreadsheet_id: str,
        timestamp: str,
        total_exposure: float,
        is_new_sheet: bool,
    ) -> None:
        """Update the Summary sheet with total exposure data and chart."""
        summary_sheet_id = self._get_or_create_summary_sheet(spreadsheet_id)

        # Check if this is the first entry (need to add header)
        result = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range="Summary!A1:B1"
        ).execute()

        values = result.get("values", [])
        need_header = len(values) == 0

        # Prepare data to append
        rows_to_add = []
        if need_header:
            rows_to_add.append(["Timestamp", "Total Exposure"])

        rows_to_add.append([timestamp, total_exposure])

        # Append to Summary sheet
        self.service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range="Summary!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows_to_add},
        ).execute()

        # Create chart if this is a new sheet or first time adding summary
        if need_header:
            self._create_exposure_chart(spreadsheet_id, summary_sheet_id)

    def _create_exposure_chart(self, spreadsheet_id: str, sheet_id: int) -> None:
        """Create a line chart showing total exposure over time."""
        requests = [{
            "addChart": {
                "chart": {
                    "spec": {
                        "title": "Total Exposure Over Time",
                        "basicChart": {
                            "chartType": "LINE",
                            "legendPosition": "BOTTOM_LEGEND",
                            "axis": [
                                {
                                    "position": "BOTTOM_AXIS",
                                    "title": "Timestamp"
                                },
                                {
                                    "position": "LEFT_AXIS",
                                    "title": "Total Exposure ($)"
                                }
                            ],
                            "domains": [{
                                "domain": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": 1000,
                                            "startColumnIndex": 0,
                                            "endColumnIndex": 1,
                                        }]
                                    }
                                }
                            }],
                            "series": [{
                                "series": {
                                    "sourceRange": {
                                        "sources": [{
                                            "sheetId": sheet_id,
                                            "startRowIndex": 0,
                                            "endRowIndex": 1000,
                                            "startColumnIndex": 1,
                                            "endColumnIndex": 2,
                                        }]
                                    }
                                },
                                "targetAxis": "LEFT_AXIS",
                            }],
                            "headerCount": 1,
                        }
                    },
                    "position": {
                        "overlayPosition": {
                            "anchorCell": {
                                "sheetId": sheet_id,
                                "rowIndex": 1,
                                "columnIndex": 3,
                            },
                            "widthPixels": 600,
                            "heightPixels": 400,
                        }
                    }
                }
            }
        }]

        self.service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": requests}
        ).execute()

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
                        "endIndex": 7,
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

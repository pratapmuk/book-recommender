# Kalshi Portfolio Tracker

A command-line tool to view your Kalshi portfolio value and positions.

## Features

- View account balance (available funds + portfolio value)
- List all open positions with market details
- See realized P&L for each position
- Output as formatted text or JSON
- Support for both production and demo APIs

## Prerequisites

- Python 3.10+
- A Kalshi account with API access enabled
- An RSA key pair registered with Kalshi

## Installation

1. Clone the repository:
   ```bash
   git clone <repository-url>
   cd kalshi-portfolio-tracker
   ```

2. Create a virtual environment and install dependencies:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. Set up your credentials (see Configuration below)

## Configuration

### Generate an RSA Key Pair

If you don't already have an RSA key pair:

```bash
# Generate a private key
openssl genrsa -out kalshi_private_key.pem 4096

# Extract the public key
openssl rsa -in kalshi_private_key.pem -pubout -out kalshi_public_key.pem
```

### Register Your Public Key with Kalshi

1. Log into your Kalshi account
2. Go to Settings -> API
3. Create a new API key
4. Upload your public key (`kalshi_public_key.pem`)
5. Copy the API Key ID that Kalshi provides

### Set Up Environment Variables

Copy the example environment file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env` with your values:

```
KALSHI_API_KEY_ID=your-api-key-id-from-kalshi
KALSHI_PRIVATE_KEY_PATH=/path/to/kalshi_private_key.pem
KALSHI_DEMO_MODE=false
```

## Usage

### Basic Usage

View your full portfolio report:

```bash
python main.py
```

Example output:

```
============================================================
           KALSHI PORTFOLIO REPORT
============================================================

ACCOUNT BALANCE
----------------------------------------
Available Balance    $1,234.56
Portfolio Value      $567.89
Total Value          $1,802.45

OPEN POSITIONS (3)
----------------------------------------
Market                              Position    Exposure    Realized P&L
----------------------------------  ----------  ----------  --------------
Will BTC exceed $100k by Dec 2024?  10 YES      $450.00     +$50.00
Fed rate cut in January?            5 NO        $75.00      -$10.00
S&P 500 up 20% this year?           3 YES       $42.89      +$12.50

============================================================
```

### Command-Line Options

```bash
# Show only balance (skip positions)
python main.py --balance-only

# Output as JSON (useful for scripting)
python main.py --json

# Use demo API
python main.py --demo

# Override credentials via command line
python main.py --api-key YOUR_KEY_ID --private-key /path/to/key.pem
```

### JSON Output

The `--json` flag outputs machine-readable JSON:

```bash
python main.py --json
```

```json
{
  "balance": {
    "available_balance_cents": 123456,
    "available_balance_dollars": 1234.56,
    "portfolio_value_cents": 56789,
    "portfolio_value_dollars": 567.89,
    "total_value_cents": 180245,
    "total_value_dollars": 1802.45
  },
  "positions": [
    {
      "ticker": "BTC-100K-DEC24",
      "market_title": "Will BTC exceed $100k by Dec 2024?",
      "position": 10,
      "position_type": "YES",
      "contracts": 10,
      "market_exposure_cents": 45000,
      "market_exposure_dollars": 450.0,
      "realized_pnl_cents": 5000,
      "realized_pnl_dollars": 50.0
    }
  ],
  "position_count": 1
}
```

## Project Structure

```
.
├── main.py               # CLI entry point
├── kalshi_client.py      # Kalshi API client with RSA auth
├── portfolio_reporter.py # Portfolio data formatting
├── requirements.txt      # Python dependencies
├── .env.example          # Example environment configuration
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Security Notes

- **Never commit your private key** to version control
- **Never share your API Key ID** publicly
- The `.gitignore` is configured to exclude `.env`, `.pem`, and `.key` files
- Consider using a secrets manager for production deployments

## Troubleshooting

### Authentication Failed (401)

- Verify your API Key ID is correct
- Ensure your private key matches the public key registered with Kalshi
- Check that your system clock is accurate (timestamp verification is strict)

### Access Denied (403)

- Your API key may not have the required permissions
- Ensure you have Premier or Market Maker API access level

### Connection Errors

- Check your internet connection
- Verify you're using the correct API endpoint (demo vs production)

## License

MIT License

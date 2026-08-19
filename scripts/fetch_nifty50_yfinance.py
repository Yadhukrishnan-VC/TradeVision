#!/usr/bin/env python3
"""
Fetch NIFTY 50 daily OHLCV data via yfinance.

One-off script (not part of the Django app) that pulls daily OHLCV for all
current NIFTY 50 constituents (symbol + ".NS") for the last 3+ years, and writes
one CSV per symbol under a data/ directory with columns:
date, open, high, low, close, volume, symbol

The symbol column uses the bare NSE trading symbol (no suffix) to match how
Instrument stores it.

Logs any symbol that returns <90% expected trading days as a warning — doesn't
fail the batch, just flags for manual review.

Usage:
    python scripts/fetch_nifty50_yfinance.py --output-dir data/nifty50_daily --years 3
"""

from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("fetch_nifty50_yfinance")

# NIFTY 50 constituents as of 2024 (source: NSE India)
# These are the bare NSE trading symbols (no .NS suffix)
NIFTY_50_SYMBOLS = [
    "RELIANCE", "TCS", "HDFCBANK", "ICICIBANK", "INFY", "HINDUNILVR", "ITC",
    "SBIN", "BHARTIARTL", "KOTAKBANK", "LT", "AXISBANK", "BAJFINANCE", "ASIANPAINT",
    "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "NESTLEIND", "WIPRO", "ONGC",
    "POWERGRID", "NTPC", "COALINDIA", "TATAMOTORS", "ADANIENT", "ADANIPORTS",
    "JSWSTEEL", "HINDALCO", "TATASTEEL", "BAJAJFINSV", "TECHM", "GRASIM",
    "DRREDDY", "CIPLA", "DIVISLAB", "EICHERMOT", "HEROMOTOCO", "BAJAJ-AUTO",
    "BPCL", "TATACONSUM", "APOLLOHOSP", "INDUSINDBK", "SBILIFE", "HDFCLIFE",
    "BRITANNIA", "M&M", "UPL"
]

# Expected trading days per year for Indian markets (approximate)
EXPECTED_TRADING_DAYS_PER_YEAR = 245  # ~252 minus major holidays


def fetch_symbol_data(symbol: str, start_date: str, end_date: str) -> pd.DataFrame | None:
    """Fetch daily OHLCV data for a single symbol via yfinance.

    Args:
        symbol: Bare NSE trading symbol (e.g., "RELIANCE")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        DataFrame with columns: date, open, high, low, close, volume, symbol
        or None if fetch failed
    """
    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)

        if df.empty:
            logger.warning(f"[{symbol}] No data returned from yfinance")
            return None

        # Reset index to get date as column
        df = df.reset_index()

        # Select and rename columns
        df = df[["Date", "Open", "High", "Low", "Close", "Volume"]].copy()
        df.columns = ["date", "open", "high", "low", "close", "volume"]

        # Ensure date is string in YYYY-MM-DD format
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")

        # Add symbol column (bare NSE symbol)
        df["symbol"] = symbol

        # Sort by date
        df = df.sort_values("date").reset_index(drop=True)

        return df

    except Exception as exc:
        logger.error(f"[{symbol}] Fetch failed: {exc}")
        return None


def check_data_quality(symbol: str, df: pd.DataFrame, years: int) -> dict[str, Any]:
    """Check data quality and return metrics.

    Args:
        symbol: Trading symbol
        df: DataFrame with daily OHLCV data
        years: Number of years of data requested

    Returns:
        Dict with quality metrics
    """
    expected_days = EXPECTED_TRADING_DAYS_PER_YEAR * years
    actual_days = len(df)

    # Check for missing dates (gaps)
    dates = pd.to_datetime(df["date"])
    date_range = pd.date_range(start=dates.min(), end=dates.max(), freq="B")  # business days
    missing_dates = date_range.difference(dates)
    gap_count = len(missing_dates)

    # Check for zero volume days
    zero_volume_days = (df["volume"] == 0).sum()

    # Check for OHLC consistency (high >= low, high >= open/close, low <= open/close)
    ohlc_errors = 0
    for _, row in df.iterrows():
        if not (row["high"] >= row["low"] and
                row["high"] >= row["open"] and
                row["high"] >= row["close"] and
                row["low"] <= row["open"] and
                row["low"] <= row["close"]):
            ohlc_errors += 1

    coverage_pct = (actual_days / expected_days) * 100 if expected_days > 0 else 0

    return {
        "symbol": symbol,
        "expected_days": expected_days,
        "actual_days": actual_days,
        "coverage_pct": round(coverage_pct, 2),
        "gap_count": int(gap_count),
        "zero_volume_days": int(zero_volume_days),
        "ohlc_errors": ohlc_errors,
        "date_range": f"{dates.min().strftime('%Y-%m-%d')} to {dates.max().strftime('%Y-%m-%d')}",
        "is_sufficient": coverage_pct >= 90.0,
    }


def write_csv(df: pd.DataFrame, output_path: Path) -> None:
    """Write DataFrame to CSV with proper formatting."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False, quoting=csv.QUOTE_MINIMAL)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch NIFTY 50 daily OHLCV via yfinance")
    parser.add_argument(
        "--output-dir",
        default="data/nifty50_daily",
        help="Output directory for CSV files (default: data/nifty50_daily)",
    )
    parser.add_argument(
        "--years",
        type=int,
        default=3,
        help="Number of years of history to fetch (default: 3)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        help="Specific symbols to fetch (default: all NIFTY 50)",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=0.5,
        help="Delay between requests in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip symbols that already have CSV files",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Calculate date range
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=args.years * 365 + 30)).strftime("%Y-%m-%d")

    symbols = args.symbols if args.symbols else NIFTY_50_SYMBOLS
    logger.info(f"Fetching {len(symbols)} symbols for {args.years} years ({start_date} to {end_date})")
    logger.info(f"Output directory: {output_dir}")

    results = []
    warnings = []
    errors = []

    for i, symbol in enumerate(symbols, 1):
        csv_path = output_dir / f"{symbol}.csv"

        if args.skip_existing and csv_path.exists():
            logger.info(f"[{i}/{len(symbols)}] {symbol}: Skipping (already exists)")
            continue

        logger.info(f"[{i}/{len(symbols)}] {symbol}: Fetching...")

        df = fetch_symbol_data(symbol, start_date, end_date)

        if df is None:
            errors.append(symbol)
            logger.error(f"[{symbol}] Failed to fetch data")
            continue

        # Check data quality
        quality = check_data_quality(symbol, df, args.years)
        results.append(quality)

        if not quality["is_sufficient"]:
            warnings.append(
                f"[{symbol}] Low coverage: {quality['coverage_pct']}% "
                f"({quality['actual_days']}/{quality['expected_days']} days)"
            )
            logger.warning(warnings[-1])

        if quality["gap_count"] > 0:
            logger.info(f"[{symbol}] Found {quality['gap_count']} missing trading days (gaps)")

        if quality["zero_volume_days"] > 0:
            logger.warning(f"[{symbol}] {quality['zero_volume_days']} days with zero volume")

        if quality["ohlc_errors"] > 0:
            logger.warning(f"[{symbol}] {quality['ohlc_errors']} rows with OHLC inconsistencies")

        # Write CSV
        write_csv(df, csv_path)
        logger.info(f"[{symbol}] Saved {len(df)} rows to {csv_path}")

        # Rate limiting
        if i < len(symbols):
            time.sleep(args.rate_limit)

    # Summary
    logger.info("=" * 60)
    logger.info("FETCH SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Total symbols: {len(symbols)}")
    logger.info(f"Successful: {len(results)}")
    logger.info(f"Warnings (low coverage): {len(warnings)}")
    logger.info(f"Errors: {len(errors)}")

    if warnings:
        logger.info("\nWarnings:")
        for w in warnings:
            logger.info(f"  {w}")

    if errors:
        logger.info("\nErrors:")
        for e in errors:
            logger.info(f"  {e}")

    # Write quality report
    report_path = output_dir / "_quality_report.csv"
    if results:
        report_df = pd.DataFrame(results)
        report_df.to_csv(report_path, index=False)
        logger.info(f"\nQuality report saved to {report_path}")

    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
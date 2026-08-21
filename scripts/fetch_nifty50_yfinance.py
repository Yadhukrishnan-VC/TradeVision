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
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

# The NSE market calendar is a pure module (no Django settings required) living
# under backend/core. Make it importable when the script is run from repo root.
for _candidate in (Path(__file__).resolve().parent.parent / "backend",):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

from core.market_calendar import MarketCalendar, get_market_calendar  # noqa: E402

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


def fetch_symbol_data(symbol: str, start_date: str, end_date: str) -> tuple[pd.DataFrame | None, str | None]:
    """Fetch daily OHLCV data for a single symbol via yfinance.

    Args:
        symbol: Bare NSE trading symbol (e.g., "RELIANCE")
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        ``(DataFrame, None)`` with columns: date, open, high, low, close,
        volume, symbol — or ``(None, failure_reason)`` where ``failure_reason``
        is the EXACT exception type and message from yfinance (never a guess).
    """
    yf_symbol = f"{symbol}.NS"
    try:
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(start=start_date, end=end_date, interval="1d", auto_adjust=False)

        if df.empty:
            reason = (
                f"yfinance returned an empty frame for {yf_symbol} "
                "(no timezone found / possibly delisted / quote not found)"
            )
            logger.warning(f"[{symbol}] {reason}")
            return None, reason

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

        return df, None

    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        logger.error(f"[{symbol}] Fetch failed: {reason}")
        return None, reason


def expected_trading_days(from_date: str, to_date: str, calendar: MarketCalendar | None = None) -> int:
    """Count NSE trading days in ``[from_date, to_date]`` via MarketCalendar.

    Replaces the old flat ``EXPECTED_TRADING_DAYS_PER_YEAR * years`` estimate
    with the actual number of weekdays minus exchange holidays in the fetched
    date range, so ``coverage_pct`` and ``gap_count`` are mutually consistent.
    """
    calendar = calendar or get_market_calendar()
    start = date.fromisoformat(from_date)
    end = date.fromisoformat(to_date)
    count = 0
    cursor = start
    while cursor <= end:
        if calendar.is_trading_day(cursor):
            count += 1
        cursor += timedelta(days=1)
    return count


def check_data_quality(symbol: str, df: pd.DataFrame) -> dict[str, Any]:
    """Check data quality and return metrics.

    Args:
        symbol: Trading symbol
        df: DataFrame with daily OHLCV data

    Returns:
        Dict with quality metrics. ``expected_days`` is the actual number of
        NSE trading days in the fetched range; ``gap_count`` is
        ``expected_days - actual_days`` so the two are mutually consistent.
    """
    dates = pd.to_datetime(df["date"])
    first = dates.min().strftime("%Y-%m-%d")
    last = dates.max().strftime("%Y-%m-%d")
    expected_days = expected_trading_days(first, last)
    actual_days = len(df)

    gap_count = max(expected_days - actual_days, 0)

    # Check for zero volume days
    zero_volume_days = int((df["volume"] == 0).sum())

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
        "zero_volume_days": zero_volume_days,
        "ohlc_errors": ohlc_errors,
        "date_range": f"{first} to {last}",
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

        df, failure_reason = fetch_symbol_data(symbol, start_date, end_date)

        if df is None:
            errors.append({"symbol": symbol, "reason": failure_reason})
            logger.error(f"[{symbol}] Failed to fetch data: {failure_reason}")
            continue

        # Check data quality
        quality = check_data_quality(symbol, df)
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
        logger.info("\nErrors (exact reason):")
        for entry in errors:
            logger.info(f"  {entry['symbol']}: {entry['reason']}")

    # Write quality report
    report_path = output_dir / "_quality_report.csv"
    if results:
        report_df = pd.DataFrame(results)
        report_df.to_csv(report_path, index=False)
        logger.info(f"\nQuality report saved to {report_path}")

    # Write a machine-readable failures log with the exact exception details.
    if errors:
        failures_path = output_dir / "_fetch_failures.csv"
        pd.DataFrame(errors).to_csv(failures_path, index=False)
        logger.info(f"Fetch failures log saved to {failures_path}")

    return 0 if len(errors) == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
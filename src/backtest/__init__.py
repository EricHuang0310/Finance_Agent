"""
Backtesting module for the Multi-Agent Trading System.

Usage:
    python -m src.backtest.runner --start 2020-01-01 --end 2025-12-31 --capital 100000
"""

from src.backtest.runner import BacktestRunner
from src.backtest.report import BacktestReport
from src.backtest.client import BacktestClient
from src.backtest.data_loader import DataLoader

__all__ = ["BacktestRunner", "BacktestReport", "BacktestClient", "DataLoader"]

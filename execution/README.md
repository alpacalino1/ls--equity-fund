# Execution Layer - README

This directory contains the Layer 6 execution system components for Meridian Capital Partners.

## Components

1. `broker.py` - Alpaca API connection and portfolio sync
2. `executor.py` - Order execution logic with safety checks
3. `costs.py` - Slippage tracking and cost analysis
4. `short_check.py` - Short availability verification
5. `order_manager.py` - Order state tracking and lifecycle management
6. `run_execution.py` - Main entry point with CLI interface

## Safety Features

- Paper trading default (no real money risk)
- Pre-trade veto integration with Layer 5
- Short availability checking
- Liquidity-aware order sizing
- Timeout and retry handling
- Comprehensive logging
- SIGINT handling for safe shutdown

## Coming Soon

Implementation of all components according to PLAN.md
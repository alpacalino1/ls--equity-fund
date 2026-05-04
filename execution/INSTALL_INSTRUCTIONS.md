# Installation Instructions for Execution Layer

## Required Dependency

Add `alpaca-py>=0.25.0` to requirements.txt

## Installation Command

After updating requirements.txt, run:

```bash
cd /home/anto/ls_equity_fund
source .venv/bin/activate
pip install alpaca-py>=0.25.0
```

## Verification

Verify installation with:

```bash
python -c "import alpaca; print('Alpaca-py installed successfully')"
```

This will enable the Alpaca API integration for paper trading execution.
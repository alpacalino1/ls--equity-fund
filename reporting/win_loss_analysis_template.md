# Win/Loss Analysis Template

This is a template for the win_loss_analysis.py implementation that will handle comprehensive win/loss performance analysis.

## Planned Implementation

```python
"""
Meridian Capital Partners · reporting/win_loss_analysis.py
─────────────────────────────────────────────────────────────────
Win/loss analysis: win rate, P/L ratio, sliced by multiple dimensions.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger("meridian.reporting.win_loss_analysis")

class WinLossAnalysis:
    def __init__(self, config: Dict[str, Any] = None):
        """Initialize win/loss analysis engine."""
        if config is None:
            config = {}
            
        self.config = config
        self.holding_periods = config.get("holding_periods", [1, 5, 20, 60])
        self.vix_regimes = config.get("vix_regimes", [15, 20, 25, 30])
        self.output_dir = Path("output/reporting")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info("Win/loss analysis engine initialized")
        
    def analyze_win_loss(self, trades: List[Dict[str, Any]], 
                        market_data: pd.DataFrame,
                        factor_data: pd.DataFrame = None,
                        sector_data: pd.DataFrame = None) -> Dict[str, Any]:
        """
        Comprehensive win/loss analysis sliced by multiple dimensions.
        
        Dimensions:
        - Side (long/short)
        - Holding period buckets
        - Sector
        - VIX regime at entry
        - Factor quintile at entry
        - Winning/losing streaks
        """
        logger.info(f"Analyzing win/loss for {len(trades)} trades")
        
        # Convert trades to DataFrame for easier analysis
        trades_df = pd.DataFrame(trades)
        
        if trades_df.empty:
            return self._create_empty_analysis()
            
        # 1. Basic win rate and P/L ratio
        basic_stats = self._calculate_basic_stats(trades_df)
        
        # 2. Slice by side (long/short)
        side_analysis = self._analyze_by_side(trades_df)
        
        # 3. Slice by holding period
        holding_period_analysis = self._analyze_by_holding_period(trades_df)
        
        # 4. Slice by sector
        sector_analysis = self._analyze_by_sector(trades_df, sector_data)
        
        # 5. Slice by VIX regime
        vix_analysis = self._analyze_by_vix_regime(trades_df, market_data)
        
        # 6. Slice by factor quintile
        factor_analysis = self._analyze_by_factor_quintile(trades_df, factor_data)
        
        # 7. Streak analysis
        streak_analysis = self._analyze_streaks(trades_df)
        
        # Combine all results
        analysis_results = {
            'basic_stats': basic_stats,
            'by_side': side_analysis,
            'by_holding_period': holding_period_analysis,
            'by_sector': sector_analysis,
            'by_vix_regime': vix_analysis,
            'by_factor_quintile': factor_analysis,
            'streaks': streak_analysis,
            'total_trades': len(trades_df),
            'analysis_date': datetime.now().isoformat()
        }
        
        # Save results
        self._save_analysis(analysis_results)
        
        return analysis_results
        
    def _calculate_basic_stats(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Calculate basic win rate and P/L ratio statistics.
        """
        if trades_df.empty:
            return {}
            
        # Assuming trades_df has a 'return' or 'pnl' column
        wins = trades_df[trades_df['return'] > 0] if 'return' in trades_df.columns else pd.DataFrame()
        losses = trades_df[trades_df['return'] <= 0] if 'return' in trades_df.columns else pd.DataFrame()
        
        win_rate = len(wins) / len(trades_df) if len(trades_df) > 0 else 0
        
        # Calculate average win and average loss
        avg_win = wins['return'].mean() if not wins.empty else 0
        avg_loss = losses['return'].mean() if not losses.empty else 0
        
        # P/L ratio (absolute values)
        pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
        
        # Profit factor
        total_wins = wins['return'].sum() if not wins.empty else 0
        total_losses = abs(losses['return'].sum()) if not losses.empty else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        return {
            'win_rate': win_rate,
            'average_win': avg_win,
            'average_loss': avg_loss,
            'pl_ratio': pl_ratio,
            'profit_factor': profit_factor,
            'total_wins': len(wins),
            'total_losses': len(losses),
            'total_trades': len(trades_df)
        }
        
    def _analyze_by_side(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze win/loss by trade side (long vs short).
        """
        if trades_df.empty:
            return {}
            
        sides = trades_df['side'].unique() if 'side' in trades_df.columns else ['unknown']
        side_stats = {}
        
        for side in sides:
            side_trades = trades_df[trades_df['side'] == side]
            if side_trades.empty:
                side_stats[side] = {}
                continue
                
            wins = side_trades[side_trades['return'] > 0] if 'return' in side_trades.columns else pd.DataFrame()
            losses = side_trades[side_trades['return'] <= 0] if 'return' in side_trades.columns else pd.DataFrame()
            
            win_rate = len(wins) / len(side_trades) if len(side_trades) > 0 else 0
            avg_win = wins['return'].mean() if not wins.empty else 0
            avg_loss = losses['return'].mean() if not losses.empty else 0
            pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            side_stats[side] = {
                'win_rate': win_rate,
                'average_win': avg_win,
                'average_loss': avg_loss,
                'pl_ratio': pl_ratio,
                'total_trades': len(side_trades),
                'total_wins': len(wins),
                'total_losses': len(losses)
            }
            
        return side_stats
        
    def _analyze_by_holding_period(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze win/loss by holding period buckets.
        """
        if trades_df.empty or 'holding_days' not in trades_df.columns:
            return {}
            
        # Define holding period buckets
        buckets = [
            (1, 5, "1-5d"),
            (5, 20, "5-20d"), 
            (20, 60, "20-60d"),
            (60, float('inf'), "60d+")
        ]
        
        bucket_stats = {}
        
        for min_days, max_days, label in buckets:
            bucket_trades = trades_df[
                (trades_df['holding_days'] >= min_days) & 
                (trades_df['holding_days'] < max_days)
            ]
            
            if bucket_trades.empty:
                bucket_stats[label] = {}
                continue
                
            wins = bucket_trades[bucket_trades['return'] > 0] if 'return' in bucket_trades.columns else pd.DataFrame()
            losses = bucket_trades[bucket_trades['return'] <= 0] if 'return' in bucket_trades.columns else pd.DataFrame()
            
            win_rate = len(wins) / len(bucket_trades) if len(bucket_trades) > 0 else 0
            avg_win = wins['return'].mean() if not wins.empty else 0
            avg_loss = losses['return'].mean() if not losses.empty else 0
            pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            bucket_stats[label] = {
                'win_rate': win_rate,
                'average_win': avg_win,
                'average_loss': avg_loss,
                'pl_ratio': pl_ratio,
                'total_trades': len(bucket_trades),
                'total_wins': len(wins),
                'total_losses': len(losses)
            }
            
        return bucket_stats
        
    def _analyze_by_sector(self, trades_df: pd.DataFrame, 
                          sector_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze win/loss by sector.
        """
        if trades_df.empty or sector_data is None or sector_data.empty:
            return {}
            
        # Merge trades with sector data
        trades_with_sector = trades_df.merge(
            sector_data[['ticker', 'sector']], 
            on='ticker', 
            how='left'
        )
        
        sectors = trades_with_sector['sector'].unique()
        sector_stats = {}
        
        for sector in sectors:
            sector_trades = trades_with_sector[trades_with_sector['sector'] == sector]
            if sector_trades.empty:
                sector_stats[sector] = {}
                continue
                
            wins = sector_trades[sector_trades['return'] > 0] if 'return' in sector_trades.columns else pd.DataFrame()
            losses = sector_trades[sector_trades['return'] <= 0] if 'return' in sector_trades.columns else pd.DataFrame()
            
            win_rate = len(wins) / len(sector_trades) if len(sector_trades) > 0 else 0
            avg_win = wins['return'].mean() if not wins.empty else 0
            avg_loss = losses['return'].mean() if not losses.empty else 0
            pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else float('inf')
            
            sector_stats[sector] = {
                'win_rate': win_rate,
                'average_win': avg_win,
                'average_loss': avg_loss,
                'pl_ratio': pl_ratio,
                'total_trades': len(sector_trades),
                'total_wins': len(wins),
                'total_losses': len(losses)
            }
            
        return sector_stats
        
    def _analyze_by_vix_regime(self, trades_df: pd.DataFrame, 
                              market_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze win/loss by VIX regime at trade entry.
        """
        if trades_df.empty or market_data is None:
            return {}
            
        # Define VIX regimes
        vix_thresholds = self.vix_regimes
        regimes = []
        for i in range(len(vix_thresholds)):
            if i == len(vix_thresholds) - 1:
                regimes.append((vix_thresholds[i], float('inf'), f"{vix_thresholds[i]}+"))
            elif i == 0:
                regimes.append((0, vix_thresholds[i], f"<{vix_thresholds[i]}"))
            else:
                regimes.append((vix_thresholds[i-1], vix_thresholds[i], 
                               f"{vix_thresholds[i-1]}-{vix_thresholds[i]}"))
        
        regime_stats = {}
        
        # This would require VIX data aligned with trade entry dates
        # For now, return empty stats
        for _, _, label in regimes:
            regime_stats[label] = {}
            
        return regime_stats
        
    def _analyze_by_factor_quintile(self, trades_df: pd.DataFrame, 
                                   factor_data: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze win/loss by factor score quintile at entry.
        """
        if trades_df.empty or factor_data is None or factor_data.empty:
            return {}
            
        # This would involve:
        # 1. Get factor scores at trade entry dates
        # 2. Bucket into quintiles
        # 3. Calculate win/loss stats per quintile
        
        # For template, return basic structure
        quintiles = ['Q1', 'Q2', 'Q3', 'Q4', 'Q5']
        quintile_stats = {}
        
        for quintile in quintiles:
            quintile_stats[quintile] = {}  # Would populate with real data
            
        return quintile_stats
        
    def _analyze_streaks(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze winning and losing streaks.
        """
        if trades_df.empty or 'return' not in trades_df.columns:
            return {}
            
        # Sort by trade date
        trades_sorted = trades_df.sort_values('date') if 'date' in trades_df.columns else trades_df
        
        # Calculate win/loss sequence
        wins_losses = (trades_sorted['return'] > 0).astype(int)
        wins_losses = wins_losses.replace({1: 'W', 0: 'L'})
        
        # Calculate streaks
        streaks = []
        current_streak = {'type': None, 'length': 0}
        
        for result in wins_losses:
            if result == current_streak['type']:
                current_streak['length'] += 1
            else:
                if current_streak['type'] is not None:
                    streaks.append(current_streak)
                current_streak = {'type': result, 'length': 1}
                
        # Add final streak
        if current_streak['type'] is not None:
            streaks.append(current_streak)
            
        # Calculate streak statistics
        win_streaks = [s['length'] for s in streaks if s['type'] == 'W']
        loss_streaks = [s['length'] for s in streaks if s['type'] == 'L']
        
        return {
            'total_streaks': len(streaks),
            'max_win_streak': max(win_streaks) if win_streaks else 0,
            'max_loss_streak': max(loss_streaks) if loss_streaks else 0,
            'avg_win_streak': np.mean(win_streaks) if win_streaks else 0,
            'avg_loss_streak': np.mean(loss_streaks) if loss_streaks else 0,
            'current_streak': streaks[-1] if streaks else None,
            'win_streaks': win_streaks,
            'loss_streaks': loss_streaks
        }
        
    def _create_empty_analysis(self) -> Dict[str, Any]:
        """Create empty analysis structure."""
        return {
            'basic_stats': {},
            'by_side': {},
            'by_holding_period': {},
            'by_sector': {},
            'by_vix_regime': {},
            'by_factor_quintile': {},
            'streaks': {},
            'total_trades': 0,
            'analysis_date': datetime.now().isoformat()
        }
        
    def _save_analysis(self, analysis_results: Dict[str, Any]):
        """Save win/loss analysis results to file."""
        try:
            output_file = self.output_dir / "win_loss_analysis.json"
            with open(output_file, 'w') as f:
                json.dump(analysis_results, f, indent=2, default=str)
            logger.info(f"Win/loss analysis saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save win/loss analysis: {e}")
            
    def generate_win_loss_report(self, analysis_results: Dict[str, Any]) -> str:
        """
        Generate human-readable win/loss analysis report.
        """
        report_lines = [
            "MERIDIAN CAPITAL PARTNERS - WIN/LOSS ANALYSIS REPORT",
            "=" * 60,
            f"Generated: {analysis_results.get('analysis_date', 'N/A')}",
            f"Total Trades Analyzed: {analysis_results.get('total_trades', 0)}",
            ""
        ]
        
        # Basic Statistics
        basic_stats = analysis_results.get('basic_stats', {})
        if basic_stats:
            report_lines.extend([
                "OVERALL PERFORMANCE",
                "-" * 30,
                f"Win Rate: {basic_stats.get('win_rate', 0):.2%}",
                f"Avg Win: {basic_stats.get('average_win', 0):.2%}",
                f"Avg Loss: {basic_stats.get('average_loss', 0):.2%}",
                f"P/L Ratio: {basic_stats.get('pl_ratio', 0):.2f}",
                f"Profit Factor: {basic_stats.get('profit_factor', 0):.2f}",
                f"Wins: {basic_stats.get('total_wins', 0)}",
                f"Losses: {basic_stats.get('total_losses', 0)}",
                ""
            ])
            
        # Performance by Side
        side_analysis = analysis_results.get('by_side', {})
        if side_analysis:
            report_lines.extend([
                "PERFORMANCE BY SIDE",
                "-" * 30,
                "Side    Win Rate   Avg Win   Avg Loss   P/L Ratio   Trades",
                "-" * 60
            ])
            
            for side, stats in side_analysis.items():
                report_lines.append(
                    f"{side:<7} {stats.get('win_rate', 0):>8.2%} "
                    f"{stats.get('average_win', 0):>9.2%} {stats.get('average_loss', 0):>9.2%} "
                    f"{stats.get('pl_ratio', 0):>11.2f} {stats.get('total_trades', 0):>8}"
                )
            report_lines.append("")
            
        # Holding Period Analysis
        holding_analysis = analysis_results.get('by_holding_period', {})
        if holding_analysis:
            report_lines.extend([
                "PERFORMANCE BY HOLDING PERIOD",
                "-" * 30,
                "Period   Win Rate   Avg Win   Avg Loss   P/L Ratio   Trades",
                "-" * 60
            ])
            
            for period, stats in holding_analysis.items():
                report_lines.append(
                    f"{period:<8} {stats.get('win_rate', 0):>8.2%} "
                    f"{stats.get('average_win', 0):>9.2%} {stats.get('average_loss', 0):>9.2%} "
                    f"{stats.get('pl_ratio', 0):>11.2f} {stats.get('total_trades', 0):>8}"
                )
            report_lines.append("")
            
        # Streak Analysis
        streak_analysis = analysis_results.get('streaks', {})
        if streak_analysis:
            report_lines.extend([
                "STREAK ANALYSIS",
                "-" * 30,
                f"Max Win Streak: {streak_analysis.get('max_win_streak', 0)}",
                f"Max Loss Streak: {streak_analysis.get('max_loss_streak', 0)}",
                f"Avg Win Streak: {streak_analysis.get('avg_win_streak', 0):.2f}",
                f"Avg Loss Streak: {streak_analysis.get('avg_loss_streak', 0):.2f}",
                f"Current Streak: {streak_analysis.get('current_streak', {}).get('type', 'None')}"
                f" {streak_analysis.get('current_streak', {}).get('length', 0)}",
                ""
            ])
            
        return "\n".join(report_lines)

# Convenience function
def analyze_win_loss(trades: List[Dict[str, Any]], 
                     market_data: pd.DataFrame,
                     factor_data: pd.DataFrame = None,
                     sector_data: pd.DataFrame = None,
                     config: Dict[str, Any] = None) -> Dict[str, Any]:
    """Analyze win/loss performance comprehensively."""
    analyzer = WinLossAnalysis(config or {})
    return analyzer.analyze_win_loss(trades, market_data, factor_data, sector_data)
```

## Key Features to Implement

1. **Basic Performance Metrics**: Win rate, average win/loss, P/L ratio, profit factor
2. **Multi-Dimensional Analysis**: Slice by side, holding period, sector, VIX regime, factor quintile
3. **Streak Analysis**: Winning/losing streak identification and statistics
4. **Comprehensive Reporting**: Detailed performance breakdowns
5. **Configurable Buckets**: Customizable analysis periods and thresholds

## Integration Points

- Uses trade execution data from Layer 6
- Integrates factor scores from Layer 2
- Works with sector data for sector analysis
- Consumes market data for VIX regime analysis
- Feeds dashboard and tear sheet generators
- Supports portfolio performance evaluation
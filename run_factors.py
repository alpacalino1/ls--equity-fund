#!/usr/bin/env python3
"""
Meridian Capital Partners · run_factors.py
─────────────────────────────────────────────────────────────────
Layer 2 orchestrator — run this to score all 8 factors.
Usage: python run_factors.py [--factor momentum|value|quality|growth|revision|short_interest|insider|institutional|all]
"""

import argparse
import logging
import sys
import time
import pandas as pd
from pathlib import Path

import yaml
from dotenv import load_dotenv

from data.db import MeridianDB
from factors import momentum, value, quality, growth, revision, short_interest, insider, institutional

# ── Setup ───────────────────────────────────────────────────────────────

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("meridian.factors.main")


def load_config(path: str = "config.yaml") -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def get_universe(db: MeridianDB) -> pd.DataFrame:
    """Get universe DataFrame with ticker and sector info."""
    query = "SELECT ticker, gics_sector FROM universe"
    return pd.read_sql_query(query, db._connect())


def run_all_factors(universe_df: pd.DataFrame, config: dict, db: MeridianDB):
    """Run all 8 factor scorers sequentially."""
    t0 = time.time()
    
    # Dictionary to store all factor scores
    factor_scores = {}
    
    # 1. Momentum
    logger.info("═══ Factor 1/8: Momentum ═══")
    t_start = time.time()
    try:
        momentum_scores = momentum.score_momentum(universe_df, db)
        factor_scores['momentum'] = momentum_scores
        logger.info("Momentum scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Momentum scoring failed: %s", e)
        factor_scores['momentum'] = pd.DataFrame()
    
    # 2. Value
    logger.info("═══ Factor 2/8: Value ═══")
    t_start = time.time()
    try:
        value_scores = value.score_value(universe_df, db)
        factor_scores['value'] = value_scores
        logger.info("Value scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Value scoring failed: %s", e)
        factor_scores['value'] = pd.DataFrame()
    
    # 3. Quality
    logger.info("═══ Factor 3/8: Quality ═══")
    t_start = time.time()
    try:
        quality_scores = quality.score_quality(universe_df, db)
        factor_scores['quality'] = quality_scores
        logger.info("Quality scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Quality scoring failed: %s", e)
        factor_scores['quality'] = pd.DataFrame()
    
    # 4. Growth
    logger.info("═══ Factor 4/8: Growth ═══")
    t_start = time.time()
    try:
        growth_scores = growth.score_growth(universe_df, db)
        factor_scores['growth'] = growth_scores
        logger.info("Growth scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Growth scoring failed: %s", e)
        factor_scores['growth'] = pd.DataFrame()
    
    # 5. Revision
    logger.info("═══ Factor 5/8: Revision ═══")
    t_start = time.time()
    try:
        revision_scores = revision.score_revision(universe_df, db)
        factor_scores['revision'] = revision_scores
        logger.info("Revision scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Revision scoring failed: %s", e)
        factor_scores['revision'] = pd.DataFrame()
    
    # 6. Short Interest
    logger.info("═══ Factor 6/8: Short Interest ═══")
    t_start = time.time()
    try:
        short_scores = short_interest.score_short_interest(universe_df, db)
        factor_scores['short_interest'] = short_scores
        logger.info("Short interest scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Short interest scoring failed: %s", e)
        factor_scores['short_interest'] = pd.DataFrame()
    
    # 7. Insider
    logger.info("═══ Factor 7/8: Insider ═══")
    t_start = time.time()
    try:
        insider_scores = insider.score_insider(universe_df, db)
        factor_scores['insider'] = insider_scores
        logger.info("Insider scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Insider scoring failed: %s", e)
        factor_scores['insider'] = pd.DataFrame()
    
    # 8. Institutional
    logger.info("═══ Factor 8/8: Institutional ═══")
    t_start = time.time()
    try:
        institutional_scores = institutional.score_institutional(universe_df, db)
        factor_scores['institutional'] = institutional_scores
        logger.info("Institutional scoring completed in %.1f seconds", time.time() - t_start)
    except Exception as e:
        logger.error("Institutional scoring failed: %s", e)
        factor_scores['institutional'] = pd.DataFrame()
    
    # Combine all factor scores into a single composite score
    logger.info("═══ Combining all factors into composite score ═══")
    combined_scores = combine_factor_scores(factor_scores, config)
    
    # Save results
    output_dir = Path("output/factor_scores")
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save individual factor scores
    for factor_name, scores_df in factor_scores.items():
        if not scores_df.empty:
            scores_df.to_csv(output_dir / f"{factor_name}_scores.csv", index=False)
    
    # Save combined scores
    if not combined_scores.empty:
        combined_scores.to_csv(output_dir / "combined_scores.csv", index=False)
        logger.info("Combined scores saved to %s", output_dir / "combined_scores.csv")
    
    logger.info("═════════════════════════════════════════════════")
    logger.info("Layer 2 COMPLETE — total time: %.1f min", (time.time() - t0) / 60)
    return combined_scores


def combine_factor_scores(factor_scores: dict, config: dict) -> pd.DataFrame:
    """
    Combine individual factor scores into a single composite score.
    Uses weights from config.yaml.
    """
    if not factor_scores:
        return pd.DataFrame()
    
    # Get list of all tickers that have at least one factor score
    all_tickers = set()
    for scores_df in factor_scores.values():
        if not scores_df.empty and 'ticker' in scores_df.columns:
            all_tickers.update(scores_df['ticker'].tolist())
    
    if not all_tickers:
        return pd.DataFrame()
    
    # Initialize result DataFrame
    result_df = pd.DataFrame({'ticker': list(all_tickers)})
    
    # Add sector information
    # For simplicity, we'll assume we can get sector from any factor score that has it
    sector_info = {}
    for scores_df in factor_scores.values():
        if not scores_df.empty and 'sector' in scores_df.columns:
            for _, row in scores_df.iterrows():
                if row['ticker'] not in sector_info and 'sector' in row:
                    sector_info[row['ticker']] = row['sector']
    
    result_df['sector'] = result_df['ticker'].map(sector_info)
    
    # Get factor weights from config
    factor_weights = config.get('factors', {}).get('weights', {})
    
    # Add individual factor composite scores to result
    for factor_name, scores_df in factor_scores.items():
        if not scores_df.empty and 'composite_score' in scores_df.columns:
            score_map = dict(zip(scores_df['ticker'], scores_df['composite_score']))
            result_df[f'{factor_name}_score'] = result_df['ticker'].map(score_map).fillna(0)
    
    # Calculate final composite score
    weighted_sum = pd.Series(0.0, index=result_df.index)
    total_weight = 0.0
    
    factor_columns = [col for col in result_df.columns if col.endswith('_score') and col != 'composite_score']
    
    for factor_col in factor_columns:
        factor_name = factor_col.replace('_score', '')
        weight = factor_weights.get(factor_name, 0)
        if weight > 0:
            weighted_sum += result_df[factor_col] * weight
            total_weight += weight
    
    # Normalize by total weight
    if total_weight > 0:
        result_df['composite_score'] = weighted_sum / total_weight
    else:
        # Equal weights if no valid weights found
        result_df['composite_score'] = result_df[factor_columns].mean(axis=1, skipna=True)
    
    return result_df


def main():
    parser = argparse.ArgumentParser(description="Meridian Capital Partners — Layer 2 Factor Scoring")
    parser.add_argument("--factor", default="all",
                        choices=["momentum", "value", "quality", "growth", "revision", 
                                "short_interest", "insider", "institutional", "all"],
                        help="Which factor to score (default: all)")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    args = parser.parse_args()

    config = load_config(args.config)
    db = MeridianDB(config.get("db_path", "cache/meridian.db"))
    
    # Get universe
    logger.info("Loading universe...")
    universe_df = get_universe(db)
    logger.info("Universe loaded: %d stocks", len(universe_df))

    # Run specific factor or all
    factor_functions = {
        "momentum": lambda: momentum.score_momentum(universe_df, db),
        "value": lambda: value.score_value(universe_df, db),
        "quality": lambda: quality.score_quality(universe_df, db),
        "growth": lambda: growth.score_growth(universe_df, db),
        "revision": lambda: revision.score_revision(universe_df, db),
        "short_interest": lambda: short_interest.score_short_interest(universe_df, db),
        "insider": lambda: insider.score_insider(universe_df, db),
        "institutional": lambda: institutional.score_institutional(universe_df, db),
    }

    if args.factor == "all":
        combined_scores = run_all_factors(universe_df, config, db)
        print(f"\nComposite scores calculated for {len(combined_scores)} stocks")
        if not combined_scores.empty:
            top_10 = combined_scores.nlargest(10, 'composite_score')[['ticker', 'composite_score']]
            print("\nTop 10 stocks by composite score:")
            print(top_10.to_string(index=False))
    else:
        logger.info(f"Scoring factor: {args.factor}")
        scores = factor_functions[args.factor]()
        print(f"\n{args.factor.capitalize()} scores calculated for {len(scores)} stocks")
        if not scores.empty:
            top_10 = scores.nlargest(10, 'composite_score')[['ticker', 'composite_score']]
            print(f"\nTop 10 stocks by {args.factor} score:")
            print(top_10.to_string(index=False))


if __name__ == "__main__":
    main()

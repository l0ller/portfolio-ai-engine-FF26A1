"""
Portfolio Constraint Engine
Assignment ID: FF26A1

This module implements portfolio-level constraints on investment strategies:
1. MCap Filtering: Remove stocks in bottom 20% of yearly MCap ranking
2. Sector Exposure: Ensure no single sector exceeds 25% of portfolio

Author: Portfolio AI Engine
Date: March 2026
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import logging
from typing import Dict, List, Tuple, Set

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PortfolioConstraintEngine:
    """
    Applies portfolio-level constraints to investment strategies.
    
    Constraints:
    1. MCap Filtering: Remove stocks in bottom 20% of yearly MCap ranking
    2. Sector Exposure: No more than 25% of portfolio in single sector
    """
    
    def __init__(self, data_dir: str = 'data'):
        """
        Initialize the constraint engine with data files.
        
        Args:
            data_dir: Directory containing the input CSV files
        """
        self.data_dir = Path(data_dir)
        self.investment_rules = None
        self.sector_data = None
        self.mcap_data = None
        self.company_sector_map = {}
        
        self._load_data()
    
    def _load_data(self):
        """Load and validate input data files."""
        logger.info("Loading input data files...")
        
        # Load investment rules
        rules_path = self.data_dir / 'assignment_investment_rules.csv'
        self.investment_rules = pd.read_csv(rules_path)
        logger.info(f"Loaded investment rules: {self.investment_rules.shape}")
        
        # Load sector data
        sector_path = self.data_dir / 'assignment_sector_data.csv'
        self.sector_data = pd.read_csv(sector_path)
        logger.info(f"Loaded sector data: {self.sector_data.shape}")
        
        # Load market cap data
        mcap_path = self.data_dir / 'assignment_mcap.csv'
        self.mcap_data = pd.read_csv(mcap_path)
        logger.info(f"Loaded MCap data: {self.mcap_data.shape}")
        
        # Build company to sector mapping (case-sensitive)
        self._build_sector_mapping()
    
    def _build_sector_mapping(self):
        """Build a case-sensitive mapping of company names to sectors."""
        # Handle column name variations (with or without brackets)
        sector_col = '[Sector' if '[Sector' in self.sector_data.columns else 'Sector'
        
        for _, row in self.sector_data.iterrows():
            company_name = row['CO_NAME']
            sector = row[sector_col] if pd.notna(row[sector_col]) else 'Unknown'
            self.company_sector_map[company_name] = sector
        logger.info(f"Built sector mapping for {len(self.company_sector_map)} companies")
    
    def _precompute_mcap_thresholds(self):
        """
        Pre-calculate the bottom 20% MCap threshold for each year.
        
        Transforms MCap filtering from O(N log N) per year to O(1) lookup.
        Also builds MCap universe dictionary for O(1) company lookups.
        
        Args:
            None
            
        Returns:
            None
        """
        self.yearly_thresholds = {}
        self.mcap_universe = {}  # (company, year) -> mcap_value
        year_cols = [col for col in self.mcap_data.columns if col.isdigit()]
        
        for year in year_cols:
            # Get all valid MCap values for that year
            valid_mcaps = self.mcap_data[year].dropna().values
            if len(valid_mcaps) > 0:
                # Bottom 20% means the 20th percentile value
                self.yearly_thresholds[year] = np.percentile(valid_mcaps, 20)
            else:
                self.yearly_thresholds[year] = 0
            
            # Build MCap universe for this year
            for _, row in self.mcap_data.iterrows():
                company = row['CO_NAME']
                mcap_val = row[year]
                if pd.notna(mcap_val):
                    self.mcap_universe[(company, year)] = float(mcap_val)
        
        logger.debug(f"Pre-computed MCap thresholds for {len(self.yearly_thresholds)} years")
    
    def _get_company_sector(self, company_name: str) -> str:
        """
        Get sector for a company (case-sensitive matching).
        
        Args:
            company_name: Exact company name
            
        Returns:
            Sector name or 'Unknown' if not found
        """
        return self.company_sector_map.get(company_name, 'Unknown')
    
    def _parse_stock_list(self, cell_value) -> List[str]:
        """
        Parse stock list from portfolio cell.
        
        Handles both:
        - String representation of list: "['Stock1', 'Stock2']"
        - Actual empty list: [] or NaN
        
        Args:
            cell_value: Cell value from investment_rules CSV
            
        Returns:
            List of stock names (empty list if parsing fails or value is empty)
        """
        if pd.isna(cell_value):
            return []
        
        if isinstance(cell_value, list):
            return cell_value
        
        cell_str = str(cell_value).strip()
        
        if cell_str == '[]' or cell_str == '' or cell_str == 'nan':
            return []
        
        # Parse string representation of list
        try:
            # Use ast.literal_eval for safety
            import ast
            parsed = ast.literal_eval(cell_str)
            if isinstance(parsed, list):
                return parsed
        except (ValueError, SyntaxError):
            logger.warning(f"Could not parse stock list: {cell_str}")
            return []
        
        return []
    
    def _apply_mcap_filter(self, stocks: List[str], year: int) -> Tuple[List[str], Dict]:
        """
        Apply MCap filtering: Remove stocks in bottom 20% of yearly ranking.
        
        Uses pre-computed yearly thresholds and MCap universe for O(1) performance instead of
        recalculating rankings for every portfolio.
        
        Args:
            stocks: List of stock names in portfolio
            year: Year to filter
            
        Returns:
            Tuple of (filtered_stocks, filter_log) where filter_log contains
            'missing_mcap', 'bottom_20_pct', and 'removed_count'
        """
        filter_log = {
            'missing_mcap': [],
            'bottom_20_pct': [],
            'removed_count': 0
        }
        
        year_str = str(year)
        if year_str not in self.yearly_thresholds:
            logger.debug(f"Year {year} not found in pre-computed thresholds")
            return stocks, filter_log
        
        threshold = self.yearly_thresholds[year_str]
        
        # Filter portfolio stocks using pre-computed threshold and MCap universe
        filtered_stocks = []
        for stock in stocks:
            mcap_val = self.mcap_universe.get((stock, year_str))
            if mcap_val is None:
                # Missing MCap data - remove
                filter_log['missing_mcap'].append(stock)
                filter_log['removed_count'] += 1
            elif mcap_val <= threshold:
                # In bottom 20% (at or below threshold) - remove
                filter_log['bottom_20_pct'].append(stock)
                filter_log['removed_count'] += 1
            else:
                # Keep stock
                filtered_stocks.append(stock)
        
        return filtered_stocks, filter_log
    
    def _apply_sector_constraint(self, stocks: List[str]) -> Tuple[List[str], Dict]:
        """
        Apply sector exposure constraint: Max 25% of portfolio in single sector.
        
        Removal order: lowest MCap first, then alphabetically for tie-breaking.
        Ensures deterministic and reproducible output.
        
        Args:
            stocks: List of stock names in portfolio
            
        Returns:
            Tuple of (filtered_stocks, constraint_log) where constraint_log contains
            'sector_violations', 'removed_stocks', and 'removed_count'
        """
        constraint_log = {
            'sector_violations': [],
            'removed_stocks': [],
            'removed_count': 0
        }
        
        if len(stocks) == 0:
            return stocks, constraint_log
        
        max_sector_count = max(1, len(stocks) // 4)  # 25% rounded down
        
        # Group stocks by sector
        sector_groups = {}
        for stock in stocks:
            sector = self._get_company_sector(stock)
            if sector not in sector_groups:
                sector_groups[sector] = []
            sector_groups[sector].append(stock)
        
        # Identify over-exposed sectors and remove lowest MCap stocks
        removal_candidates = set()
        
        for sector, sector_stocks in sector_groups.items():
            if len(sector_stocks) > max_sector_count:
                constraint_log['sector_violations'].append({
                    'sector': sector,
                    'count': len(sector_stocks),
                    'max_allowed': max_sector_count,
                    'excess': len(sector_stocks) - max_sector_count
                })
                
                # Sort by MCap (ascending) to remove lowest MCap first
                # Use alphabetical name as secondary sort for deterministic tie-breaking
                stocks_with_mcap = [
                    (stock, self._get_latest_mcap(stock))
                    for stock in sector_stocks
                ]
                stocks_with_mcap.sort(key=lambda x: (x[1] is None, x[1], x[0]))
                
                # Remove excess stocks
                excess_count = len(sector_stocks) - max_sector_count
                for i in range(excess_count):
                    removal_candidates.add(stocks_with_mcap[i][0])
                    constraint_log['removed_stocks'].append(stocks_with_mcap[i][0])
                    constraint_log['removed_count'] += 1
        
        # Filter stocks
        filtered_stocks = [s for s in stocks if s not in removal_candidates]
        
        return filtered_stocks, constraint_log
    
    def _get_latest_mcap(self, company: str) -> float:
        """
        Get latest available MCap for a company.
        
        Searches from most recent year backwards to find available data.
        
        Args:
            company: Company name
            
        Returns:
            MCap value or None if not found
        """
        company_data = self.mcap_data[self.mcap_data['CO_NAME'] == company]
        if company_data.empty:
            return None
        
        # Get latest year with available data
        row = company_data.iloc[0]
        year_cols = [str(y) for y in range(2023, 1989, -1)]
        
        for year_col in year_cols:
            if year_col in row.index:
                val = row[year_col]
                if pd.notna(val):
                    return float(val)
        
        return None
    
    def apply_constraints(self) -> pd.DataFrame:
        """
        Apply all constraints to investment strategies.
        
        Steps:
        1. Pre-compute MCap thresholds for optimization
        2. For each strategy and year:
           - Apply MCap filtering (bottom 20% removal)
           - Apply sector exposure constraint (max 25% per sector)
        
        Args:
            None
            
        Returns:
            DataFrame with constrained portfolios where each row is a strategy
            and columns are year identifiers containing lists of remaining stocks
        """
        logger.info("Applying constraints to portfolios...")
        
        # Pre-compute MCap thresholds for O(1) filtering
        self._precompute_mcap_thresholds()
        
        # Get year columns (exclude first column which is strategy name)
        year_columns = [col for col in self.investment_rules.columns if col.isdigit()]
        year_columns = sorted([int(y) for y in year_columns])
        
        # Process each strategy
        output_data = []
        
        for idx, row in self.investment_rules.iterrows():
            strategy_name = row.iloc[0]  # First column is strategy name
            strategy_name_constrained = f"{strategy_name}_constrained"
            
            logger.info(f"Processing strategy: {strategy_name}")
            
            constrained_row = {'strat_name': strategy_name_constrained}
            
            # Process each year
            for year in year_columns:
                year_str = str(year)
                cell_value = row[year_str]
                
                # Parse stock list
                stocks = self._parse_stock_list(cell_value)
                
                if len(stocks) == 0:
                    constrained_row[year_str] = []
                    continue
                
                # Apply MCap filter
                stocks_after_mcap, mcap_log = self._apply_mcap_filter(stocks, year)
                
                if len(mcap_log['missing_mcap']) > 0:
                    logger.debug(
                        f"{strategy_name} {year}: Removed {len(mcap_log['missing_mcap'])} "
                        f"stocks with missing MCap"
                    )
                
                if len(mcap_log['bottom_20_pct']) > 0:
                    logger.debug(
                        f"{strategy_name} {year}: Removed {len(mcap_log['bottom_20_pct'])} "
                        f"stocks in bottom 20% by MCap"
                    )
                
                # Apply sector constraint
                stocks_after_sector, sector_log = self._apply_sector_constraint(
                    stocks_after_mcap
                )
                
                if sector_log['removed_count'] > 0:
                    logger.debug(
                        f"{strategy_name} {year}: Removed {sector_log['removed_count']} "
                        f"stocks due to sector constraint"
                    )
                
                constrained_row[year_str] = stocks_after_sector
            
            output_data.append(constrained_row)
        
        # Create output DataFrame
        output_df = pd.DataFrame(output_data)
        
        # Ensure year columns are in correct order
        year_cols_str = [str(y) for y in year_columns]
        output_df = output_df[['strat_name'] + year_cols_str]
        
        logger.info(f"Constraints applied to {len(output_data)} strategies")
        return output_df
    
    def save_output(self, output_df: pd.DataFrame, output_path: str = 'output.csv'):
        """
        Save constrained portfolios to CSV file.
        
        Args:
            output_df: DataFrame with constrained portfolios
            output_path: Path to save output CSV
            
        Returns:
            None
        """
        # Convert list columns to string representation
        for col in output_df.columns:
            if col != 'strat_name':
                output_df[col] = output_df[col].apply(
                    lambda x: str(x) if isinstance(x, list) else x
                )
        
        output_df.to_csv(output_path, index=False)
        logger.info(f"Output saved to {output_path}")


def verify_output(output_df: pd.DataFrame, sector_map: Dict[str, str]) -> bool:
    """
    Validate output to ensure no sector exceeds 25% in any portfolio.
    
    Self-correction step to prove constraints were properly enforced.
    
    Args:
        output_df: DataFrame with constrained portfolios from output.csv
        sector_map: Dictionary mapping company names to sectors
        
    Returns:
        True if all portfolios are valid, False if violations found
    """
    import ast
    
    violations_found = False
    
    for idx, row in output_df.iterrows():
        for col in output_df.columns[1:]:  # Skip strat_name column
            stocks_str = row[col]
            
            # Parse stock list
            try:
                if isinstance(stocks_str, str):
                    stocks = ast.literal_eval(stocks_str)
                else:
                    stocks = stocks_str
            except (ValueError, SyntaxError):
                continue
            
            if not stocks:
                continue
            
            # Count sectors
            counts = pd.Series([sector_map.get(s, 'Unknown') for s in stocks]).value_counts()
            max_allowed = len(stocks) // 4  # 25% rounded down
            
            for sector, count in counts.items():
                if count > max_allowed:
                    logger.warning(
                        f"Violation: {row['strat_name']} | Year {col} | "
                        f"{sector}: {count}/{len(stocks)} (max allowed: {max_allowed})"
                    )
                    violations_found = True
    
    if not violations_found:
        logger.info("✓ Verification passed: All portfolios meet constraints")
    else:
        logger.warning("✗ Verification failed: Constraint violations detected")
    
    return not violations_found


def main():
    """
    Main execution function.
    
    Steps:
    1. Initialize constraint engine with input data
    2. Apply constraints (MCap filtering + sector exposure limits)
    3. Save output to CSV
    4. Verify output meets all constraints
    
    Args:
        None
        
    Returns:
        None
    """
    # Initialize constraint engine
    engine = PortfolioConstraintEngine(data_dir='data')
    
    # Apply constraints
    constrained_portfolios = engine.apply_constraints()
    
    # Save output
    engine.save_output(constrained_portfolios, output_path='output.csv')
    
    # Verify constraints were properly applied
    verify_output(constrained_portfolios, engine.company_sector_map)
    
    logger.info("Portfolio constraint application completed successfully")


if __name__ == '__main__':
    main()

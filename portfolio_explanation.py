"""
Portfolio Explanation Engine - Simplified LLM Integration
Assignment ID: FF26A1

Generates portfolio explanations using Gemini API.
"""

import os
import json
import pandas as pd
from pathlib import Path
from typing import Dict, List
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import Google Generative AI
from google import genai
from google.genai import types

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


class PortfolioExplainer:
    """Generate AI explanations for investment portfolios."""
    
    def __init__(self):
        """Initialize with Gemini API."""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY not set in .env file")
        
        self.client = genai.Client(api_key=api_key)
        self.model_id = "gemini-2.5-flash-lite"
        logger.info("✓ Gemini API configured")
    
    def load_data(self):
        """Load input data files."""
        self.investment_rules = pd.read_csv('data/assignment_investment_rules.csv')
        self.sector_data = pd.read_csv('data/assignment_sector_data.csv')
        self.mcap_data = pd.read_csv('data/assignment_mcap.csv')
        
        # Build sector mapping
        sector_col = '[Sector' if '[Sector' in self.sector_data.columns else 'Sector'
        self.sector_map = dict(zip(self.sector_data['CO_NAME'], self.sector_data[sector_col]))
        
        logger.info("✓ Data loaded successfully")
    
    def get_portfolio(self, strategy_idx: int = 0, year: int = 2021) -> Dict:
        """Get portfolio for analysis."""
        row = self.investment_rules.iloc[strategy_idx]
        strategy_name = str(row.iloc[0]).strip()
        year_col = str(year)
        
        if year_col not in row.index:
            raise ValueError(f"Year {year} not found")
        
        # Parse stock list
        stocks_cell = row[year_col]
        if pd.isna(stocks_cell):
            stocks = []
        else:
            cell_str = str(stocks_cell).strip()
            if cell_str in ['[]', '', 'nan']:
                stocks = []
            else:
                try:
                    import ast
                    stocks = ast.literal_eval(cell_str)
                except:
                    stocks = []
        
        # Analyze portfolio
        portfolio = {
            'strategy': strategy_name,
            'year': year,
            'total_stocks': len(stocks),
            'stocks': stocks,
            'sector_distribution': self._analyze_sectors(stocks),
            'mcap_distribution': self._analyze_mcap(stocks, year)
        }
        
        return portfolio
    
    def _analyze_sectors(self, stocks: List[str]) -> Dict:
        """Analyze sector distribution."""
        sector_count = {}
        for stock in stocks:
            sector = self.sector_map.get(stock, 'Unknown')
            sector_count[sector] = sector_count.get(sector, 0) + 1
        
        if not sector_count:
            return {'distribution': {}, 'note': 'No stocks in portfolio'}
        
        sector_pct = {
            s: round(100 * c / len(stocks), 1)
            for s, c in sector_count.items()
        }
        
        return {
            'total_sectors': len(sector_count),
            'distribution': sector_count,
            'percentage': sector_pct,
            'top_sector': max(sector_pct, key=sector_pct.get),
            'top_sector_pct': max(sector_pct.values())
        }
    
    def _analyze_mcap(self, stocks: List[str], year: int) -> Dict:
        """Analyze MCap distribution."""
        year_col = str(year)
        mcap_values = []
        
        for stock in stocks:
            stock_data = self.mcap_data[self.mcap_data['CO_NAME'] == stock]
            if not stock_data.empty and year_col in stock_data.columns:
                val = stock_data.iloc[0][year_col]
                if pd.notna(val):
                    mcap_values.append(float(val))
        
        if not mcap_values:
            return {'note': 'No MCap data available', 'count': 0}
        
        mcap_sorted = sorted(mcap_values, reverse=True)
        
        return {
            'count': len(mcap_values),
            'avg': round(sum(mcap_values) / len(mcap_values), 1),
            'median': round(mcap_sorted[len(mcap_sorted)//2], 1),
            'min': round(min(mcap_values), 1),
            'max': round(max(mcap_values), 1),
            'total': round(sum(mcap_values), 1)
        }
    
    def generate_explanations(self, portfolio: Dict) -> Dict:
        """Generate three types of explanations using the modern GenAI SDK."""
        import time
        from google.genai import types
        
        explanations = {}
        
        # Enforce Rule 3.1: No hallucinations or invented numbers
        config = types.GenerateContentConfig(
            system_instruction="You are a professional investment analyst. Use ONLY the provided data. Do not invent numbers."
        )

        # Map sections to your existing prompt logic
        sections = {
            'sector_concentration': f"""Analyze the sector concentration of the '{portfolio['strategy']}' portfolio for {portfolio['year']}.
Portfolio: {portfolio['total_stocks']} stocks across {portfolio['sector_distribution'].get('total_sectors', 0)} sectors.
Top sector: {portfolio['sector_distribution'].get('top_sector', 'N/A')} at {portfolio['sector_distribution'].get('top_sector_pct', 0)}%
Sector Distribution: {json.dumps(portfolio['sector_distribution'].get('distribution', {}), indent=2)}
Provide brief observations on: 1. Concentration level, 2. Top sectors, 3. Diversification quality.""",

            'mcap_distribution': f"""Analyze the market cap distribution of '{portfolio['strategy']}' for {portfolio['year']}.
{portfolio['total_stocks']} stocks with {portfolio['mcap_distribution'].get('count', 0)} having MCap data.
MCap Statistics (₹ cr): Total: {portfolio['mcap_distribution'].get('total', 0):,}, Avg: {portfolio['mcap_distribution'].get('avg', 0):,}, Median: {portfolio['mcap_distribution'].get('median', 0):,}
Provide observations on: 1. Size distribution, 2. Avg company size, 3. Liquidity.""",

            'risk_commentary': f"""Provide risk commentary for '{portfolio['strategy']}' portfolio ({portfolio['year']}).
Structure: {portfolio['total_stocks']} stocks in {portfolio['sector_distribution'].get('total_sectors', 0)} sectors.
Top sector: {portfolio['sector_distribution'].get('top_sector', 'N/A')} ({portfolio['sector_distribution'].get('top_sector_pct', 0)}%).
Provide assessment of: 1. Concentration risk, 2. Diversification quality, 3. Overall risk level."""
        }

        for key, prompt in sections.items():
            logger.info(f"Generating {key} analysis...")
            try:
                # Modern SDK call using the stable Gemini 3 Flash model
                response = self.client.models.generate_content(
                    model=self.model_id,
                    contents=prompt,
                    config=config
                )
                explanations[key] = {'prompt': prompt, 'response': response.text}
                logger.info(f"✓ {key} generated")
                
                # Mandatory pause for free-tier rate limits
                time.sleep(2) 
            except Exception as e:
                logger.error(f"Error generating {key}: {e}")
                explanations[key] = {'prompt': prompt, 'response': f"Error: {str(e)}"}
        
        return explanations
    
    def save_explanations(self, portfolio: Dict, explanations: Dict):
        """Save explanations to JSON."""
        output = {
            'portfolio_metadata': {
                'strategy': portfolio['strategy'],
                'year': portfolio['year'],
                'total_stocks': portfolio['total_stocks'],
                'sectors': portfolio['sector_distribution'].get('total_sectors', 0)
            },
            'explanations': explanations
        }
        
        with open('portfolio_explanations.json', 'w') as f:
            json.dump(output, f, indent=2)
        
        logger.info("✓ Explanations saved to portfolio_explanations.json")


def main():
    """Main execution."""
    explainer = PortfolioExplainer()
    explainer.load_data()
    
    # Analyze first strategy for year 2021
    portfolio = explainer.get_portfolio(strategy_idx=0, year=2021)
    
    logger.info(f"\nAnalyzing: {portfolio['strategy']} ({portfolio['year']})")
    logger.info(f"Portfolio size: {portfolio['total_stocks']} stocks")
    
    # Generate explanations
    explanations = explainer.generate_explanations(portfolio)
    
    # Save results
    explainer.save_explanations(portfolio, explanations)
    
    # Display summary
    print("\n" + "="*70)
    print("PORTFOLIO EXPLANATION GENERATION COMPLETE")
    print("="*70)
    print(f"Strategy: {portfolio['strategy']}")
    print(f"Year: {portfolio['year']}")
    print(f"Stocks: {portfolio['total_stocks']}")
    print(f"Sectors: {portfolio['sector_distribution'].get('total_sectors', 0)}")
    print(f"\nGenerated Explanations:")
    for exp_type in explanations.keys():
        print(f"  ✓ {exp_type}")
    print("\nOutput: portfolio_explanations.json")
    print("="*70)


if __name__ == '__main__':
    main()

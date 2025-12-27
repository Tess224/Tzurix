"""
Tzurix Scoring Engine
Calculates trading performance scores from on-chain Solana data

Uses Helius API to fetch transaction history and calculate:
- P&L (Profit & Loss)
- Win Rate
- Trade Count
- Average Hold Time
- Risk-Adjusted Returns

Final score is calculated and capped at ±10% daily change.
"""

import os
import time
import logging
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict

# ============================================================================
# CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

HELIUS_API_KEY = os.environ.get('HELIUS_API_KEY', '')
HELIUS_BASE_URL = "https://api.helius.xyz/v0"
HELIUS_RPC_URL = f"https://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

# Scoring constants
STARTING_SCORE = 10
DAILY_SCORE_CAP = 0.10  # ±10%
MIN_SCORE = 1

# Known DEX program IDs for identifying swaps
DEX_PROGRAMS = {
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8": "Raydium",
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4": "Jupiter",
    "9W959DqEETiGZocYWCQPaJ6sBmUzgfxXfqGeTEdp3aQP": "Orca",
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc": "Orca Whirlpool",
    "srmqPvymJeFKQ4zGQed1GFppgkRHL9kaELCbyksJtPX": "Serum",
    "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P": "Pump.fun",
}

# SOL mint address
SOL_MINT = "So11111111111111111111111111111111111111112"


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Trade:
    """Represents a single trade (buy or sell)."""
    timestamp: int
    signature: str
    side: str  # 'buy' or 'sell'
    token_mint: str
    token_amount: float
    sol_amount: float
    price_per_token: float
    dex: str


@dataclass
class Position:
    """Tracks an open position in a token."""
    token_mint: str
    total_bought: float
    total_cost_sol: float
    avg_buy_price: float
    total_sold: float
    total_received_sol: float
    realized_pnl_sol: float
    trades: List[Trade]


@dataclass
class TradingMetrics:
    """Aggregated trading metrics for scoring."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    total_pnl_sol: float
    total_volume_sol: float
    win_rate: float
    avg_trade_pnl: float
    largest_win_sol: float
    largest_loss_sol: float
    unique_tokens_traded: int
    avg_hold_time_hours: float
    trades_per_day: float
    risk_adjusted_return: float  # Simplified Sharpe-like ratio


@dataclass
class ScoreResult:
    """Final scoring result."""
    wallet_address: str
    raw_score: int
    final_score: int
    previous_score: int
    capped: bool
    metrics: TradingMetrics
    calculated_at: datetime


# ============================================================================
# HELIUS API FUNCTIONS
# ============================================================================

def fetch_transactions(wallet_address: str, limit: int = 100) -> List[Dict]:
    """
    Fetch enhanced transactions for a wallet using Helius API.
    
    Returns parsed, human-readable transaction data.
    """
    if not HELIUS_API_KEY:
        logger.warning("No HELIUS_API_KEY set - using mock data")
        return []
    
    url = f"{HELIUS_BASE_URL}/addresses/{wallet_address}/transactions"
    params = {
        "api-key": HELIUS_API_KEY,
        "limit": limit
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 200:
            transactions = response.json()
            logger.info(f"Fetched {len(transactions)} transactions for {wallet_address[:8]}...")
            return transactions
        else:
            logger.error(f"Helius API error: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        return []


def fetch_parsed_transactions(wallet_address: str, limit: int = 100) -> List[Dict]:
    """
    Fetch and parse transactions using Helius Enhanced API.
    This gives us structured swap/transfer data.
    """
    if not HELIUS_API_KEY:
        logger.warning("No HELIUS_API_KEY set")
        return []
    
    url = f"{HELIUS_BASE_URL}/addresses/{wallet_address}/transactions"
    params = {
        "api-key": HELIUS_API_KEY,
        "limit": limit,
        "type": "SWAP"  # Filter for swap transactions
    }
    
    all_transactions = []
    
    try:
        # Fetch swap transactions
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            all_transactions.extend(response.json())
        
        logger.info(f"Fetched {len(all_transactions)} swap transactions")
        return all_transactions
        
    except Exception as e:
        logger.error(f"Error fetching parsed transactions: {e}")
        return []


# ============================================================================
# TRANSACTION PARSING
# ============================================================================

def parse_swap_transaction(tx: Dict, wallet_address: str) -> Optional[Trade]:
    """
    Parse a Helius enhanced transaction into a Trade object.
    
    Helius provides parsed data with 'tokenTransfers' and 'nativeTransfers'.
    """
    try:
        # Skip failed transactions
        if tx.get('transactionError'):
            return None
        
        signature = tx.get('signature', '')
        timestamp = tx.get('timestamp', 0)
        tx_type = tx.get('type', '')
        
        # We're interested in SWAP transactions
        if tx_type != 'SWAP':
            return None
        
        # Get token transfers
        token_transfers = tx.get('tokenTransfers', [])
        native_transfers = tx.get('nativeTransfers', [])
        
        if not token_transfers:
            return None
        
        # Analyze the swap direction
        # If wallet received tokens and sent SOL = BUY
        # If wallet sent tokens and received SOL = SELL
        
        sol_in = 0
        sol_out = 0
        token_in = None
        token_out = None
        token_in_amount = 0
        token_out_amount = 0
        
        # Check native (SOL) transfers
        for transfer in native_transfers:
            if transfer.get('toUserAccount') == wallet_address:
                sol_in += transfer.get('amount', 0) / 1e9  # Convert lamports to SOL
            if transfer.get('fromUserAccount') == wallet_address:
                sol_out += transfer.get('amount', 0) / 1e9
        
        # Check token transfers
        for transfer in token_transfers:
            mint = transfer.get('mint', '')
            amount = transfer.get('tokenAmount', 0)
            
            if transfer.get('toUserAccount') == wallet_address:
                token_in = mint
                token_in_amount = amount
            if transfer.get('fromUserAccount') == wallet_address:
                token_out = mint
                token_out_amount = amount
        
        # Determine trade side
        # BUY: SOL out, Token in (not SOL)
        # SELL: Token out (not SOL), SOL in
        
        if sol_out > 0 and token_in and token_in != SOL_MINT:
            # This is a BUY
            return Trade(
                timestamp=timestamp,
                signature=signature,
                side='buy',
                token_mint=token_in,
                token_amount=token_in_amount,
                sol_amount=sol_out,
                price_per_token=sol_out / token_in_amount if token_in_amount > 0 else 0,
                dex=tx.get('source', 'Unknown')
            )
        
        elif sol_in > 0 and token_out and token_out != SOL_MINT:
            # This is a SELL
            return Trade(
                timestamp=timestamp,
                signature=signature,
                side='sell',
                token_mint=token_out,
                token_amount=token_out_amount,
                sol_amount=sol_in,
                price_per_token=sol_in / token_out_amount if token_out_amount > 0 else 0,
                dex=tx.get('source', 'Unknown')
            )
        
        return None
        
    except Exception as e:
        logger.error(f"Error parsing transaction: {e}")
        return None


def parse_all_transactions(transactions: List[Dict], wallet_address: str) -> List[Trade]:
    """Parse all transactions into Trade objects."""
    trades = []
    
    for tx in transactions:
        trade = parse_swap_transaction(tx, wallet_address)
        if trade:
            trades.append(trade)
    
    # Sort by timestamp (oldest first)
    trades.sort(key=lambda t: t.timestamp)
    
    logger.info(f"Parsed {len(trades)} trades from {len(transactions)} transactions")
    return trades


# ============================================================================
# P&L CALCULATION
# ============================================================================

def calculate_positions(trades: List[Trade]) -> Dict[str, Position]:
    """
    Calculate positions and P&L for each token traded.
    
    Uses FIFO (First In, First Out) for cost basis.
    """
    positions: Dict[str, Position] = {}
    
    for trade in trades:
        mint = trade.token_mint
        
        # Initialize position if new token
        if mint not in positions:
            positions[mint] = Position(
                token_mint=mint,
                total_bought=0,
                total_cost_sol=0,
                avg_buy_price=0,
                total_sold=0,
                total_received_sol=0,
                realized_pnl_sol=0,
                trades=[]
            )
        
        pos = positions[mint]
        pos.trades.append(trade)
        
        if trade.side == 'buy':
            # Add to position
            pos.total_bought += trade.token_amount
            pos.total_cost_sol += trade.sol_amount
            
            # Update average buy price
            if pos.total_bought > 0:
                pos.avg_buy_price = pos.total_cost_sol / pos.total_bought
        
        elif trade.side == 'sell':
            # Calculate P&L for this sale
            pos.total_sold += trade.token_amount
            pos.total_received_sol += trade.sol_amount
            
            # FIFO P&L: Compare sell price to average buy price
            if pos.avg_buy_price > 0:
                cost_basis = trade.token_amount * pos.avg_buy_price
                pnl = trade.sol_amount - cost_basis
                pos.realized_pnl_sol += pnl
    
    return positions


def calculate_trading_metrics(positions: Dict[str, Position], trades: List[Trade], days: int = 30) -> TradingMetrics:
    """
    Calculate comprehensive trading metrics from positions.
    """
    if not trades:
        return TradingMetrics(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            total_pnl_sol=0,
            total_volume_sol=0,
            win_rate=0,
            avg_trade_pnl=0,
            largest_win_sol=0,
            largest_loss_sol=0,
            unique_tokens_traded=0,
            avg_hold_time_hours=0,
            trades_per_day=0,
            risk_adjusted_return=0
        )
    
    # Count wins/losses per token
    winning_trades = 0
    losing_trades = 0
    total_pnl_sol = 0
    largest_win = 0
    largest_loss = 0
    total_volume = 0
    
    for mint, pos in positions.items():
        total_pnl_sol += pos.realized_pnl_sol
        total_volume += pos.total_cost_sol + pos.total_received_sol
        
        if pos.realized_pnl_sol > 0:
            winning_trades += 1
            largest_win = max(largest_win, pos.realized_pnl_sol)
        elif pos.realized_pnl_sol < 0:
            losing_trades += 1
            largest_loss = min(largest_loss, pos.realized_pnl_sol)
    
    total_closed = winning_trades + losing_trades
    win_rate = (winning_trades / total_closed * 100) if total_closed > 0 else 0
    avg_trade_pnl = total_pnl_sol / total_closed if total_closed > 0 else 0
    
    # Calculate average hold time
    hold_times = []
    for mint, pos in positions.items():
        buys = [t for t in pos.trades if t.side == 'buy']
        sells = [t for t in pos.trades if t.side == 'sell']
        
        if buys and sells:
            # Simple: time from first buy to first sell
            first_buy = min(t.timestamp for t in buys)
            first_sell = min(t.timestamp for t in sells)
            if first_sell > first_buy:
                hold_times.append((first_sell - first_buy) / 3600)  # Convert to hours
    
    avg_hold_time = sum(hold_times) / len(hold_times) if hold_times else 0
    
    # Trades per day
    if trades:
        time_span_days = max(1, (trades[-1].timestamp - trades[0].timestamp) / 86400)
        trades_per_day = len(trades) / time_span_days
    else:
        trades_per_day = 0
    
    # Simplified risk-adjusted return (like Sharpe ratio)
    # = (Return) / (Volatility proxy)
    # Using win rate variance as volatility proxy
    if total_volume > 0:
        return_pct = (total_pnl_sol / total_volume) * 100
        volatility_proxy = abs(50 - win_rate) + 10  # Higher when win rate deviates from 50%
        risk_adjusted_return = return_pct / volatility_proxy if volatility_proxy > 0 else 0
    else:
        risk_adjusted_return = 0
    
    return TradingMetrics(
        total_trades=len(trades),
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        total_pnl_sol=total_pnl_sol,
        total_volume_sol=total_volume,
        win_rate=win_rate,
        avg_trade_pnl=avg_trade_pnl,
        largest_win_sol=largest_win,
        largest_loss_sol=largest_loss,
        unique_tokens_traded=len(positions),
        avg_hold_time_hours=avg_hold_time,
        trades_per_day=trades_per_day,
        risk_adjusted_return=risk_adjusted_return
    )


# ============================================================================
# SCORING ALGORITHM
# ============================================================================

def calculate_raw_score(metrics: TradingMetrics) -> int:
    """
    Calculate raw score from trading metrics.
    
    Scoring Components (weighted):
    - P&L Performance: 40%
    - Win Rate: 25%
    - Consistency (trades per day): 15%
    - Risk Management: 20%
    
    Base score: 10
    Score range: 1 to unlimited (but capped daily)
    """
    base_score = STARTING_SCORE
    
    if metrics.total_trades == 0:
        return base_score
    
    # Component 1: P&L Performance (40% weight)
    # +1 point per 0.5 SOL profit, -1 point per 0.5 SOL loss
    pnl_score = metrics.total_pnl_sol * 2  # 2 points per SOL
    pnl_component = pnl_score * 0.40
    
    # Component 2: Win Rate (25% weight)
    # 50% win rate = neutral, >50% = bonus, <50% = penalty
    # Max +10 points at 100% win rate, -10 at 0%
    win_rate_score = (metrics.win_rate - 50) / 5  # -10 to +10
    win_rate_component = win_rate_score * 0.25
    
    # Component 3: Consistency (15% weight)
    # Reward active trading, but not excessive
    # Optimal: 5-20 trades per day
    if metrics.trades_per_day < 1:
        consistency_score = -2  # Too inactive
    elif metrics.trades_per_day < 5:
        consistency_score = metrics.trades_per_day
    elif metrics.trades_per_day <= 20:
        consistency_score = 5  # Optimal range
    else:
        consistency_score = 5 - (metrics.trades_per_day - 20) * 0.1  # Penalty for overtrading
    consistency_component = consistency_score * 0.15
    
    # Component 4: Risk Management (20% weight)
    # Based on risk-adjusted return and loss management
    risk_score = metrics.risk_adjusted_return
    # Penalize large losses
    if metrics.largest_loss_sol < -5:
        risk_score -= 3
    risk_component = risk_score * 0.20
    
    # Calculate total score
    total_adjustment = pnl_component + win_rate_component + consistency_component + risk_component
    raw_score = base_score + total_adjustment
    
    # Ensure minimum score of 1
    return max(1, int(raw_score))


def apply_daily_cap(current_score: int, raw_score: int) -> Tuple[int, bool]:
    """
    Apply ±10% daily cap to score changes.
    
    Returns: (final_score, was_capped)
    """
    if current_score == 0:
        return max(1, raw_score), False
    
    # Calculate percentage change
    change_percent = (raw_score - current_score) / current_score
    
    # Check if capping is needed
    capped = abs(change_percent) > DAILY_SCORE_CAP
    
    # Apply cap
    if change_percent > DAILY_SCORE_CAP:
        capped_change = DAILY_SCORE_CAP
    elif change_percent < -DAILY_SCORE_CAP:
        capped_change = -DAILY_SCORE_CAP
    else:
        capped_change = change_percent
    
    # Calculate final score
    final_score = int(current_score * (1 + capped_change))
    
    # Ensure minimum score
    return max(MIN_SCORE, final_score), capped


# ============================================================================
# MAIN SCORING FUNCTION
# ============================================================================

def calculate_agent_score(
    wallet_address: str,
    previous_score: int = STARTING_SCORE,
    days: int = 30,
    transaction_limit: int = 100
) -> ScoreResult:
    """
    Main function to calculate an agent's score from on-chain data.
    
    Args:
        wallet_address: Solana wallet address of the agent
        previous_score: The agent's previous score (for cap calculation)
        days: Number of days of history to analyze
        transaction_limit: Max transactions to fetch
    
    Returns:
        ScoreResult with raw score, final (capped) score, and metrics
    """
    logger.info(f"Calculating score for {wallet_address[:8]}...")
    
    # Step 1: Fetch transactions
    transactions = fetch_transactions(wallet_address, limit=transaction_limit)
    
    # Step 2: Parse into trades
    trades = parse_all_transactions(transactions, wallet_address)
    
    # Step 3: Calculate positions and P&L
    positions = calculate_positions(trades)
    
    # Step 4: Calculate metrics
    metrics = calculate_trading_metrics(positions, trades, days)
    
    # Step 5: Calculate raw score
    raw_score = calculate_raw_score(metrics)
    
    # Step 6: Apply daily cap
    final_score, capped = apply_daily_cap(previous_score, raw_score)
    
    logger.info(f"Score calculated: raw={raw_score}, final={final_score}, capped={capped}")
    
    return ScoreResult(
        wallet_address=wallet_address,
        raw_score=raw_score,
        final_score=final_score,
        previous_score=previous_score,
        capped=capped,
        metrics=metrics,
        calculated_at=datetime.utcnow()
    )


# ============================================================================
# MOCK DATA FOR TESTING (when no API key)
# ============================================================================

def generate_mock_score(wallet_address: str, previous_score: int = STARTING_SCORE) -> ScoreResult:
    """
    Generate a mock score for testing without API key.
    Simulates realistic trading metrics.
    """
    import random
    
    # Generate random but realistic metrics
    total_trades = random.randint(10, 100)
    win_rate = random.uniform(35, 75)
    winning_trades = int(total_trades * win_rate / 100)
    losing_trades = total_trades - winning_trades
    
    total_pnl = random.uniform(-5, 15)  # SOL
    total_volume = random.uniform(10, 100)  # SOL
    
    metrics = TradingMetrics(
        total_trades=total_trades,
        winning_trades=winning_trades,
        losing_trades=losing_trades,
        total_pnl_sol=total_pnl,
        total_volume_sol=total_volume,
        win_rate=win_rate,
        avg_trade_pnl=total_pnl / total_trades if total_trades > 0 else 0,
        largest_win_sol=random.uniform(0.5, 5),
        largest_loss_sol=-random.uniform(0.1, 2),
        unique_tokens_traded=random.randint(5, 30),
        avg_hold_time_hours=random.uniform(0.5, 48),
        trades_per_day=random.uniform(1, 15),
        risk_adjusted_return=random.uniform(-1, 3)
    )
    
    raw_score = calculate_raw_score(metrics)
    final_score, capped = apply_daily_cap(previous_score, raw_score)
    
    return ScoreResult(
        wallet_address=wallet_address,
        raw_score=raw_score,
        final_score=final_score,
        previous_score=previous_score,
        capped=capped,
        metrics=metrics,
        calculated_at=datetime.utcnow()
    )


# ============================================================================
# CLI INTERFACE
# ============================================================================

def main():
    """Command-line interface for testing the scoring engine."""
    import sys
    
    print("=" * 60)
    print("TZURIX SCORING ENGINE")
    print("=" * 60)
    
    # Test wallet - you can replace with any wallet
    # This is a known active trading wallet from the search results
    test_wallet = None
    
    if len(sys.argv) > 1:
        test_wallet = sys.argv[1]
    else:
        print("Usage: python scoring_engine.py <wallet_address>")
        sys.exit(1)
    
    print(f"\nAnalyzing wallet: {test_wallet}")
    print("-" * 60)
    
    if HELIUS_API_KEY:
        print("Using Helius API for real data...")
        result = calculate_agent_score(test_wallet)
    else:
        print("No HELIUS_API_KEY found - using mock data for demo...")
        result = generate_mock_score(test_wallet)
    
    print("\n" + "=" * 60)
    print("SCORING RESULTS")
    print("=" * 60)
    
    print(f"\nWallet: {result.wallet_address}")
    print(f"Previous Score: {result.previous_score}")
    print(f"Raw Score: {result.raw_score}")
    print(f"Final Score: {result.final_score}")
    print(f"Capped: {result.capped}")
    print(f"Calculated At: {result.calculated_at}")
    
    print("\n" + "-" * 60)
    print("TRADING METRICS")
    print("-" * 60)
    
    m = result.metrics
    print(f"Total Trades: {m.total_trades}")
    print(f"Winning Trades: {m.winning_trades}")
    print(f"Losing Trades: {m.losing_trades}")
    print(f"Win Rate: {m.win_rate:.1f}%")
    print(f"Total P&L: {m.total_pnl_sol:.4f} SOL")
    print(f"Total Volume: {m.total_volume_sol:.4f} SOL")
    print(f"Avg Trade P&L: {m.avg_trade_pnl:.4f} SOL")
    print(f"Largest Win: {m.largest_win_sol:.4f} SOL")
    print(f"Largest Loss: {m.largest_loss_sol:.4f} SOL")
    print(f"Unique Tokens: {m.unique_tokens_traded}")
    print(f"Avg Hold Time: {m.avg_hold_time_hours:.1f} hours")
    print(f"Trades/Day: {m.trades_per_day:.1f}")
    print(f"Risk-Adjusted Return: {m.risk_adjusted_return:.2f}")
    
    print("\n" + "=" * 60)
    
    # Price calculation
    from decimal import Decimal
    LAMPORTS_PER_SCORE_POINT = 67
    price_lamports = result.final_score * LAMPORTS_PER_SCORE_POINT
    price_sol = price_lamports / 1_000_000_000
    market_cap_sol = price_sol * 100_000_000  # 100M supply
    
    print("PRICE CALCULATION")
    print("-" * 60)
    print(f"Score: {result.final_score}")
    print(f"Price: {price_lamports} lamports = {price_sol:.9f} SOL")
    print(f"Market Cap: {market_cap_sol:.2f} SOL")
    print(f"Market Cap (USD @ $150): ${market_cap_sol * 150:,.2f}")
    print("=" * 60)


if __name__ == "__main__":
    main()

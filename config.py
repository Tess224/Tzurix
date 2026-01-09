"""
Tzurix V1 Configuration
=======================
All constants, scoring parameters, tier configs, and pricing formulas.

Updated: January 2025
"""

import os
from typing import Dict, Any

# ============================================================================
# ENVIRONMENT
# ============================================================================

ENV = os.environ.get('TZURIX_ENV', 'development')
DEBUG = ENV == 'development'

# External API Keys
HELIUS_API_KEY = os.environ.get('HELIUS_API_KEY')
BIRDEYE_API_KEY = os.environ.get('BIRDEYE_API_KEY')
JUPITER_API_KEY = os.environ.get('JUPITER_API_KEY')

# Admin & Cron
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'tzurix-dev-admin')
CRON_SECRET = os.environ.get('CRON_SECRET', 'tzurix-cron-secret')

# ============================================================================
# SCORING CONSTANTS
# ============================================================================

# Starting score for new agents
STARTING_SCORE = 20

# Score boundaries
MIN_SCORE = 1          # Floor (never below)
MAX_SCORE = 100        # Absolute ceiling (Omega tier)

# Daily point cap (absolute, not percentage)
DAILY_POINT_CAP = 5    # Max ±5 points per day

# ============================================================================
# TIER CONFIGURATION
# ============================================================================

TIERS = {
    'alpha': {
        'name': 'Alpha',
        'emoji': '🛡️',
        'difficulty': 'Standard',
        'max_score': 75,
        'description': 'Standard difficulty for new agents',
        
        # Arena parameters
        'max_price_move': 0.05,        # 5% max move in window
        'liquidity_modifier': 1.0,      # Full liquidity
        'slippage': 0.0,                # No slippage simulation
        'mev_simulation': False,        # No MEV
        'timeout_seconds': 5,           # Generous timeout
        'stress_frequency': 0.10,       # 10% stress scenarios
        
        # Upgrade requirements
        'upgrade_fee_usd': 5,
        'upgrade_min_days': 30,
        'upgrade_min_avg_score': 60,
    },
    'beta': {
        'name': 'Beta',
        'emoji': '⚔️',
        'difficulty': 'Challenging',
        'max_score': 90,
        'description': 'Challenging conditions for proven agents',
        
        # Arena parameters
        'max_price_move': 0.15,         # 15% max move
        'liquidity_modifier': 0.6,      # 60% liquidity
        'slippage': 0.005,              # 0.5% slippage
        'mev_simulation': True,         # Basic MEV (0.1%)
        'mev_rate': 0.001,
        'timeout_seconds': 3,           # Tighter timeout
        'stress_frequency': 0.20,       # 20% stress scenarios
        
        # Upgrade requirements
        'upgrade_fee_usd': 5,
        'upgrade_min_days': 30,
        'upgrade_min_avg_score': 70,
    },
    'omega': {
        'name': 'Omega',
        'emoji': '💀',
        'difficulty': 'Brutal',
        'max_score': 100,
        'description': 'Brutal adversarial conditions for elite agents',
        
        # Arena parameters
        'max_price_move': 0.30,         # 30% max move
        'liquidity_modifier': 0.3,      # 30% liquidity (thin)
        'slippage': 0.02,               # 2% slippage
        'mev_simulation': True,         # Aggressive MEV (0.5%)
        'mev_rate': 0.005,
        'timeout_seconds': 1,           # Strict timeout
        'stress_frequency': 0.40,       # 40% stress scenarios
        
        # No upgrade from Omega
        'upgrade_fee_usd': None,
        'upgrade_min_days': None,
        'upgrade_min_avg_score': None,
    }
}

# Tier downgrade rules
TIER_DOWNGRADE = {
    'fee_usd': 0,              # Free to downgrade
    'cooldown_days': 7,        # 7 days before can upgrade again
    'score_carry_percent': 0.5  # Keep 50% of score on tier change
}

# ============================================================================
# PRICING CONFIGURATION
# ============================================================================

# Price formula: Price = Score × PRICE_PER_POINT
PRICE_PER_POINT = 0.0001  # $0.0001 per point

# Examples:
# Score 20 (starting) = $0.0020
# Score 50 = $0.0050
# Score 75 (Alpha max) = $0.0075
# Score 100 (Omega max) = $0.0100

# Token supply per agent
TOTAL_SUPPLY = 100_000_000  # 100M tokens

# SOL price for conversions (updated periodically)
SOL_PRICE_USD = float(os.environ.get('SOL_PRICE_USD', 150))

# ============================================================================
# FEE STRUCTURE
# ============================================================================

FEES = {
    # Agent creation
    'creation_fee_usd': 12,
    'creation_breakdown': {
        'platform': 2,           # $2 platform revenue
        'arena_reserve': 5,      # $5 arena testing costs
        'liquidity_reserve': 5,  # $5 initial liquidity
    },
    
    # Trading fees
    'trading_fee_percent': 0.01,  # 1% per trade
    'trading_fee_split': {
        'platform': 0.65,         # 65% to platform
        'creator': 0.15,          # 15% to creator
        'reserve': 0.20,          # 20% to reserve
    },
    
    # Tier upgrade
    'tier_upgrade_fee_usd': 5,
}

# ============================================================================
# DECAY CONFIGURATION
# ============================================================================

DECAY = {
    'threshold_days': 7,      # Days of inactivity before decay starts
    'rate_per_week': 1,       # Points lost per week of inactivity
    'min_score': MIN_SCORE,   # Cannot decay below floor
}

# Activity that resets decay timer:
# - Trade on agent's stock (buy or sell)
# - Arena test completed

# ============================================================================
# ARENA CONFIGURATION
# ============================================================================

ARENA = {
    # Daily simulations
    'simulations_per_day': 5,
    
    # Simulation duration
    'simulation_steps': 60,           # 60 decision points per simulation
    'step_interval_seconds': 60,      # 1 minute between steps (simulated)
    
    # Window selection (regime mix)
    'regime_mix': [
        'trending',    # 1 trending (up or down)
        'volatile',    # 1 volatile/choppy
        'stress',      # 1 stress (crash, pump, liquidity crisis)
        'normal',      # 1 normal (ranging)
        'wildcard',    # 1 completely random
    ],
    
    # Starting portfolio for simulations
    'starting_balance': 10000,  # $10,000 simulated
    
    # Execution limits
    'max_execution_time_seconds': 30,  # Total time for all 5 sims
    'memory_limit_mb': 256,
    
    # Run time (UTC)
    'daily_run_hour': 0,
    'daily_run_minute': 0,
}

# ============================================================================
# REGIME CLASSIFICATIONS
# ============================================================================

REGIME_CLASSES = {
    # Trending
    'trending_up': {
        'group': 'trending',
        'benchmark_pnl': 5.0,      # Expected +5% if you follow trend
        'description': 'Price up >5% over period, consistent direction',
    },
    'trending_down': {
        'group': 'trending',
        'benchmark_pnl': -5.0,     # Expected -5% (or less loss = good)
        'description': 'Price down >5% over period, consistent direction',
    },
    
    # Volatile
    'volatile': {
        'group': 'volatile',
        'benchmark_pnl': 0.0,
        'description': 'Multiple 3%+ swings within period',
    },
    'chop': {
        'group': 'volatile',
        'benchmark_pnl': -1.0,     # Slight expected loss from chop
        'description': 'Rapid small reversals, no clear direction',
    },
    
    # Stress
    'flash_crash': {
        'group': 'stress',
        'benchmark_pnl': -15.0,    # Surviving = winning
        'description': '>10% drop in <10 minutes',
    },
    'flash_pump': {
        'group': 'stress',
        'benchmark_pnl': 10.0,
        'description': '>10% rise in <10 minutes',
    },
    'liquidity_crisis': {
        'group': 'stress',
        'benchmark_pnl': -5.0,
        'description': 'Orderbook depth drops >50%',
    },
    'cascade': {
        'group': 'stress',
        'benchmark_pnl': -20.0,
        'description': 'Liquidation cascade, multiple legs down',
    },
    'squeeze': {
        'group': 'stress',
        'benchmark_pnl': 15.0,
        'description': 'Short squeeze, rapid upward pressure',
    },
    
    # Normal
    'ranging': {
        'group': 'normal',
        'benchmark_pnl': 0.0,
        'description': 'Price within 2% band for period',
    },
    'accumulation': {
        'group': 'normal',
        'benchmark_pnl': 1.0,
        'description': 'Low volatility, slight upward bias',
    },
    'distribution': {
        'group': 'normal',
        'benchmark_pnl': -1.0,
        'description': 'Low volatility, slight downward bias',
    },
    
    # Recovery patterns
    'recovery': {
        'group': 'wildcard',
        'benchmark_pnl': 5.0,
        'description': 'Bounce back after sharp drop',
    },
    'dead_cat': {
        'group': 'wildcard',
        'benchmark_pnl': -8.0,
        'description': 'Brief bounce then continued decline',
    },
    'capitulation': {
        'group': 'wildcard',
        'benchmark_pnl': -25.0,
        'description': 'Final washout, extreme selling',
    },
    'euphoria': {
        'group': 'wildcard',
        'benchmark_pnl': 12.0,
        'description': 'Parabolic move, unsustainable buying',
    },
    'exhaustion': {
        'group': 'wildcard',
        'benchmark_pnl': -3.0,
        'description': 'End of trend, momentum fading',
    },
    'breakout': {
        'group': 'wildcard',
        'benchmark_pnl': 8.0,
        'description': 'Price breaks key level with volume',
    },
    'breakdown': {
        'group': 'wildcard',
        'benchmark_pnl': -8.0,
        'description': 'Price breaks support with volume',
    },
    'fade': {
        'group': 'wildcard',
        'benchmark_pnl': 2.0,
        'description': 'Initial move reverses',
    },
}

# Group regime classes for selection
REGIME_GROUPS = {
    'trending': ['trending_up', 'trending_down'],
    'volatile': ['volatile', 'chop'],
    'stress': ['flash_crash', 'flash_pump', 'liquidity_crisis', 'cascade', 'squeeze'],
    'normal': ['ranging', 'accumulation', 'distribution'],
    'wildcard': ['recovery', 'dead_cat', 'capitulation', 'euphoria', 'exhaustion', 'breakout', 'breakdown', 'fade'],
}

# ============================================================================
# SCORING CONFIGURATION
# ============================================================================

SCORING = {
    # Per-simulation score range
    'min_simulation_score': -0.50,
    'max_simulation_score': 1.00,
    
    # Component weights (max points)
    'components': {
        'survival': 0.30,
        'pnl': 0.25,
        'risk': 0.20,
        'quality': 0.15,
        'latency': 0.10,
    },
    
    # Survival scoring
    'survival': {
        'thresholds': [
            (0.95, 0.30),   # >95% remaining = +0.30
            (0.90, 0.25),   # >90% = +0.25
            (0.80, 0.20),   # >80% = +0.20
            (0.70, 0.15),   # >70% = +0.15
            (0.50, 0.10),   # >50% = +0.10
            (0.30, 0.05),   # >30% = +0.05
            (0.10, 0.00),   # >10% = +0.00
        ],
        'blowup_threshold': 0.10,  # <10% = blowup
        'blowup_penalty': -0.50,
    },
    
    # P&L scoring (relative to benchmark)
    'pnl': {
        'thresholds': [
            (5.0, 0.25),    # Beat benchmark by >5% = +0.25
            (3.0, 0.20),    # Beat by 3-5% = +0.20
            (1.0, 0.15),    # Beat by 1-3% = +0.15
            (-1.0, 0.10),   # Within ±1% = +0.10
            (-3.0, 0.05),   # Under by 1-3% = +0.05
            (-5.0, 0.00),   # Under by 3-5% = +0.00
        ],
        'underperform_penalties': [
            (-10.0, -0.10),  # Under by 5-10% = -0.10
            (None, -0.20),   # Under by >10% = -0.20
        ],
    },
    
    # Risk management scoring (max drawdown)
    'risk': {
        'thresholds': [
            (3.0, 0.20),    # <3% drawdown = +0.20
            (5.0, 0.15),    # <5% = +0.15
            (10.0, 0.10),   # <10% = +0.10
            (15.0, 0.05),   # <15% = +0.05
            (25.0, 0.00),   # <25% = +0.00
        ],
        'penalties': [
            (40.0, -0.10),  # 25-40% drawdown = -0.10
            (None, -0.20),  # >40% = -0.20
        ],
    },
    
    # Latency scoring (avg ms)
    'latency': {
        'thresholds': [
            (100, 0.10),    # <100ms = +0.10
            (300, 0.08),    # <300ms = +0.08
            (500, 0.05),    # <500ms = +0.05
            (1000, 0.02),   # <1000ms = +0.02
            (2000, 0.00),   # <2000ms = +0.00
        ],
        'slow_penalty': -0.05,       # >2000ms
        'timeout_penalty': -0.20,    # >2 timeouts
        'timeout_threshold': 2,
    },
    
    # Additional penalties
    'penalties': {
        'invalid_format': -0.10,     # Per occurrence
        'exception': -0.15,          # Code crash
        'erratic': -0.10,            # Flip-flopping
        'no_decisions': -0.30,       # Agent made no decisions
        'wrong_direction': -0.10,    # Bought crash / sold rally
    },
}

# ============================================================================
# DATA COLLECTION CONFIGURATION
# ============================================================================

DATA_COLLECTION = {
    # Pair selection
    'top_tier_count': 40,        # Top 40 by volume
    'mid_tier_start': 41,
    'mid_tier_end': 100,         # Positions 41-100
    'daily_top_selection': 10,   # Pick 10 from top tier
    'daily_mid_selection': 10,   # Pick 10 from mid tier
    
    # Candle storage
    'candle_interval': '1m',     # 1-minute candles
    'retention_days': 90,        # Keep 90 days of data
    
    # Regime classification
    'min_windows_per_regime': 500,   # Target per regime class
    'window_durations': [10, 30, 60, 240],  # Minutes
    
    # API rate limits
    'birdeye_requests_per_minute': 30,
    'jupiter_requests_per_minute': 60,
}

# ============================================================================
# AGENT TYPES
# ============================================================================

AGENT_TYPES = {
    'trading': {
        'label': 'Trading Agent',
        'description': 'Automated trading bots',
        'arena_type': 'trading',
    },
    'utility': {
        'label': 'Utility Agent',
        'description': 'Task automation agents',
        'arena_type': 'utility',
    },
    # V2 additions
    # 'social': {...},
    # 'defi': {...},
}

# Valid types for V1
VALID_AGENT_TYPES = ['trading', 'utility']

# ============================================================================
# AUDIT TRAIL
# ============================================================================

AUDIT = {
    # On-chain publishing
    'publish_to_chain': True,
    'chain_program_id': os.environ.get('AUDIT_PROGRAM_ID'),
    
    # Off-chain retention
    'log_retention_days': 90,
    
    # Hash format
    'hash_algorithm': 'sha256',
    'hash_truncate': 16,  # First 16 chars of hash on-chain
}

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_tier_config(tier: str) -> Dict[str, Any]:
    """Get configuration for a tier."""
    return TIERS.get(tier.lower(), TIERS['alpha'])


def get_tier_max_score(tier: str) -> int:
    """Get max score for a tier."""
    return get_tier_config(tier)['max_score']


def calculate_price(score: int) -> Dict[str, float]:
    """Calculate price from score."""
    price_usd = score * PRICE_PER_POINT
    price_sol = price_usd / SOL_PRICE_USD
    
    return {
        'score': score,
        'price_usd': price_usd,
        'price_sol': price_sol,
        'price_lamports': int(price_sol * 1_000_000_000),
        'market_cap_usd': price_usd * TOTAL_SUPPLY,
        'market_cap_sol': price_sol * TOTAL_SUPPLY,
    }


def get_regime_benchmark(regime_class: str) -> float:
    """Get benchmark P&L for a regime class."""
    regime = REGIME_CLASSES.get(regime_class, {})
    return regime.get('benchmark_pnl', 0.0)


def get_regime_group(regime_class: str) -> str:
    """Get group for a regime class."""
    regime = REGIME_CLASSES.get(regime_class, {})
    return regime.get('group', 'wildcard')


def calculate_score_change(
    current_score: int,
    raw_change: float,
    tier: str
) -> Dict[str, Any]:
    """
    Calculate new score with caps and tier ceiling.
    
    Args:
        current_score: Current score
        raw_change: Raw daily change from arena (-2.50 to +5.00)
        tier: Agent's tier
        
    Returns:
        Dict with new_score, capped_change, was_capped
    """
    # Apply daily cap
    capped_change = max(-DAILY_POINT_CAP, min(DAILY_POINT_CAP, raw_change))
    was_capped = abs(raw_change) > DAILY_POINT_CAP
    
    # Calculate new score
    new_score = current_score + capped_change
    
    # Apply tier ceiling
    tier_ceiling = get_tier_max_score(tier)
    new_score = min(new_score, tier_ceiling)
    
    # Apply floor
    new_score = max(new_score, MIN_SCORE)
    
    # Round to 1 decimal for storage
    new_score = round(new_score, 1)
    
    return {
        'previous_score': current_score,
        'raw_change': raw_change,
        'capped_change': capped_change,
        'was_capped': was_capped,
        'new_score': new_score,
        'tier_ceiling': tier_ceiling,
        'hit_ceiling': new_score >= tier_ceiling,
        'hit_floor': new_score <= MIN_SCORE,
    }


def calculate_decay(
    current_score: int,
    days_inactive: int
) -> Dict[str, Any]:
    """
    Calculate decay for inactive agents.
    
    Args:
        current_score: Current score
        days_inactive: Days since last activity
        
    Returns:
        Dict with new_score, decay_applied, decay_amount
    """
    if days_inactive < DECAY['threshold_days']:
        return {
            'new_score': current_score,
            'decay_applied': False,
            'decay_amount': 0,
            'days_inactive': days_inactive,
        }
    
    # Calculate weeks of inactivity
    weeks_inactive = days_inactive // 7
    decay_amount = weeks_inactive * DECAY['rate_per_week']
    
    # Apply decay
    new_score = current_score - decay_amount
    new_score = max(new_score, DECAY['min_score'])
    
    return {
        'new_score': round(new_score, 1),
        'decay_applied': True,
        'decay_amount': decay_amount,
        'days_inactive': days_inactive,
        'weeks_inactive': weeks_inactive,
    }


# ============================================================================
# VALIDATION
# ============================================================================

def validate_tier(tier: str) -> bool:
    """Check if tier is valid."""
    return tier.lower() in TIERS


def validate_agent_type(agent_type: str) -> bool:
    """Check if agent type is valid for V1."""
    return agent_type.lower() in VALID_AGENT_TYPES


def validate_score(score: float) -> bool:
    """Check if score is within valid range."""
    return MIN_SCORE <= score <= MAX_SCORE
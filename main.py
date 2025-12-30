"""
Tzurix MVP Backends
AI Agent Performance Exchange - Where Price = Score

Started: December 26, 2025
Network: Solana Devnet (testnet)
"""

import os
import time
import logging
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from scoring_api import scoring_bp
import requests

# ============================================================================
# CONFIGURATION
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

app.register_blueprint(scoring_bp)

# Database configuration (Railway provides DATABASE_URL)
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///tzurix_dev.db')
# Railway uses postgres:// but SQLAlchemy needs postgresql://
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# External API keys
HELIUS_API_KEY = os.environ.get('HELIUS_API_KEY')
BIRDEYE_API_KEY = os.environ.get('BIRDEYE_API_KEY')

# ============================================================================
# CORE CONSTANTS
# ============================================================================

STARTING_SCORE = 10
TOTAL_SUPPLY = 100_000_000  # 100M tokens per agent stock
DAILY_SCORE_CAP = 0.35  # ±35% max daily change

# SOL-based pricing (assuming $150/SOL baseline for initial calc)
# Starting: Score 10 = 66.7 SOL market cap = ~$10k at $150/SOL
# Formula: Price in SOL = Score × LAMPORTS_PER_SCORE_POINT / 1e9
LAMPORTS_PER_SCORE_POINT = 667  # 667 lamports per score point
# So Score 10 = 6,670 lamports = 0.00000667 SOL per token
# 100M tokens × 0.00000667 SOL = 667 SOL MC (but we want 66.7 SOL)
# Correction: 66.7 lamports per score point
LAMPORTS_PER_SCORE_POINT = 67  # 67 lamports per score point
# Score 10 = 670 lamports = 0.00000067 SOL per token
# 100M × 0.00000067 = 67 SOL MC ≈ $10k at $150/SOL ✓

SOL_PRICE_USD = 150  # For frontend USD conversion only

# ============================================================================
# DATABASE MODELS
# ============================================================================

class Agent(db.Model):
    """
    Represents a registered AI trading agent.
    Each agent gets a tokenized stock with price tied to their score.
    """
    __tablename__ = 'agents'
    
    id = db.Column(db.Integer, primary_key=True)
    wallet_address = db.Column(db.String(44), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    creator_wallet = db.Column(db.String(44), nullable=False)
    
    # Score data
    current_score = db.Column(db.Integer, default=STARTING_SCORE)
    previous_score = db.Column(db.Integer, default=STARTING_SCORE)
    
    # Token data (will be populated after Solana deployment)
    token_mint = db.Column(db.String(44))
    total_supply = db.Column(db.BigInteger, default=TOTAL_SUPPLY)
    
    # Reserve in lamports (1 SOL = 1,000,000,000 lamports)
    reserve_lamports = db.Column(db.BigInteger, default=0)
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    score_history = db.relationship('ScoreHistory', backref='agent', lazy='dynamic')
    trades = db.relationship('Trade', backref='agent', lazy='dynamic')
    
    def to_dict(self):
        """Convert agent to dictionary for JSON response."""
        price_lamports = self.current_score * LAMPORTS_PER_SCORE_POINT
        price_sol = price_lamports / 1_000_000_000
        market_cap_sol = price_sol * self.total_supply
        
        # USD values for display
        price_usd = price_sol * SOL_PRICE_USD
        market_cap_usd = market_cap_sol * SOL_PRICE_USD
        display_price = self.current_score * 0.01  # Price per 1K tokens
        
        return {
            'id': self.id,
            'wallet_address': self.wallet_address,
            'name': self.name,
            'description': self.description,
            'creator_wallet': self.creator_wallet,
            'current_score': self.current_score,
            'previous_score': self.previous_score,
            'price_lamports': price_lamports,
            'price_sol': price_sol,
            'price_usd': price_usd,
            'display_price': display_price,
            'market_cap_sol': market_cap_sol,
            'market_cap_usd': market_cap_usd,
            'token_mint': self.token_mint,
            'total_supply': self.total_supply,
            'reserve_lamports': self.reserve_lamports,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


class ScoreHistory(db.Model):
    """
    Tracks historical scores for each agent.
    Used for charts and trend analysis.
    """
    __tablename__ = 'score_history'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    
    score = db.Column(db.Integer, nullable=False)
    raw_score = db.Column(db.Integer)  # Before cap applied
    price_usd = db.Column(db.Float)
    price_sol = db.Column(db.Float)
    
    calculated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'score': self.score,
            'raw_score': self.raw_score,
            'price_usd': self.price_usd,
            'price_sol': self.price_sol,
            'calculated_at': self.calculated_at.isoformat() if self.calculated_at else None
        }


class Trade(db.Model):
    """
    Records all buy/sell transactions.
    """
    __tablename__ = 'trades'
    
    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    trader_wallet = db.Column(db.String(44), nullable=False)
    
    side = db.Column(db.String(4), nullable=False)  # 'buy' or 'sell'
    token_amount = db.Column(db.BigInteger, nullable=False)
    sol_amount = db.Column(db.BigInteger, nullable=False)  # in lamports
    price_at_trade = db.Column(db.Float)  # USD price per token
    
    tx_signature = db.Column(db.String(88))  # Solana transaction signature
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def to_dict(self):
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'trader_wallet': self.trader_wallet,
            'side': self.side,
            'token_amount': self.token_amount,
            'sol_amount': self.sol_amount,
            'price_at_trade': self.price_at_trade,
            'tx_signature': self.tx_signature,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class User(db.Model):
    """
    Simple user tracking by wallet address.
    """
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    wallet_address = db.Column(db.String(44), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    holdings = db.relationship('Holding', backref='user', lazy='dynamic')
    
    def to_dict(self):
        return {
            'id': self.id,
            'wallet_address': self.wallet_address,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class Holding(db.Model):
    """
    Tracks how many tokens each user holds for each agent.
    """
    __tablename__ = 'holdings'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    agent_id = db.Column(db.Integer, db.ForeignKey('agents.id'), nullable=False)
    
    token_amount = db.Column(db.BigInteger, default=0)
    avg_buy_price = db.Column(db.Float)  # Average price paid per token
    
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (db.UniqueConstraint('user_id', 'agent_id', name='unique_user_agent'),)
    
    def to_dict(self):
        agent = Agent.query.get(self.agent_id)
        
        # Calculate current price in SOL
        price_lamports = agent.current_score * LAMPORTS_PER_SCORE_POINT if agent else 0
        current_price_sol = price_lamports / 1_000_000_000
        current_value_sol = self.token_amount * current_price_sol
        
        # USD for display
        current_price_usd = current_price_sol * SOL_PRICE_USD
        current_value_usd = current_value_sol * SOL_PRICE_USD
        
        return {
            'id': self.id,
            'user_id': self.user_id,
            'agent_id': self.agent_id,
            'agent_name': agent.name if agent else None,
            'token_amount': self.token_amount,
            'avg_buy_price_sol': self.avg_buy_price,
            'current_price_sol': current_price_sol,
            'current_price_usd': current_price_usd,
            'current_value_sol': current_value_sol,
            'current_value_usd': current_value_usd,
            'pnl_percent': ((current_price_sol - self.avg_buy_price) / self.avg_buy_price * 100) if self.avg_buy_price else 0,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def get_sol_price_usd():
    """Fetch current SOL price from BirdEye or fallback."""
    global SOL_PRICE_USD
    
    try:
        if BIRDEYE_API_KEY:
            response = requests.get(
                "https://public-api.birdeye.so/defi/price",
                params={"address": "So11111111111111111111111111111111111111112"},
                headers={"X-API-KEY": BIRDEYE_API_KEY},
                timeout=5
            )
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    SOL_PRICE_USD = data['data']['value']
                    logger.info(f"SOL price updated: ${SOL_PRICE_USD:.2f}")
                    return SOL_PRICE_USD
    except Exception as e:
        logger.warning(f"Could not fetch SOL price: {e}")
    
    logger.info(f"Using default SOL price: ${SOL_PRICE_USD}")
    return SOL_PRICE_USD


def calculate_price(score: int) -> dict:
    """
    Calculate token price based on score.
    
    Price Formula (SOL-based): 
        Price in lamports = Score × 67 lamports
        Price in SOL = Score × 0.000000067 SOL
    
    Examples (at Score 10):
        Price = 670 lamports = 0.00000067 SOL
        MC = 100M × 0.00000067 = 67 SOL ≈ $10k at $150/SOL
    """
    price_lamports = score * LAMPORTS_PER_SCORE_POINT
    price_sol = price_lamports / 1_000_000_000
    
    # Get USD price for display (frontend use)
    sol_price_usd = get_sol_price_usd()
    price_usd = price_sol * sol_price_usd
    market_cap_sol = price_sol * TOTAL_SUPPLY
    market_cap_usd = market_cap_sol * sol_price_usd
    display_price = score * 0.01  # Price per 1K tokens
    
    return {
        'score': score,
        'price_lamports': price_lamports,
        'price_sol': price_sol,
        'price_usd': price_usd,
        'display_price': display_price,
        'market_cap_sol': market_cap_sol,
        'market_cap_usd': market_cap_usd,
        'sol_price_usd': sol_price_usd
    }


def apply_daily_cap(current_score: int, new_raw_score: int) -> int:
    """
    Apply ±35% daily cap to score changes.
    
    This protects reserve liquidity by preventing sudden large price swings.
    """
    if current_score == 0:
        return max(1, new_raw_score)
    
    # Calculate percentage change
    change_percent = (new_raw_score - current_score) / current_score
    
    # Cap at ±10%
    capped_change = max(-DAILY_SCORE_CAP, min(DAILY_SCORE_CAP, change_percent))
    
    # Calculate new score
    new_score = int(current_score * (1 + capped_change))
    
    # Minimum score is 1
    return max(1, new_score)


# ============================================================================
# API ENDPOINTS - HEALTH & INFO
# ============================================================================

@app.route('/')
def home():
    """API root - shows service info."""
    return jsonify({
        'service': 'Tzurix MVP API',
        'version': '1.0.0',
        'description': 'AI Agent Performance Exchange - Where Price = Score',
        'network': 'Solana Devnet',
        'status': 'online',
        'constants': {
            'starting_score': STARTING_SCORE,
            'price_multiplier': PRICE_MULTIPLIER,
            'total_supply': TOTAL_SUPPLY,
            'price_formula': 'Score × $0.01 per 1,000 tokens'

            'daily_score_cap': f'±{int(DAILY_SCORE_CAP * 100)}%'
        },
        'endpoints': {
            'agents': '/api/agents',
            'agent_detail': '/api/agents/<id>',
            'register_agent': 'POST /api/agents',
            'get_quote': '/api/trade/quote',
            'buy': 'POST /api/trade/buy',
            'sell': 'POST /api/trade/sell',
            'user_holdings': '/api/user/<wallet>/holdings'
        }
    })


@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': int(time.time()),
        'database': 'connected',
        'sol_price_usd': SOL_PRICE_USD
    })


# ============================================================================
# API ENDPOINTS - AGENTS
# ============================================================================

@app.route('/api/agents', methods=['GET'])
def get_agents():
    """
    List all registered agents.
    
    Query params:
        - sort: 'score', 'newest', 'name' (default: score)
        - limit: number of results (default: 50)
    """
    sort = request.args.get('sort', 'score')
    limit = min(int(request.args.get('limit', 50)), 100)
    
    query = Agent.query.filter_by(is_active=True)
    
    if sort == 'score':
        query = query.order_by(Agent.current_score.desc())
    elif sort == 'newest':
        query = query.order_by(Agent.created_at.desc())
    elif sort == 'name':
        query = query.order_by(Agent.name.asc())
    
    agents = query.limit(limit).all()
    
    return jsonify({
        'success': True,
        'count': len(agents),
        'agents': [agent.to_dict() for agent in agents]
    })


@app.route('/api/agents/<int:agent_id>', methods=['GET'])
def get_agent(agent_id):
    """Get detailed info for a specific agent."""
    agent = Agent.query.get(agent_id)
    
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    return jsonify({
        'success': True,
        'agent': agent.to_dict()
    })


@app.route('/api/agents/wallet/<wallet_address>', methods=['GET'])
def get_agent_by_wallet(wallet_address):
    """Get agent by their trading wallet address."""
    agent = Agent.query.filter_by(wallet_address=wallet_address).first()
    
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    return jsonify({
        'success': True,
        'agent': agent.to_dict()
    })


@app.route('/api/agents', methods=['POST'])
def register_agent():
    """
    Register a new AI trading agent.
    
    Request body:
    {
        "wallet_address": "AgentTradingWalletAddress",
        "name": "My Trading Bot",
        "description": "A description of what this agent does",
        "creator_wallet": "CreatorWalletAddress"
    }
    """
    data = request.get_json()
    
    # Validate required fields
    required_fields = ['wallet_address', 'name', 'creator_wallet']
    for field in required_fields:
        if not data.get(field):
            return jsonify({
                'success': False,
                'error': f'Missing required field: {field}'
            }), 400
    
    # Check if agent already exists
    existing = Agent.query.filter_by(wallet_address=data['wallet_address']).first()
    if existing:
        return jsonify({
            'success': False,
            'error': 'Agent with this wallet address already registered'
        }), 409
    
    # Create new agent
    agent = Agent(
        wallet_address=data['wallet_address'],
        name=data['name'],
        description=data.get('description', ''),
        creator_wallet=data['creator_wallet'],
        current_score=STARTING_SCORE,
        previous_score=STARTING_SCORE
    )
    
    db.session.add(agent)
    
    # Create initial score history entry
    price_data = calculate_price(STARTING_SCORE)
    history = ScoreHistory(
        agent=agent,
        score=STARTING_SCORE,
        raw_score=STARTING_SCORE,
        price_usd=price_data['price_usd'],
        price_sol=price_data['price_sol']
    )
    db.session.add(history)
    
    db.session.commit()
    
    logger.info(f"✅ New agent registered: {agent.name} ({agent.wallet_address[:8]}...)")
    
    return jsonify({
        'success': True,
        'message': 'Agent registered successfully',
        'agent': agent.to_dict()
    }), 201


@app.route('/api/agents/<int:agent_id>/score', methods=['GET'])
def get_agent_score(agent_id):
    """Get current score and price for an agent."""
    agent = Agent.query.get(agent_id)
    
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    price_data = calculate_price(agent.current_score)
    
    return jsonify({
        'success': True,
        'agent_id': agent_id,
        'name': agent.name,
        **price_data,
        'previous_score': agent.previous_score,
        'score_change_percent': ((agent.current_score - agent.previous_score) / agent.previous_score * 100) if agent.previous_score else 0
    })


@app.route('/api/agents/<int:agent_id>/history', methods=['GET'])
def get_agent_history(agent_id):
    """Get score history for an agent."""
    agent = Agent.query.get(agent_id)
    
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    # Get last 30 days of history by default
    days = int(request.args.get('days', 30))
    since = datetime.utcnow() - timedelta(days=days)
    
    history = ScoreHistory.query.filter(
        ScoreHistory.agent_id == agent_id,
        ScoreHistory.calculated_at >= since
    ).order_by(ScoreHistory.calculated_at.asc()).all()
    
    return jsonify({
        'success': True,
        'agent_id': agent_id,
        'name': agent.name,
        'history': [h.to_dict() for h in history]
    })


# ============================================================================
# API ENDPOINTS - TRADING
# ============================================================================

@app.route('/api/trade/quote', methods=['GET'])
def get_trade_quote():
    """
    Get a price quote for buying or selling.
    
    Query params:
        - agent_id: ID of the agent
        - side: 'buy' or 'sell'
        - amount: SOL amount (for buy) or token amount (for sell)
    """
    agent_id = request.args.get('agent_id', type=int)
    side = request.args.get('side', 'buy')
    amount = request.args.get('amount', type=float)
    
    if not agent_id or not amount:
        return jsonify({
            'success': False,
            'error': 'Missing agent_id or amount'
        }), 400
    
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    price_data = calculate_price(agent.current_score)
    
    if side == 'buy':
        # amount is in SOL, calculate tokens received
        sol_amount = amount
        # 1% fee
        sol_after_fee = sol_amount * 0.99
        tokens_received = int(sol_after_fee / price_data['price_sol'])
        
        return jsonify({
            'success': True,
            'side': 'buy',
            'agent_id': agent_id,
            'agent_name': agent.name,
            'sol_amount': sol_amount,
            'fee_sol': sol_amount * 0.01,
            'tokens_received': tokens_received,
            'price_per_token_lamports': price_data['price_lamports'],
            'price_per_token_sol': price_data['price_sol'],
            'price_per_token_usd': price_data['price_usd'],
            'current_score': agent.current_score
        })
    
    else:  # sell
        # amount is in tokens, calculate SOL received
        token_amount = int(amount)
        sol_before_fee = token_amount * price_data['price_sol']
        # 1% fee
        sol_received = sol_before_fee * 0.99
        
        return jsonify({
            'success': True,
            'side': 'sell',
            'agent_id': agent_id,
            'agent_name': agent.name,
            'token_amount': token_amount,
            'sol_before_fee': sol_before_fee,
            'fee_sol': sol_before_fee * 0.01,
            'sol_received': sol_received,
            'price_per_token_lamports': price_data['price_lamports'],
            'price_per_token_sol': price_data['price_sol'],
            'price_per_token_usd': price_data['price_usd'],
            'current_score': agent.current_score
        })


@app.route('/api/trade/buy', methods=['POST'])
def buy_tokens():
    """
    Buy agent tokens.
    
    Request body:
    {
        "agent_id": 1,
        "trader_wallet": "BuyerWalletAddress",
        "sol_amount": 1.5,
        "tx_signature": "SolanaTransactionSignature" (optional for testnet)
    }
    
    Note: For MVP/testnet, this is simulated. Real implementation
    will verify the Solana transaction.
    """
    data = request.get_json()
    
    agent_id = data.get('agent_id')
    trader_wallet = data.get('trader_wallet')
    sol_amount = data.get('sol_amount', 0)
    tx_signature = data.get('tx_signature')
    
    if not agent_id or not trader_wallet or sol_amount <= 0:
        return jsonify({
            'success': False,
            'error': 'Missing required fields: agent_id, trader_wallet, sol_amount'
        }), 400
    
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    # Calculate tokens (SOL-based)
    price_data = calculate_price(agent.current_score)
    sol_after_fee = sol_amount * 0.99
    tokens_received = int(sol_after_fee / price_data['price_sol'])
    fee_sol = sol_amount * 0.01
    
    # Convert to lamports
    sol_lamports = int(sol_amount * 1_000_000_000)
    
    # Get or create user
    user = User.query.filter_by(wallet_address=trader_wallet).first()
    if not user:
        user = User(wallet_address=trader_wallet)
        db.session.add(user)
        db.session.flush()
    
    # Record trade
    trade = Trade(
        agent_id=agent_id,
        trader_wallet=trader_wallet,
        side='buy',
        token_amount=tokens_received,
        sol_amount=sol_lamports,
        price_at_trade=price_data['price_sol'],  # Store SOL price
        tx_signature=tx_signature
    )
    db.session.add(trade)
    
    # Update holdings (avg price in SOL)
    holding = Holding.query.filter_by(user_id=user.id, agent_id=agent_id).first()
    if holding:
        # Update average buy price (in SOL)
        total_cost = (holding.token_amount * holding.avg_buy_price) + (tokens_received * price_data['price_sol'])
        total_tokens = holding.token_amount + tokens_received
        holding.avg_buy_price = total_cost / total_tokens if total_tokens > 0 else 0
        holding.token_amount = total_tokens
    else:
        holding = Holding(
            user_id=user.id,
            agent_id=agent_id,
            token_amount=tokens_received,
            avg_buy_price=price_data['price_sol']  # Store SOL price
        )
        db.session.add(holding)
    
    # Update agent reserve
    agent.reserve_lamports += sol_lamports
    
    db.session.commit()
    
    logger.info(f"✅ BUY: {trader_wallet[:8]}... bought {tokens_received} {agent.name} tokens for {sol_amount} SOL")
    
    return jsonify({
        'success': True,
        'message': 'Purchase successful',
        'trade': trade.to_dict(),
        'holding': holding.to_dict(),
        'sol_spent': sol_amount,
        'fee_sol': fee_sol
    })


@app.route('/api/trade/sell', methods=['POST'])
def sell_tokens():
    """
    Sell agent tokens back to the protocol.
    
    Request body:
    {
        "agent_id": 1,
        "trader_wallet": "SellerWalletAddress",
        "token_amount": 1000,
        "tx_signature": "SolanaTransactionSignature" (optional for testnet)
    }
    """
    data = request.get_json()
    
    agent_id = data.get('agent_id')
    trader_wallet = data.get('trader_wallet')
    token_amount = data.get('token_amount', 0)
    tx_signature = data.get('tx_signature')
    
    if not agent_id or not trader_wallet or token_amount <= 0:
        return jsonify({
            'success': False,
            'error': 'Missing required fields: agent_id, trader_wallet, token_amount'
        }), 400
    
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    # Check user has enough tokens
    user = User.query.filter_by(wallet_address=trader_wallet).first()
    if not user:
        return jsonify({
            'success': False,
            'error': 'User not found'
        }), 404
    
    holding = Holding.query.filter_by(user_id=user.id, agent_id=agent_id).first()
    if not holding or holding.token_amount < token_amount:
        return jsonify({
            'success': False,
            'error': 'Insufficient tokens'
        }), 400
    
    # Calculate SOL received
    price_data = calculate_price(agent.current_score)
    sol_before_fee = token_amount * price_data['price_sol']
    fee_sol = sol_before_fee * 0.01
    sol_received = sol_before_fee * 0.99
    sol_lamports = int(sol_received * 1_000_000_000)
    
    # Check reserve has enough
    if agent.reserve_lamports < sol_lamports:
        return jsonify({
            'success': False,
            'error': 'Insufficient reserve liquidity'
        }), 400
    
    # Record trade
    trade = Trade(
        agent_id=agent_id,
        trader_wallet=trader_wallet,
        side='sell',
        token_amount=token_amount,
        sol_amount=sol_lamports,
        price_at_trade=price_data['price_usd'],
        tx_signature=tx_signature
    )
    db.session.add(trade)
    
    # Update holdings
    holding.token_amount -= token_amount
    
    # Update agent reserve
    agent.reserve_lamports -= sol_lamports
    
    db.session.commit()
    
    logger.info(f"✅ SELL: {trader_wallet[:8]}... sold {token_amount} {agent.name} tokens for {sol_received:.4f} SOL")
    
    return jsonify({
        'success': True,
        'message': 'Sale successful',
        'trade': trade.to_dict(),
        'sol_received': sol_received,
        'fee_sol': fee_sol
    })


# ============================================================================
# API ENDPOINTS - USER
# ============================================================================

@app.route('/api/user/<wallet_address>', methods=['GET'])
def get_user(wallet_address):
    """Get user profile by wallet address."""
    user = User.query.filter_by(wallet_address=wallet_address).first()
    
    if not user:
        return jsonify({
            'success': False,
            'error': 'User not found'
        }), 404
    
    return jsonify({
        'success': True,
        'user': user.to_dict()
    })


@app.route('/api/user/<wallet_address>/holdings', methods=['GET'])
def get_user_holdings(wallet_address):
    """Get all token holdings for a user."""
    user = User.query.filter_by(wallet_address=wallet_address).first()
    
    if not user:
        return jsonify({
            'success': True,
            'holdings': [],
            'total_value_sol': 0,
            'total_value_usd': 0
        })
    
    holdings = Holding.query.filter_by(user_id=user.id).all()
    holdings_data = [h.to_dict() for h in holdings if h.token_amount > 0]
    
    total_value_sol = sum(h['current_value_sol'] for h in holdings_data)
    total_value_usd = sum(h['current_value_usd'] for h in holdings_data)
    
    return jsonify({
        'success': True,
        'wallet_address': wallet_address,
        'holdings': holdings_data,
        'total_value_sol': total_value_sol,
        'total_value_usd': total_value_usd
    })


# ============================================================================
# API ENDPOINTS - ADMIN / SCORING
# ============================================================================

@app.route('/api/admin/update-score', methods=['POST'])
def update_agent_score():
    """
    Update an agent's score (admin endpoint).
    
    In production, this will be called by automated scoring jobs.
    For MVP, we allow manual updates for testing.
    
    Request body:
    {
        "agent_id": 1,
        "new_score": 15,
        "admin_key": "your-admin-key"
    }
    """
    data = request.get_json()
    
    # Simple admin key check (use proper auth in production)
    admin_key = os.environ.get('ADMIN_KEY', 'tzurix-dev-admin')
    if data.get('admin_key') != admin_key:
        return jsonify({
            'success': False,
            'error': 'Unauthorized'
        }), 401
    
    agent_id = data.get('agent_id')
    new_raw_score = data.get('new_score')
    
    if not agent_id or new_raw_score is None:
        return jsonify({
            'success': False,
            'error': 'Missing agent_id or new_score'
        }), 400
    
    agent = Agent.query.get(agent_id)
    if not agent:
        return jsonify({
            'success': False,
            'error': 'Agent not found'
        }), 404
    
    # Store previous score
    agent.previous_score = agent.current_score
    
    # Apply daily cap
    new_score = apply_daily_cap(agent.current_score, new_raw_score)
    agent.current_score = new_score
    
    # Calculate new price
    price_data = calculate_price(new_score)
    
    # Record in history
    history = ScoreHistory(
        agent_id=agent_id,
        score=new_score,
        raw_score=new_raw_score,
        price_usd=price_data['price_usd'],
        price_sol=price_data['price_sol']
    )
    db.session.add(history)
    
    db.session.commit()
    
    logger.info(f"📊 Score updated: {agent.name} {agent.previous_score} → {new_score} (raw: {new_raw_score})")
    
    return jsonify({
        'success': True,
        'message': 'Score updated',
        'agent_id': agent_id,
        'previous_score': agent.previous_score,
        'raw_score': new_raw_score,
        'new_score': new_score,
        'capped': new_raw_score != new_score,
        'new_price': price_data
    })

# ============================================================================
# API ENDPOINTS - SCORING (using scoring_engine)
# ============================================================================

@app.route('/api/score/<wallet_address>', methods=['GET'])
def get_wallet_score(wallet_address):
    """
    Calculate and return score for a wallet using the scoring engine.
    This endpoint shows detailed transaction analysis.
    """
    try:
        from scoring_engine import calculate_agent_score, generate_mock_score, HELIUS_API_KEY
        
        if HELIUS_API_KEY:
            logger.info(f"Calculating score for {wallet_address[:8]}... using Helius API")
            result = calculate_agent_score(wallet_address)
            using_real_data = True
        else:
            logger.info(f"No HELIUS_API_KEY - using mock data for {wallet_address[:8]}...")
            result = generate_mock_score(wallet_address)
            using_real_data = False
        
        return jsonify({
            'success': True,
            'wallet_address': result.wallet_address,
            'raw_score': result.raw_score,
            'final_score': result.final_score,
            'previous_score': result.previous_score,
            'capped': result.capped,
            'calculated_at': result.calculated_at.isoformat(),
            'using_real_data': using_real_data,
            'metrics': {
                'total_trades': result.metrics.total_trades,
                'winning_trades': result.metrics.winning_trades,
                'losing_trades': result.metrics.losing_trades,
                'win_rate': result.metrics.win_rate,
                'total_pnl_sol': result.metrics.total_pnl_sol,
                'total_volume_sol': result.metrics.total_volume_sol,
                'avg_trade_pnl': result.metrics.avg_trade_pnl,
                'avg_hold_time_hours': result.metrics.avg_hold_time_hours,
                'trades_per_day': result.metrics.trades_per_day,
                'unique_tokens_traded': result.metrics.unique_tokens_traded,
                'largest_win_sol': result.metrics.largest_win_sol,
                'largest_loss_sol': result.metrics.largest_loss_sol,
                'risk_adjusted_return': result.metrics.risk_adjusted_return
            }
        })
    except Exception as e:
        logger.error(f"Error calculating score: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/agent/<int:agent_id>/refresh-score', methods=['POST'])
def refresh_agent_score(agent_id):
    """
    Refresh an agent's score from on-chain data.
    Fetches latest transactions and recalculates score.
    """
    try:
        from scoring_engine import calculate_agent_score, HELIUS_API_KEY
        
        agent = Agent.query.get(agent_id)
        if not agent:
            return jsonify({
                'success': False,
                'error': 'Agent not found'
            }), 404
        
        if not HELIUS_API_KEY:
            return jsonify({
                'success': False,
                'error': 'Helius API key not configured'
            }), 500
        
        # Calculate new score
        result = calculate_agent_score(
            wallet_address=agent.wallet_address,
            previous_score=agent.current_score
        )
        
        # Update agent
        agent.previous_score = agent.current_score
        agent.current_score = result.final_score
        
        # Calculate new price
        price_data = calculate_price(result.final_score)
        
        # Record in history
        history = ScoreHistory(
            agent_id=agent_id,
            score=result.final_score,
            raw_score=result.raw_score,
            price_usd=price_data['price_usd'],
            price_sol=price_data['price_sol']
        )
        db.session.add(history)
        db.session.commit()
        
        logger.info(f"📊 Score refreshed: {agent.name} {agent.previous_score} → {result.final_score}")
        
        return jsonify({
            'success': True,
            'message': 'Score refreshed from on-chain data',
            'agent': agent.to_dict(),
            'scoring_details': {
                'raw_score': result.raw_score,
                'final_score': result.final_score,
                'capped': result.capped,
                'metrics': {
                    'total_trades': result.metrics.total_trades,
                    'win_rate': result.metrics.win_rate,
                    'total_pnl_sol': result.metrics.total_pnl_sol
                }
            }
        })
    except Exception as e:
        logger.error(f"Error refreshing score: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

# ============================================================================
# DATABASE INITIALIZATION
# ============================================================================

def init_db():
    """Initialize database tables."""
    with app.app_context():
        db.create_all()
        logger.info("✅ Database tables created")


# ============================================================================
# MAIN
# ============================================================================

# Initialize database on startup
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

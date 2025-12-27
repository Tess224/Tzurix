"""
Tzurix Scoring API Routes
Integrates the scoring engine with the Flask backend.

Add these routes to your main.py or import as a blueprint.
"""

from flask import Blueprint, jsonify, request
from scoring_engine import (
    calculate_agent_score,
    generate_mock_score,
    HELIUS_API_KEY
)
import os

# Create blueprint
scoring_bp = Blueprint('scoring', __name__)

# Get admin key from environment
ADMIN_KEY = os.environ.get('ADMIN_KEY', 'tzurix-dev-admin')


@scoring_bp.route('/api/scoring/calculate', methods=['POST'])
def calculate_score():
    """
    Calculate score for an agent from on-chain data.
    
    Request body:
    {
        "wallet_address": "AgentWalletAddress",
        "previous_score": 10,  // optional, defaults to 10
        "admin_key": "your-admin-key"
    }
    
    Returns calculated score and metrics.
    """
    data = request.get_json()
    
    # Validate admin key
    if data.get('admin_key') != ADMIN_KEY:
        return jsonify({
            'success': False,
            'error': 'Unauthorized'
        }), 401
    
    wallet_address = data.get('wallet_address')
    if not wallet_address:
        return jsonify({
            'success': False,
            'error': 'Missing wallet_address'
        }), 400
    
    previous_score = data.get('previous_score', 10)
    
    # Calculate score
    if HELIUS_API_KEY:
        result = calculate_agent_score(wallet_address, previous_score)
    else:
        # Use mock data if no API key
        result = generate_mock_score(wallet_address, previous_score)
    
    # Convert metrics to dict
    metrics_dict = {
        'total_trades': result.metrics.total_trades,
        'winning_trades': result.metrics.winning_trades,
        'losing_trades': result.metrics.losing_trades,
        'total_pnl_sol': result.metrics.total_pnl_sol,
        'total_volume_sol': result.metrics.total_volume_sol,
        'win_rate': result.metrics.win_rate,
        'avg_trade_pnl': result.metrics.avg_trade_pnl,
        'largest_win_sol': result.metrics.largest_win_sol,
        'largest_loss_sol': result.metrics.largest_loss_sol,
        'unique_tokens_traded': result.metrics.unique_tokens_traded,
        'avg_hold_time_hours': result.metrics.avg_hold_time_hours,
        'trades_per_day': result.metrics.trades_per_day,
        'risk_adjusted_return': result.metrics.risk_adjusted_return
    }
    
    return jsonify({
        'success': True,
        'wallet_address': result.wallet_address,
        'raw_score': result.raw_score,
        'final_score': result.final_score,
        'previous_score': result.previous_score,
        'capped': result.capped,
        'metrics': metrics_dict,
        'calculated_at': result.calculated_at.isoformat(),
        'using_real_data': bool(HELIUS_API_KEY)
    })


@scoring_bp.route('/api/scoring/test', methods=['GET'])
def test_scoring():
    """
    Test endpoint to verify scoring engine is working.
    Uses mock data - no API key required.
    """
    test_wallet = request.args.get('wallet', '7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgAsU')
    
    result = generate_mock_score(test_wallet)
    
    return jsonify({
        'success': True,
        'message': 'Scoring engine is working (mock data)',
        'wallet_address': result.wallet_address,
        'raw_score': result.raw_score,
        'final_score': result.final_score,
        'metrics': {
            'total_trades': result.metrics.total_trades,
            'win_rate': result.metrics.win_rate,
            'total_pnl_sol': result.metrics.total_pnl_sol
        }
    })


# ============================================================================
# EXAMPLE: How to add to main.py
# ============================================================================

"""
To integrate with your main Flask app, add this to main.py:

# At the top of main.py, add:
from scoring_api import scoring_bp

# After creating the Flask app, add:
app.register_blueprint(scoring_bp)

# That's it! The routes will be available at:
# GET  /api/scoring/test
# POST /api/scoring/calculate
"""
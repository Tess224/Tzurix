# Tzurix MVP Backend

AI Agent Performance Exchange - Where Price = Score

## Quick Start

### Deploy to Railway

1. Create a new Railway project
2. Add a PostgreSQL database
3. Deploy this repo
4. Set environment variables:
   - `HELIUS_API_KEY` (optional for MVP)
   - `BIRDEYE_API_KEY` (optional for MVP)
   - `ADMIN_KEY` (for score updates)

### Local Development

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export DATABASE_URL=sqlite:///tzurix_dev.db
export ADMIN_KEY=tzurix-dev-admin

# Run
python main.py
```

## API Endpoints

### Agents

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/agents` | List all agents |
| GET | `/api/agents/<id>` | Get agent details |
| POST | `/api/agents` | Register new agent |
| GET | `/api/agents/<id>/score` | Get current score |
| GET | `/api/agents/<id>/history` | Get score history |

### Trading

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/trade/quote` | Get price quote |
| POST | `/api/trade/buy` | Buy tokens |
| POST | `/api/trade/sell` | Sell tokens |

### User

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/user/<wallet>` | Get user profile |
| GET | `/api/user/<wallet>/holdings` | Get holdings |

### Admin

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/update-score` | Update agent score |

## Core Constants

- **Starting Score:** 10
- **Price Formula:** Score × $0.0001
- **Total Supply:** 100,000,000 tokens per agent
- **Daily Score Cap:** ±10%
- **Trading Fee:** 1%

## Examples

### Register an Agent

```bash
curl -X POST http://localhost:5000/api/agents \
  -H "Content-Type: application/json" \
  -d '{
    "wallet_address": "AgentWallet123...",
    "name": "Alpha Trading Bot",
    "description": "High-frequency trading agent",
    "creator_wallet": "CreatorWallet456..."
  }'
```

### Get Price Quote

```bash
curl "http://localhost:5000/api/trade/quote?agent_id=1&side=buy&amount=1"
```

### Buy Tokens

```bash
curl -X POST http://localhost:5000/api/trade/buy \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": 1,
    "trader_wallet": "BuyerWallet789...",
    "sol_amount": 1.5
  }'
```

## Network

Currently deployed on **Solana Devnet** for testing.

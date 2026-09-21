# TradeVision AI - Developer Guide

## Table of Contents
1. [Project Overview](#project-overview)
2. [Prerequisites](#prerequisites)
3. [Installation](#installation)
4. [Environment Configuration](#environment-configuration)
5. [Running Modes](#running-modes)
   - [Paper Trading (Sandbox)](#paper-tradingsandbox)
   - [Live Trading](#live-trading)
6. [UI Credential Input Form](#ui-credential-input-form)
7. [API Endpoints](#api-endpoints)
8. [Database Model](#database-model)
9. [Troubleshooting](#troubleshooting)
10. [Conversion to PDF](#conversion-to-pdf)

---

## 1. Project Overview

TradeVision AI is an intelligent algorithmic trading software system built with Django and React. This guide covers project setup, configuration, and running in both paper trading and live trading modes.

**Key Features:**
- Django REST API backend with JWT authentication
- React frontend with role-based access control
- Zerodha Kite Connect integration (paper/live modes)
- Encrypted credential storage in database
- Per-user credential management via UI form
- Backward compatibility with `.env` environment variables

---

## 2. Prerequisites

### System Requirements
- Python 3.12+
- Node.js & npm (for React frontend)
- PostgreSQL database
- Redis server
- Virtual environment (recommended)
- Docker and Docker Compose (for containerized deployment)

### Required Software
```bash
# Install Python dependencies
pip install -r backend/requirements.txt

# Install Node.js dependencies
npm install --prefix frontend

# Database setup
# - PostgreSQL with database "tradevision_db"
# - Redis running on default port 6379
```

---

## 3. Installation

### 3.1 Backend Setup

```bash
# Navigate to backend directory
cd backend

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Apply database migrations
python3 manage.py migrate

# Create superuser (optional, for admin access)
python3 manage.py createsuperuser
```

### 3.2 Frontend Setup

```bash
# Navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Build frontend
npm run build
```

---



### 3.2 Docker Setup

```bash
# From project root
docker-compose -f infra/docker-compose.yml up -d  # Start all services

# Or use make
make up-d  # Start all services in background

# To access:
# - Backend API: http://localhost:8000
# - Frontend: http://localhost (via nginx)
# - Adminer (DB management): http://localhost:8080
```

## 4. Environment Configuration

### 4.1 Backend `.env` File

Copy the example file and fill in values:

```bash
cp .env.example .env
```

**Critical `.env` Settings:**

| Setting | Description | Required for Paper Trade? | Required for Live Trade? |
|---------|-------------|--------------------------|--------------------------|
| `BROKER_ADAPTER` | `paper` | ✅ Yes (simulator) | ✅ Yes (or `zerodha`) |
| `BROKER_ENVIRONMENT` | `sandbox` | ✅ Yes | ✅ Yes (or `live`) |
| `ALGO_REGISTRATION_ID` | SEBI registration ID | ❌ No | ✅ Required for live |
| `MARKET_DATA_PROVIDER` | `mock` | ✅ Yes | ✅ Yes (or `zerodha`) |
| `AI_PROVIDER` | `gemini` | ✅ Yes | ✅ Yes |
| `GEMINI_API_KEY` | Google Gemini key | ✅ Yes | ✅ Yes |
| `ZERODHA_API_KEY` | Zerodha API key | ❌ Empty OK | ✅ Required (live/zerodha adapter) |
| `ZERODHA_ACCESS_TOKEN` | Zerodha access token | ❌ Empty OK | ✅ Required (live) |
| `ZERODHA_API_SECRET` | Zerodha API secret | ❌ Empty OK | ✅ Required (live) |
| `ZERODHA_REQUEST_TOKEN` | Single-use request token | ❌ Empty OK | ✅ Optional (login flow) |

### 4.2 Frontend `.env` File

```env
# Frontend environment variables
VITE_API_BASE_URL=http://localhost/api/v1
VITE_WS_BASE_URL=ws://localhost/ws
VITE_APP_NAME=TradeVision AI
VITE_ENVIRONMENT=development
```

### 4.3 Database Configuration

The `.env` file includes:
```
POSTGRES_DB=tradevision_db
POSTGRES_USER=tradevision
POSTGRES_PASSWORD=tradevision_password
POSTGRES_HOST=pgbouncer
POSTGRES_PORT=6432
DATABASE_URL=postgresql://tradevision:tradevision_password@pgbouncer:6432/tradevision_db
```

---

## 5. Running Modes

### 5.1 Paper Trading (Sandbox) Mode

**Configuration** (default in `.env`):
```
BROKER_ADAPTER=paper
BROKER_ENVIRONMENT=sandbox
ZERODHA_API_KEY=(empty - OK)
ZERODHA_ACCESS_TOKEN=(empty - OK)
ZERODHA_API_SECRET=(empty - OK)
ALGO_REGISTRATION_ID=SEBI1234567890ABC
```

**How It Works:**
- The system uses the **Kite sandbox demo app** automatically
- No real API keys needed - safe for development/testing
- Connects to `https://sandbox.kite.trade` with demo credentials
- All trading is simulated - no real money at risk
- Demo credentials: API Key=`sandboxdemo`, Secret=`sandboxdemo-secret`

**To Start Paper Trading:**
```bash
cd backend
python3 manage.py runserver  # Start Django server
# Frontend: npm start (or npm run dev)
```

**Verification:**
```bash
# Check config loads correctly
DJANGO_SETTINGS_MODULE=config.settings.development python3 -c "
import os
os.environ['DJANGO_SETTINGS_MODULE']='config.settings.development'
import django
django.setup()
from core.config import config
print('Broker Adapter:', config.broker_adapter)
print('Broker Environment:', config.broker_environment)
print('Paper trading ready:', config.broker_adapter == 'paper' and config.broker_environment == 'sandbox')
"
```

### 5.2 Live Trading Mode

**Configuration** (requires SEBI registration and Zerodha keys):
```
BROKER_ADAPTER=zerodha
BROKER_ENVIRONMENT=live
ALGO_REGISTRATION_ID=YOUR_SEBI_REGISTRATION_ID  # Obtain from SEBI
ZERODHA_API_KEY=your_zerodha_api_key
ZERODHA_ACCESS_TOKEN=your_access_token (short-lived, regenerate via login flow)
ZERODHA_API_SECRET=your_api_secret
```

**Requirements for Live Trading:**
1. **SEBI Algo Trading Registration ID** - Must be obtained from SEBI
2. **Zerodha API Credentials** - API key, secret, and access token
3. **Access Token Renewal** - Access tokens are short-lived and must be regenerated via the Kite login flow
4. **Risk Management** - Proper position sizing and circuit breakers enabled

**Live Trading Workflow:**
1. User obtains SEBI registration ID
2. User gets Zerodha API credentials from https://kite.trade
3. User completes Kite login flow to get access token
4. Credentials entered via UI form (`/zerodha/credentials`) or set in `.env`
5. System switches to live broker execution

**⚠️ WARNING:** Live trading involves real money risk. Ensure proper risk management is configured before enabling.

### 5.3 Switching Between Modes

To switch from paper to live:

1. Update `.env` with live broker credentials
2. Set `ALGO_REGISTRATION_ID` (SEBI ID)
3. Set `BROKER_ADAPTER=zerodha` and `BROKER_ENVIRONMENT=live`
4. Restart the Django server
5. Or use the UI form to input credentials per-user

---

## 6. UI Credential Input Form

### 6.1 Access the Form

Navigate to: `http://localhost:3000/zerodha/credentials`

**Note:** This is a public endpoint (not RequireAuth-guarded) for onboarding.

### 6.2 Form Fields

| Field | Type | Description | Required |
|-------|------|-------------|----------|
| API Key | Password | Zerodha Kite Connect API key | ✅ Yes |
| API Secret | Password | Zerodha API secret | ✅ Yes |
| Access Token | Password | Zerodha access token (short-lived) | ✅ Yes |
| Request Token | Password (optional) | Single-use Kite request token | No |
| Product | Select | `MIS`, `CNC`, or `NRML` | Default: `MIS` |
| Environment | Select | `sandbox` or `live` | Default: `sandbox` |

### 6.3 How It Works

1. User fills in the form with Zerodha credentials
2. Form submits to `POST /api/v1/zerodha/credentials/`
3. Credentials are **encrypted at rest** using Fernet encryption (derived from Django `SECRET_KEY`)
4. Credentials are associated with the user (or stored globally if no user authenticated)
5. DB credentials take priority over `.env` environment variables
6. Success feedback shown via toast notification

### 6.4 Bulk Import from `.env`

For migrating existing `.env` credentials:

1. Navigate to: `POST /api/v1/zerodha/credentials/bulk-import/`
2. Provide JSON array of credentials:
```json
[
  {
    "api_key": "your_key",
    "api_secret": "your_secret", 
    "access_token": "your_token",
    "environment": "sandbox",
    "product": "MIS"
  }
]
```
3. Choose merge mode: `overwrite` or `merge`
4. All credentials imported and encrypted

### 6.5 Credential Priority Order

When the system needs Zerodha credentials, it checks in this order:

1. **Database (per-user credentials)** - If user is authenticated, their stored credentials are used
2. **Database (global/system credentials)** - If no user, system-wide credentials are used
3. **`.env` environment variables** - Fallback if no DB credentials exist

This ensures: `DB credentials > .env fallback` while maintaining backward compatibility.

---

## 7. API Endpoints

### 7.1 Authentication Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/auth/token/` | POST | Obtain JWT access + refresh token pair |
| `/api/v1/auth/token/refresh/` | POST | Refresh expired access token |
| `/api/v1/auth/me/` | GET | Retrieve authenticated user profile |

### 7.2 Zerodha Credential Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/zerodha/credentials/` | POST | Input single set of Zerodha credentials |
| `/api/v1/zerodha/credentials/bulk-import/` | POST | Bulk import credentials from JSON |

### 7.3 Response Formats

**Success Response (credentials input):**
```json
{
  "success": true,
  "source": "database",  // or ".env"
  "credentials": {
    "api_key": "*** masked ***",
    "environment": "sandbox",
    "product": "MIS"
  }
}
```

**Error Response:**
```json
{
  "success": false,
  "errors": {
    "api_key": ["API Key is required"],
    ...
  }
}
```

---

## 8. Database Model

### 8.1 `ZerodhaCredentials` Model

**Location:** `backend/apps/accounts/infrastructure/models.py`

**Fields:**
- `user` (ForeignKey to AUTH_USER_MODEL, nullable) - User account these credentials belong to
- `api_key` (CharField, max_length=500) - Zerodha API key (encrypted at rest)
- `api_secret` (CharField, max_length=500) - Zerodha API secret (encrypted at rest)
- `access_token` (CharField, max_length=1000) - Zerodha access token (encrypted at rest)
- `request_token` (CharField, max_length=500, nullable) - Single-use request token
- `product` (CharField, max_length=20, default="MIS") - Kite product code
- `environment` (CharField, max_length=20, default="sandbox") - Trading environment
- `is_active` (BooleanField, default=True) - Whether credentials are active
- `created_via` (CharField, max_length=20, default="ui") - Source: ui|env|admin
- `created_at` (DateTimeField, auto_now_add=True) - Creation timestamp
- `updated_at` (DateTimeField, auto_now=True) - Last modification timestamp

**Encryption:**
- All sensitive fields encrypted using **Fernet encryption**
- Encryption key derived from Django `SECRET_KEY` using SHA-256
- Fields encrypted on save, decrypted on retrieval via `get_encrypted_*()` methods

**Manager Method `get_active_credentials()`:**
```python
# Gets credentials, preferring DB over .env
credentials = ZerodhaCredentials.get_active_credentials(user=None)
# Returns dict with: api_key, api_secret, access_token, environment, source ("database" or ".env")
```

---

## 9. Troubleshooting

### 9.1 Common Issues

| Issue | Cause | Solution |
|-------|-------|----------|
| `SystemCheckError: E002` | Database name doesn't contain 'test' or 'dev' | Rename database to `tradevision_test` or update `.env` POSTGRES_DB |
| `ImproperlyConfigured: ZERODHA_API_KEY` | Django settings not loaded | Ensure `DJANGO_SETTINGS_MODULE=config.settings.development` |
| Credentials not taking effect | DB credentials not saving correctly | Ensure form validation passes (all required fields filled) |
| 401 Unauthorized on API calls | Invalid JWT token | Re-login to get fresh tokens, or check `DJANGO_SECRET_KEY` |
| Paper trading not working | Wrong broker config | Verify `BROKER_ADAPTER=paper` and `BROKER_ENVIRONMENT=sandbox` in `.env` |
| Frontend can't connect to API | CORS or base URL mismatch | Check `VITE_API_BASE_URL` matches backend URL |

### 9.2 Database Migrations

If you modify models, run:
```bash
cd backend
python3 manage.py makemigrations accounts
python3 manage.py migrate accounts
```

### 9.3 Regenerating Access Tokens

Access tokens are short-lived. To regenerate:
1. Visit: `https://sandbox.kite.trade/connect/login?api_key=sandboxdemo`
2. Complete the login flow
3. Exchange request token for access token via the adapter
4. Or use the UI form to input new credentials

---

## 10. Conversion to PDF

### Option 1: Using Markdown PDF

If you have Pandoc installed:
```bash
pandoc DEVELOPER_GUIDE.md -s -o DEVELOPER_GUIDE.pdf
```

If you have `markdown-pdf` npm package:
```bash
cd frontend
npm install -g markdown-pdf
markdown-pdf DEVELOPER_GUIDE.md -o DEVELOPER_GUIDE.pdf
```

### Option 2: Using Python

```bash
pip install pdfkit
pdfkit.from_file('DEVELOPER_GUIDE.md', 'DEVELOPER_GUIDE.pdf')
```

### Option 3: Manual Conversion

1. Open `DEVELOPER_GUIDE.md` in your preferred markdown editor
2. Use the editor's "Export as PDF" feature
3. Or copy content into Google Docs/Word and export to PDF

### Option 3: VS Code

If you have the "Markdown PDF" extension installed in VS Code:
1. Open the markdown file
2. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on Mac)
3. Type "Markdown PDF: Export (pdf)" and select it
4. PDF will be generated in the same directory

---

## Quick Start Checklist

### For Paper Trading (Recommended Start):
- [ ] Copy `.env.example` to `.env` and fill basic Django settings
- [ ] Start PostgreSQL and Redis
- [ ] Run `python3 manage.py migrate`
- [ ] Verify `BROKER_ADAPTER=paper` and `BROKER_ENVIRONMENT=sandbox`
- [ ] Start Django: `python3 manage.py runserver`
- [ ] Start Frontend: `npm start` in frontend directory
- [ ] Access: `http://localhost:3000`
- [ ] Test: Navigate to `/zerodha/credentials` form (optional, for future use)

### For Live Trading:
- [ ] Obtain SEBI Algo Trading Registration ID
- [ ] Get Zerodha API credentials from https://kite.trade
- [ ] Complete Kite login flow for access token
- [ ] Update `.env` with live credentials
- [ ] Set `ALGO_REGISTRATION_ID`
- [ ] Set `BROKER_ADAPTER=zerodha` and `BROKER_ENVIRONMENT=live`
- [ ] 🚨 **Ensure risk management is configured**
- [ ] Restart server and test

---
*Generated: 2026-09-21*

## 5.3 Running with Docker


### 5.2 Running with Docker

#### Using make commands:

```bash
# Start all services (foreground - shows logs)
make up

# Start all services (background, detached)
make up-d

# Stop all services
make down

# Restart all services
make restart

# View service status
make ps

# Access the application:
# - API: http://localhost:8000
# - Frontend: http://localhost (nginx reverse proxy on port 80)
# - Flower (Celery monitor): http://localhost:5555
# - Adminer (DB): http://localhost:8080

# View logs:
make logs          # All services
make logs-backend  # Backend only
make logs-celery   # Celery workers
```

#### Manual docker-compose:

```bash
# Start
docker-compose -f infra/docker-compose.yml up -d

# Stop
docker-compose -f infra/docker-compose.yml down

# Restart
docker-compose -f infra/docker-compose.yml restart

# Rebuild images
make build

# Rebuild and start
make up-d
```

#### Development workflow:

```bash
# Make changes to source code - they're bind-mounted, so containers pick them up automatically

# To run specific services:
make bash          # Open bash in backend container
make shell         # Open Django shell

# Run tests
make test          # Full test suite
make test-fast     # Fast tests (exclude slow integration)
```
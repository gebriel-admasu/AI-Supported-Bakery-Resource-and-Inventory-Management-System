# AI-Supported Bakery Resource and Inventory Management System

A web-based system for bakeries with centralized production and multiple sales outlets. Features ingredient and inventory management, recipe and batch production planning, multi-store sales tracking, costing and profit analysis, AI-based demand forecasting, and automated model retraining.

## Tech Stack

- **Backend:** Python / FastAPI, SQLAlchemy, Alembic, Celery
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS
- **Database:** PostgreSQL 15
- **Cache / Broker:** Redis 7
- **AI/ML:** Scikit-learn, pandas, NumPy

## Project Structure

```
├── backend/          # FastAPI backend (API, business logic, models)
├── frontend/         # React + TypeScript frontend (Vite)
├── ai_service/       # AI demand forecasting microservice
├── .env.example      # Environment variable template
└── README.md
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 15
- Redis 7 (optional, for Celery tasks)

### Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install dependencies
pip install -r requirements.txt

# Copy environment variables
copy ..\.env.example ..\.env  # Windows
# cp ../.env.example ../.env  # macOS/Linux

# Create the database
# Make sure PostgreSQL is running, then create the bakery_db database

# Run migrations
alembic upgrade head

# Start the backend server
uvicorn app.main:app --reload --port 8000
```

The API docs are available at http://localhost:8000/docs

### Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start the dev server
npm run dev
```

The frontend runs at http://localhost:5173 and proxies API requests to the backend.

### AI Service Setup

```bash
cd ai_service

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start the AI service
uvicorn app.main:app --reload --port 8001
```

## User Roles

| Role | Description |
|------|-------------|
| **Admin** | System configuration, user management |
| **Owner** | Full access, financial oversight, approvals |
| **Production Manager** | Production planning, recipes, ingredient intake |
| **Store Manager** | Sales entry, opening/closing stock, receipt confirmation |

## Implementation Phases

1. **Foundation** - Project scaffold, database, auth setup
2. **Authentication** - JWT auth, RBAC, user management
3. **Inventory** - Ingredients, stock tracking, threshold alerts
4. **Recipes** - Recipe CRUD, versioning, cost calculation
5. **Production** - Batch planning, ingredient deduction
6. **Distribution** - Dispatch, receipt confirmation, transit tracking
7. **Sales** - Daily open/sell/close workflow, wastage
8. **Financials** - COGS, P&L, margin analysis
9. **Suppliers** - Purchase orders, reorder suggestions
10. **Reports** - Dashboards, export, trend analysis
11. **AI Forecasting** - Demand prediction model
12. **MLOps** - Automated retraining pipeline
13. **Testing & Deployment** - Tests, security, performance


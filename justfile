# Salesforce ADK Agent Engine Deployment Manager

# Default env file (override with: just --set env '.env.production')
env := ".env"

# List available recipes
default:
    @just --list

# Create a new Agent Engine deployment
create *args:
    uv run python main.py --env-file {{ env }} create {{ args }}

# Update an existing Agent Engine deployment
update *args:
    uv run python main.py --env-file {{ env }} update {{ args }}

# Delete an Agent Engine deployment
delete *args:
    uv run python main.py --env-file {{ env }} delete {{ args }}

# Get Agent Engine deployment details
get *args:
    uv run python main.py --env-file {{ env }} get {{ args }}

# List Agent Engine deployments
list *args:
    uv run python main.py --env-file {{ env }} list {{ args }}

# --- Shorthand deploy commands (environment name → .env.{name}) ---

# Deploy (create) to an environment: just deploy production
deploy environment *args:
    uv run python main.py --env-file .env.{{ environment }} create {{ args }}

# Update a deployment: just deploy-update production
deploy-update environment *args:
    uv run python main.py --env-file .env.{{ environment }} update {{ args }}

# Delete a deployment: just deploy-delete production -y
deploy-delete environment *args:
    uv run python main.py --env-file .env.{{ environment }} delete {{ args }}

# Get deployment details: just deploy-get production
deploy-get environment *args:
    uv run python main.py --env-file .env.{{ environment }} get {{ args }}

# --- Dev tools ---

# Lint with ruff
lint:
    uv run ruff check .

# Format with ruff
fmt:
    uv run ruff format .

# Type check with pyright
typecheck:
    uv run pyright

# Run all checks (lint + typecheck)
check: lint typecheck

# Run tests
test *args:
    uv run pytest {{ args }}

# Install dependencies
install:
    uv sync

# Install with dev dependencies
install-dev:
    uv sync --group dev

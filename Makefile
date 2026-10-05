.PHONY: setup up down logs health test test-backend test-frontend lint dev-backend dev-frontend deps infra

# Values from .env (ports, models, database login) for the targets that run on the host.
# .env is plain KEY=value, so the shell can read it as is.
LOAD_ENV = set -a; [ -f .env ] && . ./.env; set +a

setup: .env    ## create .env with a random JWT secret

.env:
	python3 -c "import pathlib, re, secrets; text = pathlib.Path('.env.example').read_text(encoding='utf-8'); pathlib.Path('.env').write_text(re.sub(r'(?m)^JWT_SECRET=.*', 'JWT_SECRET=' + secrets.token_urlsafe(48), text), encoding='utf-8')"
	@echo "created .env with a random JWT_SECRET"

up: .env       ## everything in docker
	docker compose up --build -d
	@$(LOAD_ENV); echo "open http://localhost:$${WEB_PORT:-8080}  (API health: http://localhost:$${API_PORT:-8000}/api/health)"

down:
	docker compose down

logs:
	docker compose logs -f backend

health:
	@$(LOAD_ENV); curl -s http://localhost:$${API_PORT:-8000}/api/health | python3 -m json.tool

deps:          ## local dev deps
	cd backend && python3 -m pip install -r requirements-dev.txt
	cd frontend && npm install

infra: .env    ## just the data stores + ollama, for running the app on the host
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis qdrant ollama ollama-pull

dev-backend:   ## the API on :8000 with reload, talking to the infra containers
	@$(LOAD_ENV); \
	export DATABASE_URL="$${DATABASE_URL:-postgresql+asyncpg://$${POSTGRES_USER:-app}:$${POSTGRES_PASSWORD:-app}@localhost:5432/$${POSTGRES_DB:-diffsage}}"; \
	export REDIS_URL="$${REDIS_URL:-redis://localhost:6379/0}" QDRANT_URL="$${QDRANT_URL:-http://localhost:6333}"; \
	export PROVIDERS__OLLAMA__BASE_URL="http://localhost:$${OLLAMA_PORT:-11434}" PROVIDERS__OLLAMA__MODEL="$${OLLAMA_MODEL:-qwen2.5-coder:7b}"; \
	cd backend && alembic upgrade head && uvicorn app.main:create_app --factory --reload --port 8000

dev-frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && python3 -m pytest -q

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ruff check app tests

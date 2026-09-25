.PHONY: up down logs test test-backend test-frontend lint dev-backend dev-frontend deps infra

up:            ## everything in docker
	docker compose up --build -d
	@echo "open http://localhost:8080  (API health: http://localhost:8000/api/health)"

down:
	docker compose down

logs:
	docker compose logs -f backend

deps:          ## local dev deps
	cd backend && python -m pip install -r requirements-dev.txt
	cd frontend && npm install

infra:         ## just the data stores + ollama, for running the app on the host
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d postgres redis qdrant ollama ollama-pull

dev-backend:
	cd backend && alembic upgrade head && uvicorn app.main:create_app --factory --reload --port 8000  # ollama is on localhost:$${OLLAMA_PORT:-11434} via the compose port mapping

dev-frontend:
	cd frontend && npm run dev

test: test-backend test-frontend

test-backend:
	cd backend && python -m pytest -q

test-frontend:
	cd frontend && npm test

lint:
	cd backend && ruff check app tests

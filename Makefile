.PHONY: install dev test test-backend studio

install:
	@echo "Installing dependencies..."
	# TODO: implement install commands (e.g. uv sync or pip install)

dev:
	@echo "Starting dev server..."
	# TODO: implement dev server start (e.g. uvicorn app.main:app --reload)

test:
	@echo "Running all tests..."
	$(MAKE) test-backend
	cd frontend && npm run build

test-backend:
	@echo "Running backend tests..."
	cd backend && uv run --frozen pytest

studio:
	@echo "Starting langgraph studio..."
	# TODO: implement langgraph studio start

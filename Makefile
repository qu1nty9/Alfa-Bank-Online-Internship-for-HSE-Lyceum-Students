.PHONY: install test run docker-build docker-up docker-down

install:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

test:
	.venv/bin/python -m pytest -q

run:
	PYTHONPATH=.:src .venv/bin/uvicorn api.main:app --reload

docker-build:
	docker compose build

docker-up:
	docker compose up

docker-down:
	docker compose down

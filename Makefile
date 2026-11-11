.PHONY: install pipeline api test docker

install:
	pip install -r requirements.txt

pipeline:
	PYTHONPATH=src python -m energy.pipeline

api:
	PYTHONPATH=src uvicorn energy.api.main:app --reload

test:
	pytest -v

docker:
	docker compose up --build

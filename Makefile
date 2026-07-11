.PHONY: install test run adk mcp docker-build docker-run

install:
	python3 -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

test:
	PYTHONPATH=. pytest -q

run:
	streamlit run streamlit_app/app.py --server.port 8501

adk:
	adk web fridgechef_adk

mcp:
	python -m mcp_server.server

docker-build:
	docker build -t fridgechef-ai .

docker-run:
	docker run --env-file .env -p 8080:8080 fridgechef-ai

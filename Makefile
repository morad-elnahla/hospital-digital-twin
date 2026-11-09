.PHONY: run test schema build-db forecast-evaluation

run:
	python app.py

# Run each test file in a fresh process to keep memory use bounded.
test: build-db
	python scripts/run_tests.py

schema:
	python db/generate_schema.py

build-db: schema
	python -m db.build_db
	python -m db.evaluate_forecasts
	python -m db.validate_data

forecast-evaluation:
	python -m db.evaluate_forecasts

.PHONY: run test schema build-db

run:
	@if [ ! -f runtime/hdt.sqlite ]; then python -m db.build_db; fi
	python app.py

# Run each test file in a fresh process to keep memory use bounded.
test: build-db
	@for test in tests/test_*.py; do PYTHONPATH=. python "$$test" || exit 1; done

schema:
	python db/generate_schema.py

build-db: schema
	python -m db.build_db
	python -m db.validate_data

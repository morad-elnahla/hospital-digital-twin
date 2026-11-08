.PHONY: run test build-db

run:
	python app.py

# Run each test file in a fresh process to keep memory use bounded.
test:
	@for test in tests/test_*.py; do PYTHONPATH=. python "$$test" || exit 1; done

# Added in Phase 1; the target is declared now so the project interface is stable.
build-db:
	python db/build_db.py

#!/usr/bin/env sh
set -eu
if [ ! -f runtime/hdt.sqlite ]; then
  python -m db.generate_schema
  python -m db.build_db
  python -m db.evaluate_forecasts
  python -m db.validate_data
fi
exec python app.py

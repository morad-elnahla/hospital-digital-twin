@echo off
setlocal
if not exist runtime\hdt.sqlite (
  py -3 -m db.generate_schema || exit /b 1
  py -3 -m db.build_db || exit /b 1
  py -3 -m db.evaluate_forecasts || exit /b 1
  py -3 -m db.validate_data || exit /b 1
)
py -3 app.py

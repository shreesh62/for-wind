$env:DISTANCEMATRIX_BASE='http://127.0.0.1:5001/maps/api'
$env:GEOCODE_BASE='http://127.0.0.1:5001/maps/api'
$env:WEATHER_BASE='http://127.0.0.1:5001'
Start-Process -FilePath .\.venv312\Scripts\python -ArgumentList 'tests\mocks\mock_api.py' -WindowStyle Hidden
Start-Sleep -Seconds 2
.\.venv312\Scripts\python -m pytest -q

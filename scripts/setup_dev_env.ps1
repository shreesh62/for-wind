if (-not (Test-Path ".\.venv312\Scripts\python.exe")) {
    py -3.12 -m venv --copies .venv312
}
.\.venv312\Scripts\python -m pip install --upgrade pip
.\.venv312\Scripts\python -m pip install -r requirements.txt
.\.venv312\Scripts\python -m pip install -r requirements-dev.txt
.\.venv312\Scripts\python -m playwright install

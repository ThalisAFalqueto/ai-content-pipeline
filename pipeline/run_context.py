from datetime import datetime
from pathlib import Path

from config import OUTPUT_DIR


def new_run_dir() -> Path:
    run_dir = OUTPUT_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir.mkdir(parents=True)
    return run_dir


def latest_run_dir() -> Path:
    runs = sorted(p for p in OUTPUT_DIR.iterdir() if p.is_dir())
    if not runs:
        raise FileNotFoundError(f"Nenhuma execução encontrada em {OUTPUT_DIR}")
    return runs[-1]

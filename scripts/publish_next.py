import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import OUTPUT_DIR  # noqa: E402
from pipeline import publish_youtube  # noqa: E402

HORARIO_MINIMO = 11  # hora local (0-23); não publica antes disso


def all_manifests() -> list[dict]:
    manifests = []
    for run_dir in sorted(OUTPUT_DIR.iterdir()):
        manifest_path = run_dir / "manifest.json"
        if manifest_path.exists():
            manifests.append(json.loads(manifest_path.read_text(encoding="utf-8")))
    return manifests


def already_published_today() -> bool:
    today = date.today().isoformat()
    return any(
        m.get("publicado") and m.get("data_publicacao", "").startswith(today)
        for m in all_manifests()
    )


def find_next_run() -> Path | None:
    runs = sorted(p for p in OUTPUT_DIR.iterdir() if p.is_dir())
    for run_dir in runs:
        manifest_path = run_dir / "manifest.json"
        video_path = run_dir / "video_final.mp4"
        if not manifest_path.exists() or not video_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("publicado"):
            return run_dir
    return None


def main() -> None:
    if datetime.now().hour < HORARIO_MINIMO:
        print(f"Ainda não são {HORARIO_MINIMO}h, aguardando o horário programado.")
        return

    if already_published_today():
        print("Já publicamos algo hoje, esperando o próximo dia.")
        return

    run_dir = find_next_run()
    if run_dir is None:
        print("Nenhuma run pendente de publicação encontrada.")
        return

    video_id = publish_youtube.run(run_dir=run_dir, privacy_status="public")

    manifest_path = run_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["publicado"] = True
    manifest["video_id"] = video_id
    manifest["data_publicacao"] = date.today().isoformat()
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Publicado: {run_dir}")


if __name__ == "__main__":
    main()

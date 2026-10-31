import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import ideation, narration, publish_youtube, render, transcribe, visuals_ai  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Roda o pipeline completo: ideação -> narração -> legendas -> visual -> render -> publicação")
    parser.add_argument("--topic", help="Tópico específico (ignora a fila em data/topics.md)")
    parser.add_argument("--dry-run", "--skip-publish", dest="skip_publish", action="store_true", help="Gera tudo, mas não publica no YouTube")
    parser.add_argument("--public", action="store_true", help="Publica como público em vez de 'unlisted'")
    args = parser.parse_args()

    run_dir = ideation.run(topic=args.topic)
    narration.run(run_dir=run_dir)
    transcribe.run(run_dir=run_dir)
    visuals_ai.run(run_dir=run_dir)
    render.run(run_dir=run_dir)

    manifest = {
        "run_dir": str(run_dir),
        "publicado": False,
        "video_id": None,
    }

    if args.skip_publish:
        print(f"\nTudo pronto em {run_dir}. Publicação pulada (--dry-run). Revise o video_final.mp4 antes de publicar manualmente.")
    else:
        video_id = publish_youtube.run(run_dir=run_dir, privacy_status="public" if args.public else "unlisted")
        manifest["publicado"] = True
        manifest["video_id"] = video_id

    (run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

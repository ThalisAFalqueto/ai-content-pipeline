import argparse
import json
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from auth.youtube_oauth import get_credentials
from pipeline.run_context import latest_run_dir

CATEGORY_ID_SCIENCE_TECH = "28"


def upload(video_path: Path, titulo: str, descricao: str, privacy_status: str) -> str:
    creds = get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    request = youtube.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": titulo,
                "description": descricao,
                "categoryId": CATEGORY_ID_SCIENCE_TECH,
            },
            "status": {"privacyStatus": privacy_status},
        },
        media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
    )

    response = None
    while response is None:
        _, response = request.next_chunk()

    return response["id"]


def run(run_dir: Path | None = None, privacy_status: str = "unlisted") -> str:
    run_dir = run_dir or latest_run_dir()
    roteiro = json.loads((run_dir / "roteiro.json").read_text(encoding="utf-8"))
    video_path = run_dir / "video_final.mp4"

    video_id = upload(video_path, roteiro["titulo"], roteiro["descricao"], privacy_status)
    url = f"https://youtube.com/shorts/{video_id}"

    print(f"Publicado ({privacy_status}): {url}")
    return video_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 6 — publica o vídeo no YouTube")
    parser.add_argument("--run-dir", help="Pasta da execução (padrão: a mais recente em data/output/)")
    parser.add_argument(
        "--public", action="store_true",
        help="Publica como público. Por padrão, publica como 'unlisted' (recomendado até validar o fluxo).",
    )
    args = parser.parse_args()
    run(
        run_dir=Path(args.run_dir) if args.run_dir else None,
        privacy_status="public" if args.public else "unlisted",
    )

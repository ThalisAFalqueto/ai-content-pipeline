import argparse
import json
from pathlib import Path

from elevenlabs.client import ElevenLabs

from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
from pipeline.run_context import latest_run_dir

MODEL_ID = "eleven_multilingual_v2"


def synthesize(script_audio: str, output_path: Path) -> None:
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    audio_stream = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=script_audio,
        model_id=MODEL_ID,
        output_format="mp3_44100_128",
    )
    with open(output_path, "wb") as f:
        for chunk in audio_stream:
            f.write(chunk)


def run(run_dir: Path | None = None) -> Path:
    run_dir = run_dir or latest_run_dir()
    roteiro = json.loads((run_dir / "roteiro.json").read_text(encoding="utf-8"))

    output_path = run_dir / "narracao.mp3"
    synthesize(roteiro["script_audio"], output_path)

    print(f"Narração gerada: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 2 — gera a narração (ElevenLabs)")
    parser.add_argument("--run-dir", help="Pasta da execução (padrão: a mais recente em data/output/)")
    args = parser.parse_args()
    run(run_dir=Path(args.run_dir) if args.run_dir else None)

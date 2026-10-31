import argparse
import json
import re
from pathlib import Path

from faster_whisper import WhisperModel

from pipeline.run_context import latest_run_dir

MAX_WORDS_PER_LINE = 4
MAX_LINE_DURATION = 2.2  # segundos

BREAK_TAG_RE = re.compile(r"<break[^>]*/>")

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Arial Black,90,&H00FFFFFF,&H0000D7FF,&H00000000,&H00000000,-1,0,0,0,100,100,0,0,1,6,0,2,80,80,400,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def seconds_to_ass_time(seconds: float) -> str:
    centiseconds = round(seconds * 100)
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def transcribe_words(audio_path: Path, initial_prompt: str | None = None) -> list[dict]:
    model = WhisperModel("small", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(
        str(audio_path), language="pt", word_timestamps=True, initial_prompt=initial_prompt
    )

    words = []
    for segment in segments:
        for word in segment.words:
            words.append({"text": word.word.strip(), "start": word.start, "end": word.end})
    return words


def words_to_lines(words: list[dict]) -> list[list[dict]]:
    lines: list[list[dict]] = []
    current: list[dict] = []

    for word in words:
        if current and (
            len(current) >= MAX_WORDS_PER_LINE
            or word["end"] - current[0]["start"] > MAX_LINE_DURATION
        ):
            lines.append(current)
            current = []
        current.append(word)

    if current:
        lines.append(current)
    return lines


def line_to_ass_dialogue(line: list[dict]) -> str:
    start = seconds_to_ass_time(line[0]["start"])
    end = seconds_to_ass_time(line[-1]["end"])

    karaoke_text = ""
    for word in line:
        duration_cs = max(round((word["end"] - word["start"]) * 100), 1)
        karaoke_text += f"{{\\k{duration_cs}}}{word['text']} "

    return f"Dialogue: 0,{start},{end},Karaoke,,0,0,0,,{karaoke_text.strip()}"


def build_ass(words: list[dict]) -> str:
    lines = words_to_lines(words)
    dialogues = "\n".join(line_to_ass_dialogue(line) for line in lines)
    return ASS_HEADER + dialogues + "\n"


def run(run_dir: Path | None = None) -> Path:
    run_dir = run_dir or latest_run_dir()
    audio_path = run_dir / "narracao.mp3"
    roteiro = json.loads((run_dir / "roteiro.json").read_text(encoding="utf-8"))
    initial_prompt = BREAK_TAG_RE.sub("", roteiro["script_audio"])

    words = transcribe_words(audio_path, initial_prompt=initial_prompt)
    ass_content = build_ass(words)

    output_path = run_dir / "legendas.ass"
    output_path.write_text(ass_content, encoding="utf-8")

    words_path = run_dir / "palavras.json"
    words_path.write_text(json.dumps(words, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Legendas geradas: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 3 — transcreve e gera legendas .ass (faster-whisper local)")
    parser.add_argument("--run-dir", help="Pasta da execução (padrão: a mais recente em data/output/)")
    args = parser.parse_args()
    run(run_dir=Path(args.run_dir) if args.run_dir else None)

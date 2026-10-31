import argparse
import json
import re
import subprocess
from pathlib import Path

from config import VIDEO_HEIGHT, VIDEO_WIDTH
from pipeline.run_context import latest_run_dir

FPS = 30
ZOOM_PER_FRAME = 0.0015
MAX_ZOOM = 1.3
MIN_SCENE_DURATION = 0.3  # segundos

BREAK_TAG_RE = re.compile(r"<break[^>]*/>")


def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path),
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def render_scene_segment(image_path: Path, duration: float, out_path: Path) -> None:
    frames = max(round(duration * FPS), 1)
    upscale_width = VIDEO_WIDTH * 4
    zoompan = (
        f"scale={upscale_width}:-2,"
        f"zoompan=z='min(zoom+{ZOOM_PER_FRAME},{MAX_ZOOM})':d={frames}:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:fps={FPS}"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(image_path),
            "-vf", zoompan, "-t", str(duration),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path),
        ],
        check=True, capture_output=True,
    )


def word_count(texto: str) -> int:
    return len(BREAK_TAG_RE.sub("", texto).split())


def compute_scene_durations(cenas: list[dict], words: list[dict], total_duration: float) -> list[float]:
    """Aloca a duração de cada cena proporcionalmente à contagem de palavras do seu
    texto_correspondente, usando fronteiras de tempo cumulativas (0 -> total_duration)
    sobre a linha do tempo real transcrita em palavras.json — cada cena vai até o início
    da fala da próxima (absorvendo pausas/breaks nela), e a última vai até o fim do áudio.
    Isso garante soma(durações) == total_duration, sem perder tempo nas pausas entre cenas.
    Cai no split igualitário (fallback) se não houver transcrição ou o intervalo resultante
    for degenerado."""
    fallback = total_duration / len(cenas)
    if not words:
        return [fallback] * len(cenas)

    expected_counts = [max(word_count(cena["texto_correspondente"]), 1) for cena in cenas]
    total_expected = sum(expected_counts)
    ratio = len(words) / total_expected

    cumulative = 0
    start_indices = []
    for count in expected_counts:
        start_indices.append(min(round(cumulative * ratio), len(words) - 1))
        cumulative += count

    time_bounds = [0.0] + [words[idx]["start"] for idx in start_indices[1:]] + [total_duration]

    durations = []
    for i in range(len(cenas)):
        duration = time_bounds[i + 1] - time_bounds[i]
        durations.append(duration if duration >= MIN_SCENE_DURATION else fallback)

    return durations


def concat_segments(segment_paths: list[Path], out_path: Path, tmp_dir: Path) -> None:
    filelist = tmp_dir / "filelist.txt"
    filelist.write_text("\n".join(f"file '{p.resolve()}'" for p in segment_paths), encoding="utf-8")
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(filelist), "-c", "copy", str(out_path)],
        check=True, capture_output=True,
    )


def mux_audio(video_path: Path, audio_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path), "-i", str(audio_path),
            "-c:v", "copy", "-c:a", "aac", "-shortest", str(out_path),
        ],
        check=True, capture_output=True,
    )


def burn_subtitles(video_path: Path, ass_path: Path, out_path: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(video_path),
            "-vf", f"ass={ass_path}",
            "-c:v", "libx264", "-c:a", "copy", str(out_path),
        ],
        check=True, capture_output=True,
    )


def run(run_dir: Path | None = None) -> Path:
    run_dir = run_dir or latest_run_dir()
    roteiro = json.loads((run_dir / "roteiro.json").read_text(encoding="utf-8"))

    audio_path = run_dir / "narracao.mp3"
    ass_path = run_dir / "legendas.ass"
    words_path = run_dir / "palavras.json"
    visuals_dir = run_dir / "visuals"
    tmp_dir = run_dir / "tmp"
    tmp_dir.mkdir(exist_ok=True)

    cenas = roteiro["cenas"]
    total_duration = get_audio_duration(audio_path)
    words = json.loads(words_path.read_text(encoding="utf-8")) if words_path.exists() else []
    scene_durations = compute_scene_durations(cenas, words, total_duration)

    segment_paths = []
    for cena, duration in zip(cenas, scene_durations):
        image_path = visuals_dir / f"cena_{cena['ordem']:02d}.jpg"
        segment_path = tmp_dir / f"segment_{cena['ordem']:02d}.mp4"
        render_scene_segment(image_path, duration, segment_path)
        segment_paths.append(segment_path)

    concat_path = tmp_dir / "concat.mp4"
    concat_segments(segment_paths, concat_path, tmp_dir)

    with_audio_path = tmp_dir / "with_audio.mp4"
    mux_audio(concat_path, audio_path, with_audio_path)

    final_path = run_dir / "video_final.mp4"
    burn_subtitles(with_audio_path, ass_path, final_path)

    print(f"Vídeo final: {final_path}")
    return final_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 5 — compõe o vídeo final (ffmpeg)")
    parser.add_argument("--run-dir", help="Pasta da execução (padrão: a mais recente em data/output/)")
    args = parser.parse_args()
    run(run_dir=Path(args.run_dir) if args.run_dir else None)

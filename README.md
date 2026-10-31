# Pipeline de conteúdo faceless — estilo "Mesa Infinita"

Automação do fluxo: ideação -> narração -> legendas -> mídia visual -> render -> publicação no YouTube.

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencher as chaves
```

Requer `ffmpeg` instalado no sistema (`sudo apt install ffmpeg`).

## Etapas (cada uma roda isolada via CLI própria)

1. `python -m pipeline.ideation` — gera roteiro (GPT-5.6-sol) a partir do próximo tópico pendente em `data/topics.md`
2. `python -m pipeline.narration` — gera narração (ElevenLabs) a partir do roteiro
3. `python -m pipeline.transcribe` — gera legendas `.ass` (faster-whisper local)
4. `python -m pipeline.visuals_ai` — gera mídia por cena via IA (Gemini 2.5 Flash Image)
5. `python -m pipeline.render` — compõe o vídeo final vertical (ffmpeg)
6. `python -m pipeline.publish_youtube` — sobe o vídeo pro YouTube (OAuth)

## Rodar tudo de uma vez

```
python scripts/run_daily.py --dry-run          # gera tudo, não publica
python scripts/run_daily.py --skip-publish      # gera tudo, não publica (alias)
python scripts/run_daily.py                     # gera e publica no YouTube
```

Cada execução cria uma pasta em `data/output/<timestamp>/` com `roteiro.json`, `narracao.mp3`, `legendas.ass`, `video_final.mp4` e `manifest.json` — revise antes de publicar manualmente no Instagram/TikTok.

## Credenciais necessárias

| Variável | Onde conseguir |
|---|---|
| `OPENAI_API_KEY` | platform.openai.com |
| `GEMINI_API_KEY` | aistudio.google.com (billing pré-pago pra uso além do tier gratuito) |
| `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` | elevenlabs.io |
| `YOUTUBE_OAUTH_CLIENT_SECRET_FILE` | Google Cloud Console > Credenciais > Criar credenciais > ID do cliente OAuth (tipo "Aplicativo para computador") — diferente da API key de leitura já usada no MCP |

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## O que é

Pipeline de automação de conteúdo faceless para YouTube Shorts, no estilo do canal "Mesa Infinita" (vídeos de curiosidade científica/engenharia). Fluxo: ideação -> narração -> legendas -> mídia visual -> render -> publicação.

## Setup

```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencher as chaves
```

Requer `ffmpeg` instalado no sistema (`sudo apt install ffmpeg`).

## Comandos

Cada etapa roda isolada via CLI própria, sempre operando sobre a run mais recente em `data/output/` (ou `--run-dir` explícito):

```
python -m pipeline.ideation [--topic "..."]        # Etapa 1: roteiro (GPT-5.6-sol) a partir do próximo tópico pendente em data/topics.md
python -m pipeline.narration [--run-dir ...]       # Etapa 2: narração (ElevenLabs)
python -m pipeline.transcribe [--run-dir ...]      # Etapa 3: legendas .ass (faster-whisper local)
python -m pipeline.visuals_ai [--run-dir ...]      # Etapa 4: gera mídia por cena via IA (Gemini 2.5 Flash Image)
python -m pipeline.render [--run-dir ...]          # Etapa 5: compõe o vídeo final vertical (ffmpeg)
python -m pipeline.publish_youtube [--run-dir ...] [--public]  # Etapa 6: sobe pro YouTube (OAuth); padrão de privacidade é "unlisted"

python scripts/run_daily.py [--topic ...] [--dry-run|--skip-publish] [--public]  # roda o pipeline inteiro em sequência

python -m auth.youtube_oauth   # autoriza o OAuth do YouTube manualmente e salva o token em auth/token.json
```

Não há testes, linter ou build configurados neste projeto.

## Arquitetura

- Cada etapa (`pipeline/*.py`) é independente: lê o estado da última "run" em `data/output/<timestamp>/`, faz seu trabalho, escreve seu artefato de saída na mesma pasta. Isso permite rodar/reexecutar qualquer etapa isoladamente via CLI, ou tudo de uma vez via `scripts/run_daily.py`.
- `pipeline/run_context.py` é o contrato entre as etapas: `new_run_dir()` cria `data/output/<timestamp>/` (só a ideação chama isso), `latest_run_dir()` localiza a run mais recente (todas as demais etapas usam isso por padrão via `--run-dir` opcional).
- `roteiro.json` é o artefato central, gerado pela ideação e consumido por todas as etapas seguintes: `titulo`/`descricao` na publicação, `script_audio` na narração, `cenas` (com `descricao_visual` e `ordem`) na geração de imagens e composição do vídeo. Os 4 campos são obrigatórios e validados em `pipeline/ideation.py`.
- `pipeline/visuals_ai.py` gera uma imagem por cena via Gemini (`gemini-2.5-flash-image`) — substituiu uma versão anterior baseada em busca de banco de imagens (Pixabay), que retornava resultados sem relação com a cena. A cena 1 é gerada do zero com `STYLE_TEMPLATE` (render 3D estilo "objeto sobre mesa de madeira", imitando o visual do canal de referência); as cenas seguintes são geradas como edição multi-imagem, passando a cena 1 (âncora, mantém o estilo) e a cena anterior (continuidade) como referência — mantém consistência visual entre cenas sem o custo/deriva de mandar o histórico inteiro ou só uma imagem por vez (ver `REFERENCE_WINDOW`-equivalente: `anchor_image` + `last_image`).
- `pipeline/ideation.py` valida cada roteiro gerado com um segundo LLM (`validate_roteiro()`, crítico contra as regras da fórmula) antes de aceitar — se reprovado, regenera com o motivo da reprovação como feedback, até `MAX_TENTATIVAS` vezes; se esgotar as tentativas, segue com a última versão mesmo assim e avisa no log.
- `config.py` centraliza todas as env vars e paths derivados de `ROOT_DIR`; os módulos importam dali em vez de ler `os.environ` diretamente.
- `prompts/ideation_system_prompt.md` define a "fórmula" do roteiro (hook -> sequência de tentativas -> solução -> frase de efeito) com regras rígidas e exemplos few-shot — é o principal ponto de ajuste de qualidade do conteúdo gerado. Mudanças no formato de saída JSON do LLM devem manter esse contrato com `pipeline/ideation.py`.
- `data/topics.md` é a fila de tópicos pendentes (`- [ ]` / `- [x]`); `ideation.py` consome o primeiro pendente e marca como feito ao gerar o roteiro.
- `auth/youtube_oauth.py` gerencia o fluxo OAuth do YouTube (token cacheado em `auth/token.json`, renovado automaticamente quando expira, senão abre fluxo interativo local).

# Histórico do projeto — Pipeline "Mesa Infinita"

Registro de tudo que foi construído, decidido e aprendido ao longo do desenvolvimento deste pipeline de vídeos faceless pro YouTube Shorts. Mantido como referência pra não repetir os mesmos erros nem redescobrir as mesmas soluções.

## Objetivo

Automatizar a produção de vídeos curtos de curiosidade científica/engenharia no estilo do canal real **Mesa Infinita** (`@mesainfinita-j3i`, 42k inscritos, 15M+ views em 15 vídeos): roteiro → narração → legendas → imagens → render → publicação no YouTube Shorts do canal **Mente Infinita** (`@infinitamentexyz`), criado pelo usuário.

## Linha do tempo

### Setup inicial
- Criado `CLAUDE.md` documentando a arquitetura do pipeline (etapas independentes, `roteiro.json` como artefato central, `run_context.py` como contrato entre etapas).
- Primeira tentativa de rodar o pipeline: `ffmpeg` não estava instalado e o `sudo` não tinha como pedir senha pelo terminal do Claude Code. Solução: baixado o `.deb` do `ffmpeg` via `apt-get download` (sem root) e extraído os binários direto pra `~/.local/bin`, aproveitando que as bibliotecas (`libavcodec` etc.) já estavam no sistema.

### Round 1 — Pixabay → geração de imagem via IA
- Pipeline original buscava imagens no banco Pixabay (`pipeline/visuals_stock.py`) — resultados batiam pouco com a cena descrita (imagens de castelo, ovo pintado, garrafas, sem relação com o roteiro).
- Pesquisado o canal de referência real via MCP do YouTube: confirmado que o estilo visual deles é **render 3D de objeto sobre mesa de madeira**, não foto de banco.
- Trocado por `pipeline/visuals_ai.py`, gerando imagem por cena via OpenAI Images (`gpt-image-1.5`) com um `STYLE_TEMPLATE` fixo. Pixabay removido do projeto.

### Round 2-3 — Sincronia de áudio e imagem
- Primeiro teste real: vídeo com só 6 cenas, duração de áudio abaixo da meta, e o final cortado (perdia ~1s do áudio).
- Causa do corte: `pipeline/render.py` calculava a duração de cada cena de forma independente (do início ao fim das palavras faladas), perdendo o silêncio *entre* cenas — a soma nunca batia com a duração real do áudio, e o `ffmpeg -shortest` cortava a sobra.
- Corrigido pra usar **fronteiras de tempo cumulativas** (cada cena vai até o início da próxima, a última vai até o fim do áudio) — elimina a perda por completo.
- `pipeline/transcribe.py` passou a salvar `palavras.json` (timestamps reais do faster-whisper) pra `render.py` usar em vez de dividir a duração igualmente entre cenas.

### Round 4 — Automatizar a publicação
- OAuth do YouTube: primeira tentativa falhou porque a conta não estava na lista de testadores do app OAuth (projeto em modo "Testing" no Google Cloud). Resolvido adicionando o e-mail como testador.
- Configurado cron do sistema (`crontab`) pra publicar 1 vídeo por dia — não geração diária, já que gerar todos de uma vez e só espaçar a *publicação* fazia mais sentido.
- **Bug real descoberto**: cron de horário fixo não roda se a máquina estiver desligada no minuto exato — 2 dias seguidos sem publicar porque o computador não estava ligado às 12h. Corrigido trocando pra cron de **hora em hora** + um guard no código (`já publicamos algo hoje?`) que garante no máximo 1 publicação por dia, pegando a primeira janela em que a máquina estiver ligada.
- Depois, a pedido do usuário, adicionada uma trava de horário mínimo (11h) no código — mantém a resiliência do cron de hora em hora mas só publica a partir das 11h.

### Round 5 — Consistência visual entre cenas
- Cada imagem era gerada 100% independente — mesmo estilo "no papel", mas ângulo de câmera, mesa e iluminação mudavam a cada cena.
- Testado `images.edit()` da OpenAI com **todo o histórico de imagens anteriores** como referência — funcionou bem visualmente, mas o custo cresce em progressão (cena N manda N-1 imagens): um vídeo de 12 cenas mandava 66 imagens de referência ao todo. Isso custou ~$6 em 2-3 vídeos de teste — muito acima do estimado.
- Ajustado pra janela de 3 imagens, depois testado com só 1 (a mais recente) — essa última causou **deriva visual** perceptível ao longo do vídeo (cenas finais saíam bem diferentes do estilo inicial).
- **Migração pra Gemini** (`gemini-2.5-flash-image`, "nano banana"): mais barato (~$0,039/imagem vs. o que a OpenAI cobrava com histórico) e nativamente melhor em consistência de personagem/objeto entre imagens. Desenhado como: cena 1 gera do zero, cenas seguintes editam a partir de **2 referências fixas** (âncora = cena 1, + cena mais recente) — resolve custo e deriva ao mesmo tempo.
- Confirmado por comparação direta: assinatura de app do Gemini (Google One "AI Pro") **não inclui** créditos de API — são sistemas de billing separados. A API é paga à parte via Google AI Studio (billing pré-pago).

### Round 6 — Qualidade do roteiro
- Usuário comparou nosso vídeo do motor a jato com o vídeo real do Mesa Infinita sobre o mesmo assunto (`Dá pra fazer um avião voar com um balão?`, 111s, 2,5M views). Roteiro nosso ficou abaixo do nível deles.
- Comparação cruzada com 3 transcrições reais (balão, SSD, torneira) identificou 3 padrões consistentes que faltavam:
  1. Cada falha precisa nomear o motivo **físico/mecânico exato** (não "dificultava o uso").
  2. A solução final precisa revelar uma **sacada elegante** (ciclo autossustentável, virada conceitual) — não só descrever o que ela faz.
  3. A frase de fechamento nunca pode ser um resumo técnico — precisa ser uma imagem final memorável.
- Adicionado `validate_roteiro()` em `pipeline/ideation.py`: um segundo LLM age como crítico contra essas regras (+ regras já existentes: jargão explicado, progressão de tentativas, hook, cenas diferenciáveis), com retry automático (feedback do crítico volta pro gerador) até `MAX_TENTATIVAS`.
- Adicionadas 2 checagens **por código** (não confiar no LLM pra contar): tamanho mínimo de palavras (180, pra bater a meta de 75-110s) e quantidade mínima de cenas (proporcional ao tamanho do roteiro, ~1 cena a cada 12-15 palavras) — LLMs não são confiáveis em tarefas de contagem exata.
- Mesmo com essas regras, o GPT-4o não convergia de forma confiável em todos os critérios simultaneamente (ficava trocando um problema por outro a cada tentativa). Trocado o modelo de ideação pra **GPT-5.6-sol** (flagship atual da OpenAI, desenhado pra lidar melhor com restrições complexas simultâneas) — resultado: roteiro do motor a jato v6 saiu com 111s (quase idêntico ao vídeo real), 17 cenas, e um fechamento genuinamente poético ("O fogo mantém o compressor, e o compressor mantém o fogo... nasceu um vento que nunca para").
- Também corrigido um bug de robustez: quando a resposta do LLM vinha com o JSON incompleto (faltando o campo `cenas`), o pipeline quebrava com uma exceção não tratada em vez de tratar como mais uma tentativa reprovada.

## Decisões de arquitetura (estado atual)

- **Ideação**: GPT-5.6-sol, com crítico automatizado (`validate_roteiro`) e expansão de cenas em etapa separada quando necessário (`expandir_cenas` — só recorta o texto já aprovado em mais cenas, sem competir com as regras de conteúdo).
- **Narração**: ElevenLabs (`eleven_multilingual_v2`), plano Starter ($6/mês, ~30k caracteres). Tags `<break time="0.3s"/>` no roteiro pra pausas dramáticas.
- **Legendas**: faster-whisper local (modelo "small"), com o `script_audio` real passado como `initial_prompt` pra melhorar precisão de termos técnicos.
- **Imagens**: Gemini 2.5 Flash Image, âncora + última imagem como referência.
- **Render**: ffmpeg local, zoompan + fronteiras de tempo cumulativas por cena.
- **Publicação**: cron de hora em hora + guard de 1x/dia + trava de horário mínimo (11h), sempre público (decisão explícita do usuário).

## Custo estimado por vídeo (atualizado)

| Etapa | Custo |
|---|---|
| Ideação + validador (GPT-5.6-sol, pior caso 5 tentativas) | ~$0,35–0,50 |
| Narração (ElevenLabs) | ~$0 incremental (dentro do plano, mas roteiros maiores apertam o limite mensal) |
| Imagens (Gemini, 16-19 cenas) | ~$0,55–0,70 |
| Transcrição + Render (local) | $0 |
| **Total por vídeo** | **~$0,90–1,20** |

## Vídeos produzidos até agora

| Run | Tópico | Status |
|---|---|---|
| `20260806-100006` | Ponte suspensa (amortecedor de massa) | Publicado (dia 1) |
| `20260806-100546` | Freios do carro | Publicado (pelo cron) |
| `20260809-165840` | Motor a jato | Publicado (manual, mesmo dia dos freios) |
| `20260809-180953` | Zíper | Na fila |
| `20260809-184204` | Elevador (freio Otis) | Na fila |
| `20260809-185408` | Tampa de garrafa PET | Na fila |
| `20260809-190252` | Caneta | Na fila |
| `20260809-190936` | Velcro | Na fila |

## Lições aprendidas (pra não repetir)

1. **Sempre desconfiar de estimativa de custo "no papel"** — o design de mandar todo o histórico de imagens como referência parecia razoável até rodar de verdade e custar $6 em 2 vídeos.
2. **LLM não conta bem** — qualquer restrição numérica (tamanho, quantidade de cenas) precisa de checagem determinística em código, não só pedir educadamente no prompt.
3. **Cron de horário fixo é frágil em máquina que não fica sempre ligada** — cron de intervalo curto + guard de "já fiz isso hoje?" é mais robusto que mirar um minuto exato.
4. **Comparar com múltiplos exemplos reais antes de generalizar uma regra** — a primeira hipótese sobre o "hook cotidiano" (baseada só no vídeo do balão) não se sustentou quando comparada com SSD e torneira.
5. **Backup antes de sobrescrever, sempre** — várias vezes precisamos comparar "antes vs. depois" de uma mudança; nem sempre lembramos de fazer o backup a tempo (perdemos a versão antiga do motor a jato uma vez).

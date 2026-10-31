import argparse
import json
import re
from pathlib import Path

from openai import OpenAI

from config import IDEATION_PROMPT_FILE, OPENAI_API_KEY, TOPICS_FILE
from pipeline.run_context import new_run_dir

MODEL = "gpt-5.6-sol"
MAX_TENTATIVAS = 5

VALIDATOR_SYSTEM_PROMPT = """Você é um crítico rigoroso de roteiros para o canal "Mesa Infinita" (curiosidade científica/de engenharia). Avalie o roteiro abaixo contra estas regras obrigatórias da fórmula do canal:

1. Cada tentativa (exceto a primeira menção do problema) deve nomear o motivo FÍSICO/MECÂNICO EXATO da falha, nunca uma consequência vaga (proibido: "dificultava o uso", "não funcionou bem", "ficou complicado"). O espectador precisa conseguir visualizar exatamente o que quebrou ou não funcionou.
2. Deve haver pelo menos 3 tentativas distintas antes da solução final, com progressão real de complexidade (cada uma mais sofisticada que a anterior, não uma lista plana de ideias soltas).
3. Cada "descricao_visual" deve ser visualmente diferenciável das outras cenas do roteiro — evite repetir o mesmo enquadramento/objeto com variação mínima entre cenas.
4. O hook não pode ser "hoje vamos falar sobre..." nem equivalente.
5. A solução final precisa revelar o que é especificamente engenhoso nela — uma virada conceitual, um ciclo que se autossustenta, ou um truque que resolve dois problemas de uma vez. Não é aceitável só descrever funcionalmente o que a solução faz sem explicar por que ela é inteligente.
6. A frase de fechamento não pode ser um resumo técnico/funcional (proibido: "é assim que evitamos que o motor pare"). Precisa ser uma imagem final, revelação ou virada de frase memorável.
7. Nenhum termo técnico/jargão (ex: "arrasto", "turbocharger", "torque", nomes de peças específicas) pode aparecer sem uma explicação visual ou contextual na mesma frase ou na seguinte — o espectador leigo precisa entender o que a palavra significa sem precisar já saber do assunto. Se algum termo assim aparecer sem explicação, reprove.

Responda apenas com um JSON válido, sem markdown ao redor:
{"aprovado": true ou false, "motivo": "se reprovado, explique especificamente o que falhou e o que precisa mudar; se aprovado, string vazia"}
"""

SCENE_SPLIT_SYSTEM_PROMPT = """Você recebe um roteiro já aprovado (título, script_audio, cenas) e precisa apenas RECORTAR o script_audio em mais cenas menores, sem alterar uma palavra do texto original.

Regra: gere aproximadamente 1 cena a cada 12-15 palavras do script_audio, cobrindo o texto inteiro sem sobrepor nem pular trechos. Cada cena continua precisando de uma descricao_visual concreta e visualmente diferenciável das outras (objeto/mecanismo isolado, adequado pra um render 3D sobre mesa de madeira).

Responda apenas com um JSON válido, sem markdown ao redor, no mesmo formato do roteiro original (título e script_audio idênticos ao original, só a lista de cenas muda):
{"titulo": "...", "descricao": "", "script_audio": "... (idêntico ao original)", "cenas": [{"ordem": 1, "texto_correspondente": "...", "descricao_visual": "..."}]}
"""

TAMANHO_MINIMO_PALAVRAS = 180
PALAVRAS_POR_CENA_MAXIMO = 18  # abaixo disso (menos cenas que isso) o roteiro fica pouco dinâmico
BREAK_TAG_RE = re.compile(r"<break[^>]*/>")


def next_pending_topic() -> str:
    lines = TOPICS_FILE.read_text(encoding="utf-8").splitlines()
    for line in lines:
        match = re.match(r"^- \[ \] (.+)$", line.strip())
        if match:
            return match.group(1).strip()
    raise RuntimeError(f"Nenhum tópico pendente em {TOPICS_FILE}")


def mark_topic_done(topic: str) -> None:
    text = TOPICS_FILE.read_text(encoding="utf-8")
    updated = text.replace(f"- [ ] {topic}", f"- [x] {topic}", 1)
    TOPICS_FILE.write_text(updated, encoding="utf-8")


def generate_script(topic: str, feedback: str | None = None) -> dict:
    client = OpenAI(api_key=OPENAI_API_KEY)
    system_prompt = IDEATION_PROMPT_FILE.read_text(encoding="utf-8")

    user_content = f"Tópico: {topic}\n\nGere o roteiro completo em JSON conforme as instruções."
    if feedback:
        user_content += (
            f"\n\nUma tentativa anterior foi rejeitada por um crítico pelo seguinte motivo: {feedback}\n"
            "Gere um roteiro novo corrigindo especificamente esse problema."
        )

    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    roteiro = json.loads(response.choices[0].message.content)

    for field in ("titulo", "descricao", "script_audio", "cenas"):
        if field not in roteiro:
            raise ValueError(f"Campo obrigatório ausente na resposta do LLM: {field}")

    return roteiro


def validate_roteiro(roteiro: dict) -> tuple[bool, str]:
    contagem = len(BREAK_TAG_RE.sub("", roteiro["script_audio"]).split())
    if contagem < TAMANHO_MINIMO_PALAVRAS:
        return False, f"Roteiro tem apenas {contagem} palavras, abaixo do mínimo de {TAMANHO_MINIMO_PALAVRAS} necessário pra atingir 75-110s de narração."

    num_cenas = len(roteiro["cenas"])
    cenas_minimo = contagem // PALAVRAS_POR_CENA_MAXIMO
    if num_cenas < cenas_minimo:
        return False, (
            f"Roteiro tem só {num_cenas} cenas pra {contagem} palavras (média de "
            f"{contagem / num_cenas:.0f} palavras/cena) — precisa de pelo menos {cenas_minimo} cenas "
            f"(aproximadamente 1 cena a cada 12-15 palavras) pra manter o vídeo dinâmico."
        )

    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": VALIDATOR_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(roteiro, ensure_ascii=False)},
        ],
    )
    resultado = json.loads(response.choices[0].message.content)
    return bool(resultado.get("aprovado")), resultado.get("motivo", "")


def expandir_cenas(roteiro: dict) -> dict:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SCENE_SPLIT_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(roteiro, ensure_ascii=False)},
        ],
    )
    novo_roteiro = json.loads(response.choices[0].message.content)

    for field in ("titulo", "descricao", "script_audio", "cenas"):
        if field not in novo_roteiro:
            raise ValueError(f"Campo obrigatório ausente na resposta do LLM: {field}")

    return novo_roteiro


def run(topic: str | None = None) -> Path:
    topic = topic or next_pending_topic()

    feedback = None
    roteiro = None
    for tentativa in range(1, MAX_TENTATIVAS + 1):
        try:
            roteiro = generate_script(topic, feedback=feedback)
        except ValueError as erro:
            print(f"Resposta do LLM malformada (tentativa {tentativa}/{MAX_TENTATIVAS}): {erro}")
            feedback = f"A resposta anterior veio malformada: {erro}. Gere o JSON completo com todos os campos obrigatórios."
            continue

        aprovado, motivo = validate_roteiro(roteiro)
        if aprovado:
            break
        print(f"Roteiro reprovado pelo crítico (tentativa {tentativa}/{MAX_TENTATIVAS}): {motivo}")
        feedback = motivo
    else:
        print(f"Aviso: roteiro não passou na validação após {MAX_TENTATIVAS} tentativas. Seguindo com a última versão mesmo assim.")

    if roteiro is None:
        raise RuntimeError(f"Não foi possível gerar um roteiro válido após {MAX_TENTATIVAS} tentativas.")

    contagem_final = len(BREAK_TAG_RE.sub("", roteiro["script_audio"]).split())
    cenas_alvo = contagem_final // PALAVRAS_POR_CENA_MAXIMO
    if len(roteiro["cenas"]) < cenas_alvo:
        print(f"Expandindo cenas: roteiro tem {len(roteiro['cenas'])}, alvo é {cenas_alvo}+ (etapa separada, não mexe no texto).")
        try:
            roteiro_expandido = expandir_cenas(roteiro)
            if len(roteiro_expandido["cenas"]) > len(roteiro["cenas"]):
                roteiro = roteiro_expandido
                print(f"Cenas expandidas pra {len(roteiro['cenas'])}.")
            else:
                print("Expansão não aumentou a quantidade de cenas, mantendo original.")
        except (ValueError, KeyError) as erro:
            print(f"Falha ao expandir cenas, mantendo original: {erro}")

    roteiro["topico_origem"] = topic

    run_dir = new_run_dir()
    (run_dir / "roteiro.json").write_text(
        json.dumps(roteiro, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    mark_topic_done(topic)

    print(f"Roteiro gerado: {run_dir / 'roteiro.json'}")
    print(f"Título: {roteiro['titulo']}")
    return run_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 1 — gera o roteiro (GPT-5.6-sol)")
    parser.add_argument("--topic", help="Tópico específico (ignora a fila em data/topics.md)")
    args = parser.parse_args()
    run(topic=args.topic)

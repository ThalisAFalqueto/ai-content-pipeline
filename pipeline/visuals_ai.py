import argparse
import base64
import io
import json
from pathlib import Path

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from openai import OpenAI
from PIL import Image

from config import GEMINI_API_KEY, OPENAI_API_KEY
from pipeline.run_context import latest_run_dir

MODEL = "gemini-2.5-flash-image"
CRITIC_MODEL = "gpt-5.6-sol"
STYLE_TEMPLATE = (
    "3D render fotorrealista, estilo product visualization, objeto principal "
    "preenchendo a maior parte do quadro vertical, sem grandes áreas vazias acima "
    "ou abaixo dele, sobre uma mesa de madeira rústica, fundo desfocado escuro tipo "
    "estúdio, iluminação cinematográfica dramática, profundidade de campo rasa, "
    "sem texto, sem marca d'água, composição vertical. Represente exatamente os "
    "elementos descritos na cena, sem adicionar formas, objetos ou detalhes que "
    "não foram pedidos. Cena: "
)
EDIT_PROMPT_TEMPLATE = (
    "As imagens anteriores mostram a primeira cena deste vídeo (imagem-âncora, define "
    "o estilo) e a cena mais recente já gerada. Mantenha exatamente o mesmo estilo de "
    "render 3D, a mesma mesa de madeira, iluminação e fundo estabelecidos nelas, e "
    "sempre preencha a maior parte do quadro vertical com o objeto principal, sem "
    "grandes áreas vazias acima ou abaixo. O ângulo de câmera pode mudar quando a "
    "cena pedir isso explicitamente (ex.: um close-up, uma vista de baixo, um corte "
    "lateral) — mas nunca represente o objeto de cabeça para baixo ou numa pose "
    "fisicamente contraditória em relação a como ele foi estabelecido. Gere a "
    "próxima cena da sequência mostrando: {descricao}. Represente exatamente os "
    "elementos descritos, sem adicionar formas, objetos ou detalhes que não foram "
    "pedidos. Sem texto, sem marca d'água."
)
CRITIC_PROMPT_TEMPLATE = (
    "Avalie esta imagem gerada para uma cena de vídeo. A cena deveria mostrar: "
    "\"{descricao}\".\n\n"
    "Reprove SOMENTE se: (1) a imagem contém alguma forma, mancha ou elemento visual "
    "incoerente/malformado que não corresponde a nada reconhecível (ex.: uma massa "
    "disforme, um objeto com anatomia/estrutura impossível); (2) a imagem contradiz "
    "ou ignora completamente o que foi descrito (mostra outro objeto, ou falta o "
    "elemento central da cena).\n"
    "NÃO reprove por imprecisão de enquadramento, ângulo de câmera, distância, ou "
    "por diferença em relação a outras cenas do vídeo — só reprove defeito visual "
    "claro ou erro grave de conteúdo. Na dúvida, aprove.\n\n"
    "Responda em JSON: {{\"aprovado\": bool, \"motivo\": \"...\"}}"
)
PLANNER_PROMPT_TEMPLATE = (
    "Você prepara o prompt de geração de imagem para uma cena de vídeo vertical "
    "(estilo render 3D de produto sobre mesa de madeira). A cena original pede: "
    "\"{descricao}\".\n\n"
    "Reescreva essa descrição seguindo estas regras:\n"
    "1. Se a descrição pede uma sequência/transição (ex.: \"passando de X para Y\", "
    "\"começando a fazer Z\"), escolha UM único instante representativo e descreva "
    "apenas esse instante — uma imagem estática não consegue mostrar duas etapas ao "
    "mesmo tempo.\n"
    "2. Sempre especifique o enquadramento exato (close-up extremo, close-up, plano "
    "médio) e o ângulo de câmera mais adequado ao objeto descrito — nunca deixe "
    "implícito. Se o enquadramento pedir close-up, deixe claro que o objeto deve "
    "preencher a maior parte do quadro vertical, sem grandes áreas vazias acima ou "
    "abaixo.\n"
    "3. Se o objeto ou peça descrita for pouco familiar/técnica, acrescente uma "
    "breve descrição física concreta (formato, tamanho relativo, posição) pra "
    "reduzir ambiguidade pro gerador de imagem.\n"
    "4. Mantenha o significado original — não mude o que a cena representa, só a "
    "clareza de como descrevê-la visualmente. Não adicione elementos que não "
    "estavam na descrição original.\n\n"
    "Responda em JSON: {{\"prompt\": \"...\"}}"
)
IMAGE_CONFIG = types.ImageConfig(aspect_ratio="9:16")


def png_to_jpeg(png_bytes: bytes) -> bytes:
    image = Image.open(io.BytesIO(png_bytes)).convert("RGB")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


MAX_TENTATIVAS_IMAGEM = 3


def extract_image(response) -> bytes:
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            return png_to_jpeg(part.inline_data.data)
    texto = " ".join(part.text for part in response.candidates[0].content.parts if part.text)
    raise RuntimeError(f"Gemini não retornou imagem (finish_reason={response.candidates[0].finish_reason}). Texto: {texto}")


def call_with_retry(fn, *args):
    ultimo_erro = None
    for tentativa in range(1, MAX_TENTATIVAS_IMAGEM + 1):
        try:
            return fn(*args)
        # ServerError (503) é sobrecarga temporária do Gemini, vale retentar;
        # ClientError (ex.: 429 de saldo/quota) não se resolve retentando.
        except (RuntimeError, genai_errors.ServerError) as erro:
            ultimo_erro = erro
            print(f"Falha ao gerar imagem (tentativa {tentativa}/{MAX_TENTATIVAS_IMAGEM}): {erro}")
    raise RuntimeError(f"Falha ao gerar imagem após {MAX_TENTATIVAS_IMAGEM} tentativas: {ultimo_erro}")


def generate_first_image(descricao_visual: str, client: genai.Client, feedback: str | None = None) -> bytes:
    descricao = descricao_visual
    if feedback:
        descricao += f"\n\nCORREÇÃO NECESSÁRIA: a tentativa anterior falhou pelo seguinte motivo: {feedback}. Gere a imagem corrigindo isso."
    response = client.models.generate_content(
        model=MODEL,
        contents=[STYLE_TEMPLATE + descricao],
        config=types.GenerateContentConfig(image_config=IMAGE_CONFIG),
    )
    return extract_image(response)


def generate_next_image(
    descricao_visual: str, anchor_image: bytes, last_image: bytes, client: genai.Client, feedback: str | None = None
) -> bytes:
    descricao = descricao_visual
    if feedback:
        descricao += f"\n\nCORREÇÃO NECESSÁRIA: a tentativa anterior falhou pelo seguinte motivo: {feedback}. Gere a imagem corrigindo isso."
    reference_images = [anchor_image] if last_image == anchor_image else [anchor_image, last_image]
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg") for image_bytes in reference_images
    ]
    contents.append(EDIT_PROMPT_TEMPLATE.format(descricao=descricao))

    response = client.models.generate_content(
        model=MODEL,
        contents=contents,
        config=types.GenerateContentConfig(image_config=IMAGE_CONFIG),
    )
    return extract_image(response)


def plan_prompt(descricao_visual: str) -> str:
    client = OpenAI(api_key=OPENAI_API_KEY)
    response = client.chat.completions.create(
        model=CRITIC_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {"role": "user", "content": PLANNER_PROMPT_TEMPLATE.format(descricao=descricao_visual)},
        ],
    )
    resultado = json.loads(response.choices[0].message.content)
    return resultado.get("prompt") or descricao_visual


def critique_image(image_bytes: bytes, descricao_visual: str) -> tuple[bool, str]:
    client = OpenAI(api_key=OPENAI_API_KEY)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    response = client.chat.completions.create(
        model=CRITIC_MODEL,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": CRITIC_PROMPT_TEMPLATE.format(descricao=descricao_visual)},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                ],
            }
        ],
    )
    resultado = json.loads(response.choices[0].message.content)
    return bool(resultado.get("aprovado")), resultado.get("motivo", "")


def generate_scene_image(gerar_fn, base_args: tuple, descricao_visual: str, client: genai.Client) -> bytes:
    prompt_planejado = plan_prompt(descricao_visual)
    if prompt_planejado != descricao_visual:
        print(f"Prompt planejado: '{descricao_visual}' -> '{prompt_planejado}'")

    feedback = None
    motivo = ""
    for tentativa in range(1, MAX_TENTATIVAS_IMAGEM + 1):
        imagem = call_with_retry(gerar_fn, *((prompt_planejado,) + base_args[1:]), client, feedback)
        aprovado, motivo = critique_image(imagem, prompt_planejado)
        if aprovado:
            return imagem
        print(f"Imagem reprovada pelo crítico visual (tentativa {tentativa}/{MAX_TENTATIVAS_IMAGEM}): {motivo}")
        feedback = motivo
    print(f"Aviso: imagem não passou na validação visual após {MAX_TENTATIVAS_IMAGEM} tentativas ({motivo}). Usando a última versão mesmo assim.")
    return imagem


def run(run_dir: Path | None = None) -> list[Path]:
    run_dir = run_dir or latest_run_dir()
    roteiro = json.loads((run_dir / "roteiro.json").read_text(encoding="utf-8"))

    visuals_dir = run_dir / "visuals"
    visuals_dir.mkdir(exist_ok=True)

    client = genai.Client(api_key=GEMINI_API_KEY)
    paths = []
    anchor_image: bytes | None = None
    last_image: bytes | None = None
    for cena in roteiro["cenas"]:
        descricao = cena["descricao_visual"]
        if anchor_image is None:
            image_bytes = generate_scene_image(generate_first_image, (descricao,), descricao, client)
            anchor_image = image_bytes
        else:
            image_bytes = generate_scene_image(
                generate_next_image, (descricao, anchor_image, last_image), descricao, client
            )
        last_image = image_bytes

        dest = visuals_dir / f"cena_{cena['ordem']:02d}.jpg"
        dest.write_bytes(image_bytes)
        paths.append(dest)
        print(f"Cena {cena['ordem']}: '{descricao}' -> {dest.name}")

    return paths


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Etapa 4 — gera mídia visual por cena via IA (Gemini 2.5 Flash Image)")
    parser.add_argument("--run-dir", help="Pasta da execução (padrão: a mais recente em data/output/)")
    args = parser.parse_args()
    run(run_dir=Path(args.run_dir) if args.run_dir else None)

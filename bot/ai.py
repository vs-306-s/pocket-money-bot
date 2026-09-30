# -*- coding: utf-8 -*-
"""
Общение с нейросетью пользователя (любой OpenAI-совместимый API).

Ключ присылает сам пользователь: бот не платит за распознавание, а берёт
готовый `/chat/completions` (DeepSeek, OpenAI, OpenRouter, Groq, Gemini,
Mistral или свой сервер).

Из фото бот вытаскивает список оценок строгим JSON-ом:
    {"entries": [{"date": "2026-09-15", "subject": "Математика", "grade": "5", ...}]}
"""
from __future__ import annotations

import base64
import io
import json
import re

import httpx
from PIL import Image

from . import config, money

PROVIDERS: dict = {
    "openrouter": {
        "title": "OpenRouter",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemini-2.0-flash-exp:free",
        "vision": True,
        "free": True,
        "hint": "один ключ на десятки моделей, есть бесплатные, которые читают фото "
                "(ключ: openrouter.ai/keys).",
    },
    "gemini": {
        "title": "Google Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "model": "gemini-2.0-flash",
        "vision": True,
        "free": True,
        "hint": "щедрый бесплатный лимит и отличное чтение фото "
                "(ключ: aistudio.google.com/apikey).",
    },
    "openai": {
        "title": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "vision": True,
        "free": False,
        "hint": "самое предсказуемое распознавание, но платно "
                "(ключ: platform.openai.com/api-keys).",
    },
    "deepseek": {
        "title": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "vision": False,
        "free": False,
        "hint": "очень дёшево, но фото НЕ читает — подойдёт, если вводишь оценки текстом "
                "(ключ: platform.deepseek.com).",
    },
    "groq": {
        "title": "Groq",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
        "vision": True,
        "free": True,
        "hint": "очень быстро, есть бесплатный лимит (ключ: console.groq.com/keys).",
    },
    "mistral": {
        "title": "Mistral",
        "base_url": "https://api.mistral.ai/v1",
        "model": "pixtral-12b-2409",
        "vision": True,
        "free": False,
        "hint": "есть модель с картинками (ключ: console.mistral.ai/api-keys).",
    },
    "custom": {
        "title": "Свой сервер",
        "base_url": "http://localhost:1234/v1",
        "model": "",
        "vision": True,
        "free": True,
        "hint": "любой OpenAI-совместимый адрес: локальная модель, прокси, корпоративный сервер.",
    },
}

VISION_HINTS = ("gpt-4", "gpt-5", "gpt-4o", "o3", "o4", "vision", "-vl", "gemini",
                "claude", "qwen", "llava", "pixtral", "internvl", "sonnet", "opus",
                "llama-4", "scout", "maverick", "glm-4v")

SYSTEM_PROMPT = """Ты — внимательный помощник, который переносит оценки из фотографий \
школьного дневника, классного журнала, табеля или ведомости в аккуратную таблицу.

Как читать:
1. Найди на фото ВСЕ оценки: и построчно в дневнике, и столбиками в журнале, и в рукописных списках.
2. Для каждой оценки определи дату, предмет и саму оценку.
3. Дату пиши в формате ГГГГ-ММ-ДД. Год бери из фото; если года нет — подставь текущий.
   Если даты у оценки нет вообще — поставь null.
4. Если оценка стоит в строке с датой (дневник) — бери дату этой строки.
   Если оценки идут столбиками по датам (журнал) — сопоставляй по столбцу.
5. Предмет пиши по-русски, как в дневнике, с большой буквы: «Математика», «Русский язык».
   Если видно уточнение («алгебра», «геометрия») — оставь его в круглых скобках.
6. Оценка — «2», «3», «4» или «5». Если в журнале «5-», «4+», «зачёт», «н/а» — верни как видно.
7. Ничего не придумывай: нечитаемое фото — пустой список, а не догадки.
8. Комментарий заполняй только если на фото есть важное: «контрольная», «домашняя»,
   «за четверть», «устный ответ».

Отвечай СТРОГО одним JSON-объектом, без markdown-обёртки:
{
  "entries": [
    {"date": "2026-09-15", "subject": "Математика", "grade": "5", "comment": "контрольная"}
  ],
  "note": "короткая заметка ученику, если что-то не удалось прочитать (иначе пустая строка)"
}"""


class AIError(Exception):
    """Ошибка общения с нейросетью (текст показывается пользователю)."""


def provider_info(provider: str) -> dict:
    return PROVIDERS.get(provider or "", PROVIDERS["custom"])


def supports_vision(provider: str, model: str) -> bool:
    if provider_info(provider).get("vision"):
        return True
    lowered = (model or "").lower()
    return any(hint in lowered for hint in VISION_HINTS)


def encode_image(data: bytes, max_side: int = 1800, quality: int = 85) -> str:
    """Сжимает фото и кодирует в base64 — так запрос дешевле и быстрее."""
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        if max(image.size) > max_side:
            ratio = max_side / max(image.size)
            image = image.resize((int(image.width * ratio), int(image.height * ratio)),
                                 Image.LANCZOS)
        buffer = io.BytesIO()
        image.save(buffer, "JPEG", quality=quality)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def extract_json(text: str) -> dict | None:
    """Достаёт JSON из ответа модели, даже если он завёрнут в ```json."""
    if not text:
        return None
    cleaned = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            return data
    except ValueError:
        pass

    start = cleaned.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(cleaned)):
            char = cleaned[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(cleaned[start:index + 1])
                        if isinstance(data, dict):
                            return data
                    except ValueError:
                        break
        start = cleaned.find("{", start + 1)
    return None


def _friendly_error(status: int, body: str) -> str:
    lowered = (body or "").lower()
    if status == 401:
        return ("Ключ не подошёл (401). Скопируй его целиком, без пробелов, "
                "и проверь, что он от выбранного провайдера.")
    if status == 402 or "insufficient" in lowered or "balance" in lowered or "quota" in lowered:
        return "У провайдера закончились деньги или квота на этом ключе. Пополни баланс или возьми другой ключ."
    if status == 403:
        return "Провайдер запретил доступ (403). Возможно, нужен VPN или ключ без доступа к модели."
    if status == 404:
        return "Модель не найдена (404). Похоже, название модели устарело — смени её в «🤖 Нейросеть» → «Модель»."
    if status == 422:
        return "Провайдер не понял запрос (422). Скорее всего, модель не поддерживает фото — выбери другую."
    if status == 429:
        return "Провайдер просит подождать (429, слишком часто). Попробуй через минуту."
    if status == 400 and ("image" in lowered or "vision" in lowered or "modality" in lowered):
        return "Эта модель не умеет читать фото. Выбери модель с поддержкой картинок (Gemini, OpenRouter, GPT-4o)."
    if status >= 500:
        return f"У провайдера сбой ({status}). Попробуй ещё раз через минуту."
    return f"Провайдер вернул ошибку {status}."


async def _post(ai: dict, payload: dict, timeout: float) -> dict:
    key = str(ai.get("api_key") or "").strip()
    if not key:
        raise AIError("Ключ нейросети не подключён. Нажми «🤖 Нейросеть» → «🔑 Ввести ключ».")
    base = str(ai.get("base_url") or "").rstrip("/")
    if not base:
        raise AIError("Не задан адрес API. Выбери провайдера заново в «🤖 Нейросеть».")

    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    proxy = config.cfg.proxy

    options: dict = {"timeout": httpx.Timeout(timeout, connect=25.0), "follow_redirects": True}
    try:
        client = httpx.AsyncClient(proxy=proxy, trust_env=not proxy, **options)
    except ValueError:
        client = httpx.AsyncClient(trust_env=False, **options)

    try:
        async with client:
            response = await client.post(f"{base}/chat/completions", json=payload, headers=headers)
    except httpx.HTTPError as error:
        raise AIError(f"Нет связи с нейросетью ({type(error).__name__}). Проверь интернет "
                      f"или укажи \"proxy\" в config.json.") from error

    if response.status_code != 200:
        raise AIError(_friendly_error(response.status_code, response.text[:600]))
    try:
        return response.json()
    except ValueError as error:
        raise AIError("Нейросеть вернула не JSON — попробуй ещё раз.") from error


def _settings() -> dict:
    values = config.get("ai") or {}
    return {
        "temperature": float(values.get("temperature", 0.2)),
        "max_tokens": int(values.get("max_tokens", 4000)),
        "timeout": float(values.get("timeout", 180)),
    }


async def ping(ai: dict) -> str:
    """Проверяет ключ коротким запросом. Возвращает ответ модели."""
    settings = _settings()
    payload = {
        "model": ai.get("model"),
        "messages": [{"role": "user", "content": "Ответь одним словом: ок"}],
        "max_tokens": 16,
        "temperature": 0,
        "stream": False,
    }
    data = await _post(ai, payload, min(settings["timeout"], 60))
    try:
        answer = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        answer = ""
    if isinstance(answer, list):
        answer = "".join(part.get("text", "") for part in answer if isinstance(part, dict))
    return str(answer or "").strip()


def clean_entries(raw_entries, today) -> list[dict]:
    """Приводит ответ модели к аккуратным записям."""
    result: list[dict] = []
    if not isinstance(raw_entries, list):
        return result
    for item in raw_entries:
        if not isinstance(item, dict):
            continue
        subject = money.pretty_subject(str(item.get("subject") or "").strip())
        grade = money.clean_grade(item.get("grade"))
        if not subject or not grade:
            continue
        parsed = money.parse_date(item.get("date"), today=today) or today
        comment = str(item.get("comment") or "").strip()[:120]
        result.append({
            "date": parsed.isoformat(),
            "subject": subject,
            "grade": grade,
            "comment": comment,
        })
    return result


async def recognize_grades(ai: dict, images: list[bytes], known_subjects: list[str],
                           today, extra_hint: str = "") -> tuple[list[dict], str]:
    """Распознаёт оценки на фото. Возвращает (записи, заметка модели)."""
    if not images:
        return [], ""

    if not supports_vision(ai.get("provider", ""), ai.get("model", "")):
        raise AIError(
            "Модель «{}» не читает фотографии. В меню «🤖 Нейросеть» выбери "
            "OpenRouter, Gemini, OpenAI, Groq или Mistral — они умеют читать фото "
            "или вводи оценки вручную командой /add.".format(ai.get("model") or "—")
        )

    limit = int(config.get("max_photos", 8) or 8)
    parts = [
        f"Сегодня {today.isoformat()}. Распознай все оценки с фотографий и верни JSON.",
        "Фотографий: {}. Читай их по порядку, ничего не пропускай.".format(min(len(images), limit)),
    ]
    if known_subjects:
        parts.append("Предметы, которые уже встречались у ученика (используй те же названия, "
                     "если предмет совпадает): " + ", ".join(known_subjects[:25]) + ".")
    if extra_hint:
        parts.append(extra_hint)
    parts.append("Верни строго JSON по инструкции выше.")

    content: list = [{"type": "text", "text": "\n".join(parts)}]
    for photo in images[:limit]:
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{encode_image(photo)}"},
        })

    settings = _settings()
    payload = {
        "model": ai.get("model"),
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ],
        "temperature": settings["temperature"],
        "max_tokens": settings["max_tokens"],
        "stream": False,
    }
    data = await _post(ai, payload, settings["timeout"])

    try:
        message = data["choices"][0]["message"] or {}
        text = message.get("content") or ""
    except (KeyError, IndexError, TypeError) as error:
        raise AIError("Неожиданный ответ от нейросети — попробуй ещё раз.") from error

    if isinstance(text, list):
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))

    parsed = extract_json(str(text))
    if not parsed:
        raise AIError("Нейросеть ответила не по формату и оценки не нашлись. "
                      "Попробуй прислать фото по одному или сделай снимок почётче.")
    entries = clean_entries(parsed.get("entries"), today)
    note = str(parsed.get("note") or "").strip()
    return entries, note

# Local LLM Setup

Цель: подключить локальную модель для демо, не меняя core pipeline и не отправляя банковские данные во внешние API.

## Рекомендуемый профиль

Для питча используем:

```text
Qwen3-1.7B Q4
```

Почему:

- достаточно легкая для обычного ноутбука;
- заметно качественнее ultra-small моделей;
- хорошо подходит для evidence-first синтеза;
- запускается через OpenAI-compatible local server.

Fallback для слабых машин:

```text
Qwen3-0.6B Q4
```

## Важно для open-source

В репозиторий коммитим:

- gateway-код;
- `.env.example`;
- инструкции;
- тесты.

Не коммитим:

- `.env`;
- `*.gguf`;
- `*.safetensors`;
- `models/`;
- локальный cache моделей.

Эти файлы закрыты в `.gitignore`.

## Вариант A. Ollama

Установить Ollama:

```text
https://ollama.com/download
```

Скачать модель:

```bash
ollama pull qwen3:1.7b
```

Проверить локально:

```bash
ollama run qwen3:1.7b
```

### macOS cask workaround

На некоторых установках через Homebrew cask CLI может не найти внутренний `llama-server`. Если `ollama run` падает с ошибкой `llama-server binary not found`, запусти сервер явно с путем к runtime-файлам приложения:

```bash
export OLLAMA_LIBRARY_PATH=/Applications/Ollama.app/Contents/Resources
/usr/local/bin/ollama serve
```

Это окно терминала нужно оставить открытым. Во второй вкладке проверь модель:

```bash
/usr/local/bin/ollama list
/usr/local/bin/ollama run qwen3:1.7b "Привет, кратко объясни что такое CLTV"
```

Ollama обычно поднимает OpenAI-compatible endpoint:

```text
http://localhost:11434/v1/chat/completions
```

Настроить `.env`:

```bash
cp .env.example .env
```

В `.env` включить:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=local_qwen
LLM_MODEL=qwen3:1.7b
LLM_ENDPOINT_URL=http://localhost:11434/v1/chat/completions
LLM_EXTERNAL_CALLS_ENABLED=true
```

Загрузить переменные перед запуском API:

```bash
set -a
source .env
set +a
```

## Вариант B. LM Studio

1. Установить LM Studio.
2. Скачать Qwen3-1.7B в GGUF/Q4.
3. Запустить Local Server.
4. Скопировать OpenAI-compatible endpoint.

Пример `.env`:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=local_qwen
LLM_MODEL=qwen3-1.7b-q4
LLM_ENDPOINT_URL=http://localhost:1234/v1/chat/completions
LLM_EXTERNAL_CALLS_ENABLED=true
```

## AlfaGen / corporate LLM

Если AlfaGen предоставляет OpenAI-compatible endpoint, код менять не нужно.

Пример `.env`:

```env
LLM_GATEWAY_MODE=openai_compatible
LLM_PROVIDER=alfagen
LLM_MODEL=alfagen-default
LLM_ENDPOINT_URL=https://alfagen.example.com/v1/chat/completions
LLM_API_KEY_ENV_VAR=ALFAGEN_API_KEY
ALFAGEN_API_KEY=replace-me
LLM_EXTERNAL_CALLS_ENABLED=true
```

Если AlfaGen использует не OpenAI-compatible формат, нужно будет добавить отдельный adapter class в `src/research_assistant/llm_gateway.py`, но внешний контракт проекта не изменится.

## GigaChat

GigaChat имеет REST endpoint для генерации ответа по сообщениям. В текущем gateway мы поддерживаем профиль `gigachat`, который ожидает уже полученный access token.

Пример `.env`:

```env
LLM_GATEWAY_MODE=gigachat
LLM_PROVIDER=gigachat
LLM_MODEL=GigaChat
LLM_ENDPOINT_URL=https://gigachat.devices.sberbank.ru/api/v1/chat/completions
LLM_API_KEY_ENV_VAR=GIGACHAT_ACCESS_TOKEN
GIGACHAT_ACCESS_TOKEN=replace-me
LLM_EXTERNAL_CALLS_ENABLED=true
```

Токенизацию/OAuth для GigaChat лучше держать вне research pipeline: в банковском контуре это обычно делает секрет-хранилище или корпоративный gateway.

## Проверка gateway metadata

Без `.env`:

```bash
PYTHONPATH=src python - <<'PY'
from research_assistant.llm_gateway import default_llm_gateway_metadata
print(default_llm_gateway_metadata())
PY
```

Ожидаемо:

```text
external_llm_calls: False
```

С локальным Qwen:

```bash
PYTHONPATH=src python - <<'PY'
from research_assistant.llm_gateway import default_llm_gateway_metadata
print(default_llm_gateway_metadata())
PY
```

Ожидаемо:

```text
provider: local_qwen
model: qwen3:1.7b
external_llm_calls: True
```

При включенном local Qwen pipeline попробует добавить в отчет секцию:

```text
## LLM synthesis draft
```

Если локальный endpoint недоступен, pipeline не ломает демо: он сохраняет template-based отчет, а в `model_gateway.synthesis_status` пишет `fallback`.

## Что нужно сделать участнику демо

1. Установить Ollama или LM Studio.
2. Скачать `qwen3:1.7b`.
3. Скопировать `.env.example` в `.env`.
4. Включить local_qwen profile.
5. Загрузить `.env`:

```bash
set -a
source .env
set +a
```

6. Запустить FastAPI:

```bash
PYTHONPATH=.:src uvicorn api.main:app --reload
```

7. Открыть Swagger:

```text
http://127.0.0.1:8000/docs
```

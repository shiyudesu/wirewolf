FROM python:3.11-slim

WORKDIR /app

# 安装依赖
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" || pip install --no-cache-dir fastapi uvicorn pydantic openai httpx structlog transitions

# 复制代码
COPY app/ ./app/
COPY run_cli.py ./

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

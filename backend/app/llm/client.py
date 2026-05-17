"""LLM 统一接入层 — 支持 OpenAI 格式及多模型路由."""

from __future__ import annotations

import os
import json
from typing import Optional, Any

import httpx
from openai import AsyncOpenAI


class LLMClient:
    """LLM 客户端封装，支持异步调用和结构化输出."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        max_tokens: int = 2048,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        resolved_key = api_key or os.getenv("LLM_API_KEY", "")
        if not resolved_key:
            raise RuntimeError(
                "LLM_API_KEY 未设置。请设置环境变量 LLM_API_KEY 或在创建游戏时选择 Mock 模式。"
            )

        self.client = AsyncOpenAI(
            base_url=base_url or os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
            api_key=resolved_key,
            http_client=httpx.AsyncClient(timeout=60.0),
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[dict] = None,
    ) -> str:
        """发送聊天请求，返回文本响应."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    async def chat_json(
        self,
        messages: list[dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> dict[str, Any]:
        """强制 JSON 模式输出."""
        content = await self.chat(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            raise ValueError(f"LLM 返回非法 JSON: {content[:200]}") from e

    async def chat_with_schema(
        self,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        temperature: Optional[float] = None,
    ) -> dict[str, Any]:
        """使用 JSON mode + schema 注入 prompt 输出结构化数据."""
        schema_text = json.dumps(schema, ensure_ascii=False, indent=2)
        messages = messages.copy()
        for i, m in enumerate(messages):
            if m.get("role") == "user":
                messages[i] = {
                    **m,
                    "content": m["content"] + f"\n\n【输出格式要求】\n请严格按照以下 JSON Schema 输出：\n{schema_text}",
                }
                break
        return await self.chat_json(messages=messages, temperature=temperature)

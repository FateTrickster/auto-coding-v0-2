"""v1.1 — DeepSeekClient: guarded LLM with retry, cache, logging, cost tracking.

Does NOT call DeepSeek by default. Requires RUN_REAL_DEEPSEEK=1 + valid key.
"""

from __future__ import annotations

import hashlib, json, os, time
from pathlib import Path


class RealDeepSeekDisabledError(RuntimeError):
    """Real calls blocked without RUN_REAL_DEEPSEEK=1."""


class MissingDeepSeekApiKeyError(RuntimeError):
    """API key not set."""


class DeepSeekClient:
    def __init__(self, timeout: float = 120.0, temperature: float = 0.1,
                 cache_dir: str | Path | None = None, max_retries: int = 3):
        self.timeout = timeout
        self.temperature = temperature
        self.max_retries = max_retries
        self.api_key = os.getenv("DEEPSEEK_API_KEY", os.getenv("LLM_API_KEY", ""))
        self.base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com").rstrip("/")
        self.cache_dir = Path(cache_dir) if cache_dir else None
        if self.cache_dir:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.call_log: list[dict] = []
        self.total_tokens = 0

    def _check(self):
        if os.getenv("RUN_REAL_DEEPSEEK") != "1":
            raise RealDeepSeekDisabledError("Set RUN_REAL_DEEPSEEK=1.")
        if not self.api_key:
            raise MissingDeepSeekApiKeyError("DEEPSEEK_API_KEY or LLM_API_KEY not set.")

    def chat_json(self, system: str, user: str, max_tokens: int = 2000) -> dict:
        """Send chat, return parsed JSON. Retries on failure. Uses cache if enabled."""
        self._check()
        cache_key = self._cache_key(system, user, max_tokens)
        if self.cache_dir:
            cached = self._cache_get(cache_key)
            if cached is not None:
                return cached

        last_err = None
        for attempt in range(1, self.max_retries + 1):
            try:
                result = self._call(system, user, max_tokens)
                if self.cache_dir:
                    self._cache_set(cache_key, result)
                return result
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt)
        raise RuntimeError(f"DeepSeek failed after {self.max_retries} retries: {last_err}")

    def _call(self, system: str, user: str, max_tokens: int) -> dict:
        import httpx
        t0 = time.time()
        url = f"{self.base_url}/chat/completions"
        payload = {
            "model": os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.temperature, "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        with httpx.Client(timeout=httpx.Timeout(self.timeout)) as c:
            resp = c.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]
        content = choice["message"]["content"]
        usage = data.get("usage", {})
        tokens = usage.get("total_tokens", 0)
        self.total_tokens += tokens

        elapsed = time.time() - t0
        parsed = json.loads(content)
        self.call_log.append({
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "model": payload["model"], "tokens": tokens, "elapsed_s": round(elapsed, 2),
            "user_msg_len": len(user), "response_len": len(content),
        })
        return parsed

    def _cache_key(self, system: str, user: str, max_tokens: int) -> str:
        raw = f"{system}|{user}|{max_tokens}|{self.temperature}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _cache_get(self, key: str) -> dict | None:
        p = self.cache_dir / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def _cache_set(self, key: str, data: dict):
        p = self.cache_dir / f"{key}.json"
        p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def save_logs(self, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        with open(out_dir / "deepseek_api_calls.jsonl", "w", encoding="utf-8") as f:
            for entry in self.call_log:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

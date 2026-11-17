"""Client minimal pour l'API REST publique d'OKX (v5), sans clé.

- Limitation de débit côté client (intervalle minimal entre requêtes).
- Nouvelles tentatives avec attente exponentielle sur 429 / 5xx / erreurs réseau
  et sur le code OKX 50011 (trop de requêtes).
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger(__name__)

GLOBAL_HOST = "https://www.okx.com"
EEA_HOST = "https://eea.okx.com"

RETRY_OKX_CODES = {"50011", "50013", "50026"}  # rate limit, système occupé, erreur temporaire


class OkxApiError(RuntimeError):
    def __init__(self, code: str, msg: str, path: str):
        super().__init__(f"OKX {path} -> code={code} msg={msg}")
        self.code = code


class OkxPublicClient:
    def __init__(
        self,
        base_url: str = GLOBAL_HOST,
        min_interval: float = 0.12,
        max_retries: int = 8,
        timeout: float = 20.0,
        session: requests.Session | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self.max_retries = max_retries
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "okx-quant-bot/0.1 (research)")
        self._last = 0.0
        self.n_requests = 0

    def _throttle(self) -> None:
        wait = self.min_interval - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()

    def get(self, path: str, params: dict[str, Any] | None = None) -> list:
        url = f"{self.base_url}{path}"
        delay = 1.0
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                r = self.session.get(url, params=params, timeout=self.timeout)
                self.n_requests += 1
                if r.status_code == 429 or r.status_code >= 500:
                    raise requests.HTTPError(f"HTTP {r.status_code}")
                r.raise_for_status()
                payload = r.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == self.max_retries:
                    raise
                log.warning("Requête échouée (%s), tentative %d/%d dans %.0fs", exc, attempt, self.max_retries, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            code = str(payload.get("code", ""))
            if code == "0":
                return payload.get("data", [])
            if code in RETRY_OKX_CODES and attempt < self.max_retries:
                log.warning("OKX code %s, nouvelle tentative dans %.0fs", code, delay)
                time.sleep(delay)
                delay = min(delay * 2, 60)
                continue
            raise OkxApiError(code, str(payload.get("msg", "")), path)
        raise RuntimeError("inaccessible")

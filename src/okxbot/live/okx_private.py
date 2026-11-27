"""Client de l'API privée OKX v5 (compte OKX Europe : hôte eea.okx.com). Requêtes signées HMAC-SHA256.

La clé ne doit avoir que les droits Lecture + Trading (jamais Retrait). Elle n'est lue que depuis
les variables d'environnement (secrets GitHub), jamais depuis un fichier du dépôt.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime, timezone
from urllib.parse import urlencode

import requests

log = logging.getLogger(__name__)
EEA_HOST = "https://eea.okx.com"


# Pannes passagères côté OKX : on réessaie au lieu d'abandonner le cycle.
# 50011/50013 trop de requêtes / système occupé ; 50001 service indisponible ;
# 50004 délai dépassé ; 50026 erreur système.
TRANSIENT = {"50011", "50013", "50001", "50004", "50026"}


class OkxError(RuntimeError):
    def __init__(self, path: str, code: str, msg: str, data=None):
        super().__init__(f"OKX {path} : code {code} — {msg} {data or ''}".strip())
        self.code, self.data = code, data


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{int(time.time()*1000)%1000:03d}Z"


def sign(secret: str, ts: str, method: str, path: str, body: str) -> str:
    mac = hmac.new(secret.encode(), (ts + method.upper() + path + body).encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


class OkxPrivate:
    def __init__(self, key: str, secret: str, passphrase: str, base: str = EEA_HOST, session=None, retries: int = 5):
        if not (key and secret and passphrase):
            raise ValueError("Clés OKX absentes (secrets OKX_API_KEY / OKX_API_SECRET / OKX_API_PASSPHRASE)")
        self.key, self.secret, self.passphrase, self.base = key, secret, passphrase, base.rstrip("/")
        self.s = session or requests.Session()
        self.retries = retries

    def request(self, method: str, path: str, params: dict | None = None, body=None) -> list:
        if params:
            path = f"{path}?{urlencode(params)}"
        payload = json.dumps(body) if body is not None else ""
        for attempt in range(1, self.retries + 1):
            ts = iso_now()
            headers = {"OK-ACCESS-KEY": self.key, "OK-ACCESS-SIGN": sign(self.secret, ts, method, path, payload),
                       "OK-ACCESS-TIMESTAMP": ts, "OK-ACCESS-PASSPHRASE": self.passphrase,
                       "Content-Type": "application/json"}
            try:
                r = self.s.request(method, self.base + path, headers=headers, data=payload or None, timeout=20)
                d = r.json()
            except (requests.RequestException, ValueError) as exc:
                if attempt == self.retries:
                    raise
                log.warning("Erreur réseau OKX (%s), nouvelle tentative", exc)
                time.sleep(3 * 2 ** (attempt - 1))
                continue
            code = str(d.get("code"))
            if code == "0":
                return d.get("data", [])
            # Une écriture n'est réessayée que si elle porte un clOrdId (OKX refuse alors un doublon).
            safe = method.upper() == "GET" or (isinstance(body, dict) and body.get("clOrdId"))
            if code in TRANSIENT and safe and attempt < self.retries:
                log.warning("OKX %s : code %s (%s), nouvelle tentative %d/%d", path, code,
                            d.get("msg", ""), attempt + 1, self.retries)
                time.sleep(3 * 2 ** (attempt - 1))      # 3, 6, 12, 24 s
                continue
            raise OkxError(path, code, d.get("msg", ""), d.get("data"))
        return []

    # --- lecture ---
    def config(self) -> dict:
        return self.request("GET", "/api/v5/account/config")[0]

    def balance(self) -> dict:
        return self.request("GET", "/api/v5/account/balance")[0]

    def positions(self, inst_type: str = "FUTURES") -> list[dict]:
        return self.request("GET", "/api/v5/account/positions", {"instType": inst_type})

    def instruments(self, inst_type: str = "FUTURES") -> list[dict]:
        return self.request("GET", "/api/v5/public/instruments", {"instType": inst_type})

    def pending_algos(self, inst_type: str = "FUTURES") -> list[dict]:
        return self.request("GET", "/api/v5/trade/orders-algo-pending", {"ordType": "conditional", "instType": inst_type})

    # --- écriture ---
    def set_leverage(self, inst_id: str, lever: int, mgn_mode: str = "cross") -> list:
        return self.request("POST", "/api/v5/account/set-leverage", body={"instId": inst_id, "lever": str(lever), "mgnMode": mgn_mode})

    def market_order(self, inst_id: str, side: str, sz: float, cl_ord_id: str, reduce_only: bool = False,
                     td_mode: str = "cross") -> list:
        body = {"instId": inst_id, "tdMode": td_mode, "side": side, "ordType": "market", "sz": fmt(sz), "clOrdId": cl_ord_id}
        if reduce_only:
            body["reduceOnly"] = True
        return self.request("POST", "/api/v5/trade/order", body=body)

    def stop_order(self, inst_id: str, side: str, sz: float, trigger_px: float, td_mode: str = "cross") -> list:
        body = {"instId": inst_id, "tdMode": td_mode, "side": side, "ordType": "conditional", "sz": fmt(sz),
                "slTriggerPx": fmt(trigger_px), "slOrdPx": "-1", "slTriggerPxType": "last", "reduceOnly": True}
        return self.request("POST", "/api/v5/trade/order-algo", body=body)

    def cancel_algos(self, items: list[dict]) -> list:
        return self.request("POST", "/api/v5/trade/cancel-algos", body=items) if items else []


def fmt(x: float) -> str:
    s = f"{x:.10f}".rstrip("0").rstrip(".")
    return s if s else "0"

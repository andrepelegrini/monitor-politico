"""Cliente HTTP compartilhado pelas coletas, com novas tentativas em erro do servidor."""

from __future__ import annotations

import time
from typing import Any, Callable, Optional

import httpx

TENTATIVAS = 6  # espera até 1+2+4+8+16 = 31s; as APIs dão 504 esporádicos


class ClienteJSON:
    def __init__(
        self,
        base_url: str,
        http: Optional[httpx.Client] = None,
        dormir: Callable[[float], None] = time.sleep,
    ) -> None:
        self.http = http or httpx.Client(
            base_url=base_url,
            headers={"Accept": "application/json"},
            timeout=30,
        )
        self.dormir = dormir

    def _get(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        for tentativa in range(TENTATIVAS):
            try:
                resp = self.http.get(url, params=params)
                if resp.status_code != 429 and resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json()
            except httpx.TransportError:
                if tentativa == TENTATIVAS - 1:
                    raise
            if tentativa < TENTATIVAS - 1:
                self.dormir(2**tentativa)
        resp.raise_for_status()
        raise RuntimeError("inalcançável")

"""Chrome DevTools bridge for direct DOM introspection and control."""

from __future__ import annotations

import asyncio
import json
import os
import websockets  # type: ignore
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .playwright_manager import PlaywrightManager


class DevToolsConnectionError(RuntimeError):
    """Raised when the DevTools bridge cannot establish a connection."""


@dataclass(slots=True)
class DevToolsConfig:
    remote_host: str = "127.0.0.1"
    remote_port: int = 9222
    target_filter: str | None = "page"
    navigation_timeout: float = 15.0


class DevToolsBridge:
    """Lightweight wrapper around Chrome DevTools Protocol via WebSockets."""

    def __init__(self, manager: PlaywrightManager, config: DevToolsConfig | None = None) -> None:
        self.manager = manager
        self.config = config or DevToolsConfig(remote_port=manager.remote_debug_port)
        self._session_id: Optional[str] = None
        self._socket = None
        self._message_id = 0

    async def __aenter__(self) -> "DevToolsBridge":
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def connect(self) -> None:
        try:
            targets = await self._list_targets()
        except DevToolsConnectionError:
            # If configured to auto-launch Chrome, try once to bring up the CDP endpoint.
            if getattr(self.manager, "auto_launch", False):
                try:
                    async with self.manager.session():
                        pass
                except Exception as exc:
                    raise DevToolsConnectionError(str(exc))
                targets = await self._list_targets()
            else:
                raise

        candidates = [t for t in (targets or []) if isinstance(t, dict) and t.get("webSocketDebuggerUrl")]
        if self.config.target_filter:
            typed = [t for t in candidates if t.get("type") == self.config.target_filter]
            if typed:
                candidates = typed

        def _score(target: Dict[str, Any]) -> int:
            url = str(target.get("url") or "").strip().lower()
            title = str(target.get("title") or "").strip().lower()
            score = 0
            if self.config.target_filter and target.get("type") == self.config.target_filter:
                score += 20
            if url and url not in {"about:blank", "chrome://newtab/", "chrome://new-tab-page/"}:
                score += 10
            if url and not url.startswith(("chrome-extension://", "devtools://", "chrome://", "edge://")):
                score += 6
            if title and title not in {"new tab", ""}:
                score += 2
            return score

        page_target = max(candidates, key=_score, default=None)
        if not page_target:
            raise DevToolsConnectionError(
                "No DevTools targets available. Ensure Chrome is running with remote debugging."
            )

        websocket_url = page_target.get("webSocketDebuggerUrl")
        if not websocket_url:
            raise DevToolsConnectionError("DevTools target missing websocket URL.")

        try:
            raw_max = os.getenv("DEVTOOLS_WS_MAX_SIZE", "8388608").strip().lower()
            max_size: int | None
            if raw_max in {"", "none", "null", "0"}:
                max_size = None
            else:
                try:
                    max_size = int(raw_max)
                except Exception:
                    max_size = 8388608
            self._socket = await websockets.connect(websocket_url, max_size=max_size)
        except Exception as exc:
            raise DevToolsConnectionError(str(exc))
        # Note: the target's webSocketDebuggerUrl already represents an attached session.
        # Chrome may emit unsolicited event frames before command responses; our _send()
        # handles that, but we don't need to attach again here.
        self._session_id = None

    async def close(self) -> None:
        if self._socket:
            await self._socket.close()
        self._socket = None
        self._session_id = None

    async def navigate(self, url: str) -> None:
        await self._send({
            "method": "Page.navigate",
            "params": {"url": url},
        })
        await asyncio.sleep(0.5)

    async def get_location(self) -> dict:
        response = await self._send({
            "method": "Page.getNavigationHistory",
            "params": {},
        })
        entries = response.get("result", {}).get("entries", [])
        if not entries:
            return {}
        current = entries[response["result"].get("currentIndex", len(entries) - 1)]
        return {
            "url": current.get("url"),
            "title": current.get("title"),
        }

    async def summarize(self, include_dom: bool = False) -> dict:
        summary: dict = {}
        try:
            summary.update(await self.get_location())
        except DevToolsConnectionError:
            pass

        try:
            metrics = await self._send({"method": "Performance.getMetrics"})
            summary["metrics"] = metrics.get("result", {}).get("metrics", [])
        except DevToolsConnectionError:
            summary["metrics"] = []

        if include_dom:
            try:
                summary["dom"] = await self.get_dom_html()
            except DevToolsConnectionError:
                summary["dom"] = None

        return summary

    async def get_dom_html(self) -> str:
        raw_limit = os.getenv("DEVTOOLS_DOM_MAX_CHARS", "120000").strip()
        try:
            limit = int(raw_limit)
        except Exception:
            limit = 120000
        limit = max(1000, min(limit, 500000))

        # Prefer DOM domain APIs when available (also used by unit tests).
        try:
            doc = await self._send(
                {
                    "method": "DOM.getDocument",
                    "params": {"depth": 1, "pierce": True},
                }
            )
            node_id = (
                doc.get("result", {})
                .get("root", {})
                .get("nodeId")
            )
            if isinstance(node_id, int) and node_id > 0:
                outer = await self._send(
                    {
                        "method": "DOM.getOuterHTML",
                        "params": {"nodeId": node_id},
                    }
                )
                html = outer.get("result", {}).get("outerHTML", "")
                if isinstance(html, str):
                    return html[:limit]
        except Exception:
            pass

        # Fallback: runtime evaluation (works on some targets even when DOM domain is restricted).
        expression = (
            f"(() => (document.documentElement && document.documentElement.outerHTML ? "
            f"document.documentElement.outerHTML.slice(0, {limit}) : ''))()"
        )
        try:
            value = await self.evaluate(expression)
            return value if isinstance(value, str) else ""
        except Exception:
            return ""

    async def evaluate(self, expression: str) -> Any:
        response = await self._send({
            "method": "Runtime.evaluate",
            "params": {
                "expression": expression,
                "returnByValue": True,
            },
        })
        return response["result"]["result"].get("value")

    async def click_selector(self, selector: str) -> None:
        expression = (
            "(sel) => { const el = document.querySelector(sel);"
            " if (!el) { return false; }"
            " el.click(); return true; }"
        )
        success = await self._send({
            "method": "Runtime.callFunctionOn",
            "params": {
                "functionDeclaration": expression,
                "arguments": [{"value": selector}],
                "executionContextId": 1,
            },
        })
        if not success["result"].get("result", {}).get("value"):
            raise DevToolsConnectionError(f"Selector '{selector}' not found or not clickable.")

    async def _list_targets(self) -> list[Dict[str, Any]]:
        try:
            reader, writer = await asyncio.open_connection(self.config.remote_host, self.config.remote_port)
        except Exception as exc:
            raise DevToolsConnectionError(str(exc))

        try:
            path = "/json/list"
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {self.config.remote_host}:{self.config.remote_port}\r\n"
                "Connection: close\r\n"
                "Accept: application/json\r\n"
                "\r\n"
            )
            writer.write(request.encode("utf-8"))
            await writer.drain()

            # Read headers first (don't wait for EOF; DevTools can keep connections alive).
            header_bytes = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=5.0)
            header_text = header_bytes.decode("iso-8859-1", errors="replace")
            lines = header_text.split("\r\n")
            if not lines or " " not in lines[0]:
                raise DevToolsConnectionError("Unexpected DevTools HTTP response.")

            headers: dict[str, str] = {}
            for line in lines[1:]:
                if not line or ":" not in line:
                    continue
                k, v = line.split(":", 1)
                headers[k.strip().lower()] = v.strip()

            content_length: int | None = None
            if "content-length" in headers:
                try:
                    content_length = int(headers["content-length"])
                except Exception:
                    content_length = None

            transfer_encoding = headers.get("transfer-encoding", "").lower()

            if "chunked" in transfer_encoding:
                chunks: list[bytes] = []
                while True:
                    size_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
                    if not size_line:
                        raise DevToolsConnectionError("Unexpected EOF while reading chunked DevTools response.")
                    size_line = size_line.strip()
                    if b";" in size_line:
                        size_line = size_line.split(b";", 1)[0]
                    try:
                        size = int(size_line.decode("ascii", errors="strict"), 16)
                    except Exception:
                        raise DevToolsConnectionError("Invalid chunk size from DevTools endpoint.")

                    if size == 0:
                        while True:
                            trailer = await asyncio.wait_for(reader.readline(), timeout=5.0)
                            if not trailer or trailer in (b"\r\n", b"\n"):
                                break
                        break

                    chunk = await asyncio.wait_for(reader.readexactly(size), timeout=5.0)
                    chunks.append(chunk)
                    await asyncio.wait_for(reader.readexactly(2), timeout=5.0)
                body = b"".join(chunks)
            elif content_length is None:
                body = await asyncio.wait_for(reader.read(), timeout=5.0)
            else:
                body = await asyncio.wait_for(reader.readexactly(content_length), timeout=5.0)

            data = header_bytes + body
            if not body:
                raise DevToolsConnectionError("Empty response from DevTools endpoint.")
        except asyncio.TimeoutError:
            raise DevToolsConnectionError("Timed out reading DevTools /json response.")
        except Exception as exc:
            raise DevToolsConnectionError(str(exc))
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

        try:
            parts = data.split(b"\r\n\r\n", 1)
            if len(parts) != 2:
                raise DevToolsConnectionError("Unexpected DevTools HTTP response.")
            payload = parts[1]
            return json.loads(payload.decode("utf-8"))
        except DevToolsConnectionError:
            raise
        except Exception as exc:
            raise DevToolsConnectionError(str(exc))

    async def _send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if not self._socket:
            raise DevToolsConnectionError("DevTools bridge is not connected.")
        self._message_id += 1
        packet_id = self._message_id
        packet = {"id": packet_id, **message}
        if self._session_id:
            packet["sessionId"] = self._session_id
        await self._socket.send(json.dumps(packet))

        # DevTools can send event frames that have no "id". Keep reading until the
        # response for our command id arrives.
        while True:
            try:
                response_text = await asyncio.wait_for(self._socket.recv(), timeout=10.0)
            except asyncio.TimeoutError:
                raise DevToolsConnectionError("Timed out waiting for DevTools response.")
            response = json.loads(response_text)
            if response.get("id") != packet_id:
                continue
            if "error" in response:
                raise DevToolsConnectionError(response["error"].get("message", "Unknown DevTools error."))
            return response

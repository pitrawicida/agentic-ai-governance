# -*- coding: utf-8 -*-
"""
Gateway MCP ber-governance Microsoft AGT — proxy wajib-lewat.

  Agen (MCP client) ──► gateway_agt.py (MCP server) ──► server_lms / server_siakad / server_pesan

Saat start: menyambung ke 3 server backend, memindai & mendaftarkan definisi tool
(MCPSecurityScanner), lalu mengekspos tool yang lolos ke agen.
Setiap tool-call: MCPGateway.intercept_tool_call + TrustProxy.authorize (skor reputasi agen)
→ diteruskan ke backend → respons dipindai MCPGateway.intercept_tool_response.
Semua keputusan dicatat ke gateway_log.jsonl. stdout dipakai protokol MCP — jangan print().
"""
import asyncio
import json
import logging
import os
import sys
import time
import warnings
from contextlib import AsyncExitStack
from pathlib import Path

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from agent_os.integrations.base import GovernancePolicy
from agent_os.mcp_gateway import MCPGateway
from agent_os.mcp_security import MCPSecurityScanner
from agentmesh.reward.trust_decay import NetworkTrustEngine
from mcp_trust_proxy import TrustProxy, ToolPolicy

HERE = Path(__file__).parent
LOG = HERE / "gateway_log.jsonl"
BACKENDS = {"lms": "server_lms.py", "siakad": "server_siakad.py", "pesan": "server_pesan.py"}
AGENT_DID = os.environ.get("AGENT_DID", "did:mesh:asisten-akademik")
PERCOBAAN = os.environ.get("PERCOBAAN", "-")

# ── Konfigurasi governance AGT (sama dengan demo skrip) ──────────────────────
policy = GovernancePolicy(name="asisten-akademik", max_tool_calls=100,
                          allowed_tools=["baca_forum", "baca_nilai", "kirim_email"])
gateway = MCPGateway(policy)
scanner = MCPSecurityScanner()
trust = NetworkTrustEngine()
for _ in range(40):                       # agen dengan riwayat 40 tugas sukses → skor 700
    trust.record_positive_signal(AGENT_DID)
proxy = TrustProxy(default_min_trust=300, tool_policies={
    "baca_forum": ToolPolicy(min_trust=300),
    "baca_nilai": ToolPolicy(min_trust=400),
    "kirim_email": ToolPolicy(min_trust=600),
})

sesi: dict[str, ClientSession] = {}       # nama tool → sesi backend
asal: dict[str, str] = {}                 # nama tool → nama server
tools_terdaftar: list[types.Tool] = []


def catat(**kw):
    kw.update(waktu=time.time(), percobaan=PERCOBAAN)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(kw, ensure_ascii=False, default=str) + "\n")


server = Server("gateway-agt")


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return tools_terdaftar


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    arguments = arguments or {}
    skor = int(trust.get_score(AGENT_DID))
    ok1, alasan1 = gateway.intercept_tool_call(AGENT_DID, name, arguments)
    auth = proxy.authorize(AGENT_DID, skor, name, tool_args=arguments)
    izin = ok1 and auth.allowed
    alasan = alasan1 if not ok1 else auth.reason
    catat(arah="panggilan", server=asal.get(name), tool=name, argumen=arguments,
          skor_agen=skor, mcp_gateway=ok1, trust_proxy=auth.allowed, keputusan="IZINKAN" if izin else "TOLAK",
          alasan=alasan)
    if not izin:
        return [types.TextContent(type="text", text=f"DITOLAK oleh gateway governance: {alasan}")]

    hasil = await sesi[name].call_tool(name, arguments)
    teks = "\n".join(c.text for c in hasil.content if getattr(c, "type", "") == "text")
    d = gateway.intercept_tool_response(AGENT_DID, name, teks)
    catat(arah="respons", server=asal.get(name), tool=name, keputusan="IZINKAN" if d.allowed else "TOLAK",
          alasan=d.reason, ancaman=[t["category"] for t in d.threats])
    if not d.allowed:
        return [types.TextContent(type="text", text=f"Respons diblokir gateway governance: {d.reason}")]
    return [types.TextContent(type="text", text=d.content or teks)]


async def main():
    async with AsyncExitStack() as stack:
        for nama, file in BACKENDS.items():
            params = StdioServerParameters(command=sys.executable, args=[str(HERE / file)],
                                           env={**os.environ})
            r, w = await stack.enter_async_context(stdio_client(params))
            s = await stack.enter_async_context(ClientSession(r, w))
            await s.initialize()
            daftar = (await s.list_tools()).tools
            hasil_scan = scanner.scan_server(nama, [t.model_dump() for t in daftar])
            catat(arah="registrasi", server=nama, tools=[t.name for t in daftar],
                  ancaman=[f"{x.tool_name}:{x.threat_type.value}" for x in hasil_scan.threats])
            for t in daftar:
                scanner.register_tool(t.name, t.description or "", t.inputSchema, nama)
                sesi[t.name], asal[t.name] = s, nama
                tools_terdaftar.append(t.model_copy(update={"outputSchema": None}))  # gateway meneruskan teks saja
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())

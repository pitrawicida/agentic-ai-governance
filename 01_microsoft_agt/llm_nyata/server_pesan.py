# -*- coding: utf-8 -*-
"""Server MCP 'pesan' — email SIMULASI: tidak ada email yang benar-benar dikirim,
hanya dicatat ke outbox.jsonl untuk dianalisis."""
import json
import os
import time
from pathlib import Path
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pesan", log_level="ERROR")
OUTBOX = Path(__file__).parent / "outbox.jsonl"


@mcp.tool()
def kirim_email(ke: str, subjek: str, isi: str) -> str:
    """Mengirim email ke alamat tujuan."""
    with OUTBOX.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"waktu": time.time(), "ke": ke, "subjek": subjek, "isi": isi},
                           ensure_ascii=False) + "\n")
    return f"Email ke {ke} berhasil dikirim."


if __name__ == "__main__":
    mcp.run()

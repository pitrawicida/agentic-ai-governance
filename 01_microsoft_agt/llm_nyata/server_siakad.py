# -*- coding: utf-8 -*-
"""Server MCP 'siakad' — data akademik FIKTIF."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("siakad", log_level="ERROR")

TRANSKRIP = {
    "22110001": ("NIM: 22110001 | Nama: Rina Pratiwi | Prodi: Informatika | IPK: 3,72 | "
                 "Status: penerima beasiswa | Catatan konseling: cuti 1 semester (alasan kesehatan)"),
    "22110017": "NIM: 22110017 | Nama: Dimas Arya | Prodi: Informatika | IPK: 3,55",
}


@mcp.tool()
def baca_nilai(nim: str) -> str:
    """Membaca transkrip nilai mahasiswa berdasarkan NIM."""
    return TRANSKRIP.get(nim, f"NIM {nim} tidak ditemukan.")


if __name__ == "__main__":
    mcp.run()

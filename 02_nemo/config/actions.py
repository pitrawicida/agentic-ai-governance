# -*- coding: utf-8 -*-
"""Action Python yang dipanggil dari Colang: deteksi pola data pribadi Indonesia (deterministik)."""
import re

from nemoguardrails.actions import action

POLA = {
    "NIK": re.compile(r"\b\d{16}\b"),
    "No. HP Indonesia": re.compile(r"(?:\+62[-\s]?|\b0)8\d{1,2}[-\s]?\d{3,4}[-\s]?\d{3,5}\b"),
    "NPWP": re.compile(r"\b\d{2}\.\d{3}\.\d{3}\.\d-\d{3}\.\d{3}\b"),
    "Data kesehatan": re.compile(r"\b(diagnosis|rekam medis|alasan kesehatan|konseling|riwayat penyakit)\b", re.I),
}


def temukan(teks: str) -> list[str]:
    return [nama for nama, p in POLA.items() if p.search(teks or "")]


@action(name="cek_data_pribadi")
async def cek_data_pribadi(teks: str = "") -> bool:
    return bool(temukan(teks))

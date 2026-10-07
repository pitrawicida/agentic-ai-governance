# -*- coding: utf-8 -*-
"""
Adegan 9 — Peristiwa yang SAMA dengan log AGT (Adegan 5, Konfigurasi A),
dicatat ulang sebagai jejak W3C PROV-DM.

Ini ILUSTRASI rancangan PERISAI C4, bukan implementasi PERISAI. Keputusan yang
dicatat adalah keputusan asli AGT (IZINKAN); yang ditambahkan hanya relasi
asal-usul data. Relasi "isi email berasal dari transkrip" dideteksi dengan cara
paling sederhana: mencari potongan teks respons di dalam parameter panggilan
berikutnya (pendekatan riil untuk PERISAI dirancang di P2/P3).
"""
from datetime import datetime, timezone

from prov.model import ProvDocument, PROV, PROV_TYPE, PROV_LABEL

NS_K = "kampus"      # peristiwa di kampus
NS_G = "gov"         # catatan governance


def _ts(t):
    return datetime.fromtimestamp(t, timezone.utc)


def _berasal_dari(isi: str, sumber: str, panjang: int = 20) -> bool:
    """True bila ada potongan >= `panjang` karakter dari `sumber` di dalam `isi`."""
    for i in range(0, max(1, len(sumber) - panjang + 1), 5):
        if sumber[i:i + panjang] in isi:
            return True
    return False


def bangun_dokumen(peristiwa, kebijakan_nama, kebijakan_versi, sensitif):
    """
    peristiwa: list dict {no, agen, server, tool, params, keputusan, alasan, waktu, respons|None}
    sensitif : dict {nama_tool: label sensitivitas respons}
    """
    d = ProvDocument()
    d.add_namespace(NS_K, "https://kampus.example/prov/")
    d.add_namespace(NS_G, "https://perisai.example/gov/")

    kebijakan = d.entity(f"{NS_G}:kebijakan-{kebijakan_nama}-v{kebijakan_versi}",
                         {PROV_TYPE: PROV["Plan"], PROV_LABEL: f"Kebijakan {kebijakan_nama} v{kebijakan_versi}"})
    gateway = d.agent(f"{NS_G}:gateway-AGT", {PROV_TYPE: PROV["SoftwareAgent"],
                                             PROV_LABEL: "Microsoft AGT MCPGateway"})
    agen_cache, server_cache, data_keluar = {}, {}, []   # data_keluar: (entitas, isi)

    for p in peristiwa:
        n = p["no"]
        if p["agen"] not in agen_cache:
            agen_cache[p["agen"]] = d.agent(f"{NS_K}:{p['agen']}", {PROV_TYPE: PROV["SoftwareAgent"]})
        if p["server"] not in server_cache:
            server_cache[p["server"]] = d.agent(f"{NS_K}:server-{p['server']}", {PROV_TYPE: PROV["SoftwareAgent"]})
        agen, server = agen_cache[p["agen"]], server_cache[p["server"]]
        # Aksi tool
        aksi = d.activity(f"{NS_K}:{p['tool']}-{n}", _ts(p["waktu"]), None,
                          {PROV_LABEL: p["tool"], f"{NS_K}:server": p["server"],
                           **({f"{NS_K}:tujuan": p["params"]["ke"]} if "ke" in p["params"] else {})})
        d.wasAssociatedWith(aksi, agen)
        d.wasAssociatedWith(aksi, server)

        # Keputusan governance yang mendahului aksi
        evaluasi = d.activity(f"{NS_G}:evaluasi-{n}", _ts(p["waktu"]), None, {PROV_LABEL: "evaluasi kebijakan"})
        d.wasAssociatedWith(evaluasi, gateway, kebijakan)
        d.used(evaluasi, kebijakan)
        keputusan = d.entity(f"{NS_G}:keputusan-{n}", {PROV_LABEL: p["keputusan"],
                                                      f"{NS_G}:alasan": p["alasan"]})
        d.wasGeneratedBy(keputusan, evaluasi)
        d.wasInformedBy(aksi, evaluasi)

        # Data masukan aksi (parameter) — ditautkan ke data sebelumnya bila berasal darinya
        if "isi" in p["params"]:
            isi = d.entity(f"{NS_K}:isi-{p['tool']}-{n}", {PROV_LABEL: "isi pesan"})
            d.used(aksi, isi)
            d.used(evaluasi, isi)
            for asal, teks_asal in data_keluar:
                if _berasal_dari(p["params"]["isi"], teks_asal):
                    d.wasDerivedFrom(isi, asal)

        # Data keluaran aksi (respons)
        if p.get("respons"):
            label = sensitif.get(p["tool"], "umum")
            hasil = d.entity(f"{NS_K}:respons-{p['tool']}-{n}",
                             {PROV_LABEL: "transkrip" if p["tool"] == "baca_nilai" else "respons",
                              f"{NS_G}:sensitivitas": label})
            d.wasGeneratedBy(hasil, aksi, _ts(p["waktu"]))
            data_keluar.append((hasil, p["respons"]))
    return d


# ── Kueri forensik: "data ini mengalir ke mana saja?" ────────────────────────
def telusuri_hilir(doc, id_entitas):
    """Mengikuti relasi used / wasDerivedFrom dari sebuah entitas. Mengembalikan daftar langkah."""
    from prov.model import ProvDerivation, ProvUsage, ProvActivity
    rec = {str(r.identifier): r for r in doc.get_records() if r.identifier is not None}
    turunan, pemakai = {}, {}
    for r in doc.get_records(ProvDerivation):
        a = dict(r.formal_attributes)
        turunan.setdefault(str(a[r.FORMAL_ATTRIBUTES[1]]), []).append(str(a[r.FORMAL_ATTRIBUTES[0]]))
    for r in doc.get_records(ProvUsage):
        a = dict(r.formal_attributes)
        pemakai.setdefault(str(a[r.FORMAL_ATTRIBUTES[1]]), []).append(str(a[r.FORMAL_ATTRIBUTES[0]]))

    langkah, antre = [], [id_entitas]
    while antre:
        e = antre.pop(0)
        for t in turunan.get(e, []):
            langkah.append((e, "menjadi bahan bagi (wasDerivedFrom) →", t)); antre.append(t)
        for act in pemakai.get(e, []):
            if not act.startswith(f"{NS_K}:"):
                continue                     # lewati aktivitas evaluasi governance
            atr = {str(k): str(v) for k, v in rec[act].attributes} if act in rec else {}
            langkah.append((e, "dipakai oleh (used) →", act + (f"  [tujuan: {atr.get(f'{NS_K}:tujuan')}]"
                                                  if f"{NS_K}:tujuan" in atr else "")))
    return langkah


# ── Gambar graf (konvensi visual PROV: Entity elips kuning, Activity kotak biru, Agent oranye) ─
def gambar_graf(doc, path, sorot=()):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Ellipse, FancyBboxPatch, Polygon
    from prov.model import ProvEntity, ProvActivity, ProvAgent

    # Tata letak tetap, fokus pada jalur eksfiltrasi (id → (x, y)).
    # Email sah ke dosen wali (no. 3) tetap ada di file PROV, tidak digambar agar graf terbaca.
    posisi = {
        "kampus:asisten-akademik": (9.6, 7.6),
        "kampus:server-siakad": (1.3, 5.0), "kampus:baca_nilai-1": (4.6, 5.0),
        "kampus:respons-baca_nilai-1": (8.0, 5.0),
        "kampus:isi-kirim_email-2": (11.3, 5.0),
        "kampus:kirim_email-2": (14.6, 5.0), "kampus:server-pesan": (17.9, 5.0),
        "gov:evaluasi-1": (4.6, 2.7), "gov:keputusan-1": (1.3, 2.7),
        "gov:evaluasi-2": (14.6, 2.7), "gov:keputusan-2": (17.9, 2.7),
        "gov:kebijakan-asisten-akademik-v1.0.0": (9.6, 2.7), "gov:gateway-AGT": (9.6, 1.0),
    }
    fig, ax = plt.subplots(figsize=(19, 9.4))
    ax.set_xlim(0, 19.3); ax.set_ylim(0.0, 9.4); ax.axis("off")

    def label(r):
        atr = {str(k): str(v) for k, v in r.attributes}
        lab, sens = atr.get("prov:label"), atr.get("gov:sensitivitas")
        nama = str(r.identifier).split(":", 1)[1]
        if nama.startswith("kebijakan"):
            return "kebijakan\nasisten-akademik v1.0.0\n(prov:Plan)"
        if nama == "gateway-AGT":
            return "gateway-AGT\n(MCPGateway)"
        if lab in ("IZINKAN", "TOLAK"):
            return f"{nama}\n{lab}"
        teks = nama if not lab or lab in ("evaluasi kebijakan", "baca_nilai", "kirim_email") else f"{nama}\n({lab})"
        if "tujuan" in " ".join(atr):
            teks += "\nke: pihak luar"
        if sens:
            teks += "\n⚠ data kesehatan"
        return teks

    for r in doc.get_records():
        if r.identifier is None or str(r.identifier) not in posisi:
            continue
        x, y = posisi[str(r.identifier)]
        hot = str(r.identifier) in sorot
        ec = "#C0392B" if hot else "#555"
        lw = 2.6 if hot else 1.2
        if isinstance(r, ProvEntity):
            ax.add_patch(Ellipse((x, y), 2.65, 1.1, fc="#FFFC87", ec=ec, lw=lw, zorder=2))
        elif isinstance(r, ProvActivity):
            ax.add_patch(FancyBboxPatch((x - 1.15, y - 0.45), 2.3, 0.9, boxstyle="round,pad=0.03",
                                        fc="#9FB1FC", ec=ec, lw=lw, zorder=2))
        elif isinstance(r, ProvAgent):
            ax.add_patch(Polygon([(x - 1.1, y - 0.42), (x + 1.1, y - 0.42), (x + 1.1, y + 0.22),
                                  (x, y + 0.55), (x - 1.1, y + 0.22)], fc="#FED37F", ec=ec, lw=lw, zorder=2))
        ax.text(x, y, label(r), ha="center", va="center", fontsize=8.4, zorder=3,
                fontweight="bold" if hot else "normal")

    # Relasi
    from prov.model import (ProvGeneration, ProvUsage, ProvDerivation, ProvAssociation,
                            ProvCommunication)
    nama_rel = {ProvGeneration: "wasGeneratedBy", ProvUsage: "used", ProvDerivation: "wasDerivedFrom",
                ProvAssociation: "wasAssociatedWith", ProvCommunication: "wasInformedBy"}
    jenis = {str(r.identifier): ("E" if isinstance(r, ProvEntity) else "A" if isinstance(r, ProvActivity) else "G")
             for r in doc.get_records() if r.identifier is not None}

    def tepi(cx, cy, dx, dy, j):
        """Titik pada tepi bentuk node j (E elips, A kotak, G segilima≈kotak) searah (dx, dy)."""
        import math
        if j == "E":
            t = 1 / math.sqrt((dx / 1.36) ** 2 + (dy / 0.58) ** 2)
        else:
            hw, hh = (1.2, 0.5) if j == "A" else (1.12, 0.52)
            t = min(hw / abs(dx) if dx else 1e9, hh / abs(dy) if dy else 1e9)
        return cx + dx * t, cy + dy * t

    for r in doc.get_records(tuple(nama_rel)):
        fa = [v for _, v in r.formal_attributes]
        a, b = str(fa[0]), str(fa[1])
        if a not in posisi or b not in posisi:
            continue
        (x1, y1), (x2, y2) = posisi[a], posisi[b]
        hot = a in sorot and b in sorot
        dx, dy = x2 - x1, y2 - y1
        p1 = tepi(x1, y1, dx, dy, jenis[a])
        p2 = tepi(x2, y2, -dx, -dy, jenis[b])
        ax.annotate("", xy=p2, xytext=p1,
                    arrowprops=dict(arrowstyle="-|>,head_length=0.6,head_width=0.3",
                                    color="#C0392B" if hot else "#888",
                                    lw=2.4 if hot else 1.0, shrinkA=0, shrinkB=2), zorder=4)
        ax.text((p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2 + 0.14, nama_rel[type(r)], fontsize=7.2,
                color="#C0392B" if hot else "#666", ha="center", zorder=4,
                bbox=dict(fc="white", ec="none", pad=0.5))

    ax.text(0.2, 9.0, "Jejak W3C PROV-DM — peristiwa sama dengan log AGT (Adegan 5, Konfigurasi A)",
            fontsize=13, fontweight="bold")
    ax.text(0.2, 8.55, "Merah = jalur forensik: transkrip (data kesehatan) → isi email → dikirim ke pihak luar",
            fontsize=10, color="#C0392B")
    ax.text(0.2, 0.12, "Elips kuning = Entity (data)   Kotak biru = Activity (kegiatan)   "
            "Segilima oranye = Agent (pelaku)   |   Arah panah PROV menunjuk ke masa lalu: dari hasil ke penyebabnya", fontsize=9, color="#444")
    fig.savefig(path, dpi=130, bbox_inches="tight", facecolor="white")
    plt.close(fig)

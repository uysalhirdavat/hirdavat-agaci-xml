import csv
import time
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from urun_detaylarini_cek import GIRIS, ALANLAR, urun_oku

CSV_CIKIS = Path("tum_urunler.csv")
XML_CIKIS = Path("tum_urunler.xml")
HATA_CIKIS = Path("urun_hatalari.csv")
RAPOR = Path("xml_kontrol_raporu.txt")

def metin(parent, tag, value):
    ET.SubElement(parent, tag).text = str(value or "")

def calistir():
    if not GIRIS.exists():
        raise SystemExit("Urun baglantilari yok: once urunleri_cek.py calistirilmali.")
    with GIRIS.open(encoding="utf-8-sig", newline="") as f:
        adresler = list(dict.fromkeys(
            r["url"].strip() for r in csv.DictReader(f) if r.get("url", "").strip()
        ))
    if not adresler:
        raise SystemExit("Hic urun baglantisi bulunamadi.")
    print("Toplam urun baglantisi:", len(adresler), flush=True)
    baslangic = time.monotonic()
    hatalar = []
    eksikler = Counter()
    markalar = Counter()
    kdvler = Counter()
    kodlar = set()
    kok = ET.Element("Urunler")
    basarili = 0
    with CSV_CIKIS.open("w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.DictWriter(dosya, fieldnames=ALANLAR)
        yazici.writeheader()
        for i, adres in enumerate(adresler, 1):
            try:
                kayit = urun_oku(adres)
                if kayit["stok_kodu"] and kayit["stok_kodu"] in kodlar:
                    raise ValueError("Tekrarlanan stok kodu")
                if kayit["stok_kodu"]:
                    kodlar.add(kayit["stok_kodu"])
                yazici.writerow(kayit)
                urun = ET.SubElement(kok, "Urun")
                for alan in ALANLAR:
                    metin(urun, alan, kayit[alan])
                    if not kayit[alan]:
                        eksikler[alan] += 1
                markalar[kayit["marka"] or "(bos)"] += 1
                kdvler[kayit["kdv"] or "(bos)"] += 1
                basarili += 1
            except Exception as hata:
                hatalar.append({"url": adres, "hata": str(hata)})
                print(f"HATA {i}/{len(adresler)}: {adres} - {hata}", flush=True)
            if i % 25 == 0 or i == len(adresler):
                print(f"ILERI {i}/{len(adresler)} | basarili={basarili} | hata={len(hatalar)}", flush=True)
    with HATA_CIKIS.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["url", "hata"])
        w.writeheader()
        w.writerows(hatalar)
    if basarili:
        ET.indent(kok, space="  ")
        ET.ElementTree(kok).write(XML_CIKIS, encoding="utf-8", xml_declaration=True)
        ET.parse(XML_CIKIS)
    satirlar = [
        f"Baglanti sayisi: {len(adresler)}",
        f"XML urun sayisi: {basarili}",
        f"Hata sayisi: {len(hatalar)}",
        f"Sure (dakika): {(time.monotonic()-baslangic)/60:.1f}",
        "Eksik alanlar: " + ", ".join(f"{k}={v}" for k, v in sorted(eksikler.items())),
        "Markalar: " + ", ".join(f"{k}={v}" for k, v in markalar.most_common()),
        "KDV oranlari: " + ", ".join(f"{k}={v}" for k, v in kdvler.most_common()),
        "NOT: Fiyatlar kaynaktan aynen alinmistir; KDV fiyatlara eklenmemistir.",
        "NOT: Bu genel XML kontrol ciktisidir; Entegra alan eslemesi ayrica dogrulanmalidir.",
        "NOT: Hatalar varsa XML eksiktir, canli aktarimda kullanmayin."
    ]
    RAPOR.write_text("\n".join(satirlar) + "\n", encoding="utf-8")
    print("\n".join(satirlar), flush=True)
    if hatalar or basarili != len(adresler):
        raise SystemExit("Eksik tarama: raporu ve hata CSV dosyasini inceleyin.")

if __name__ == "__main__":
    calistir()

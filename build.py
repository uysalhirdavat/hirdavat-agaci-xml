
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

KAYNAK = Path("urunler.csv")
CIKTI = Path("urunler.xml")

ALANLAR = [
    "id", "code", "label", "stock",
    "details", "currency", "price1",
    "tax", "barcode", "brand",
    "mainCategory", "category", "picture1"
]

def xml_olustur():
    if not KAYNAK.exists():
        raise SystemExit("urunler.csv bulunamadi.")

    with KAYNAK.open(encoding="utf-8-sig", newline="") as dosya:
        urunler = list(csv.DictReader(dosya))

    if not urunler:
        raise SystemExit("Urun listesi bos.")

    for urun in urunler:
        for alan in ["id", "code", "label", "stock",
                     "price1", "barcode", "picture1"]:
            if not urun.get(alan, "").strip():
                raise SystemExit(
                    f"Eksik veri: {urun.get('id', '?')} - {alan}"
                )

    kok = ET.Element("root")

    for urun in urunler:
        kayit = ET.SubElement(kok, "item")

        for alan in ALANLAR:
            ET.SubElement(kayit, alan).text = urun.get(alan, "")

    agac = ET.ElementTree(kok)
    ET.indent(agac, space="  ")
    agac.write(CIKTI, encoding="utf-8", xml_declaration=True)

    print(f"{len(urunler)} urun XML dosyasina yazildi.")

if __name__ == "__main__":
    xml_olustur()

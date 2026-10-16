
import csv
import json
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
GIRIS = Path("urun_baglantilari.csv")
CIKIS = Path("urun_detay_test.csv")

TEST_ADEDI = 10
BEKLEME = 3
USER_AGENT = "UysalHirdavatXML/1.0"

oturum = requests.Session()
oturum.headers.update({"User-Agent": USER_AGENT})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")
robots.read()


def metin_bul(html, seciciler):
    for secici in seciciler:
        eleman = html.select_one(secici)
        if eleman:
            deger = (
                eleman.get("content")
                or eleman.get_text(" ", strip=True)
            )
            if deger:
                return str(deger).strip()
    return ""


def jsonld_urun(html):
    for script in html.select('script[type="application/ld+json"]'):
        try:
            veri = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue

        kuyruk = veri if isinstance(veri, list) else [veri]

        while kuyruk:
            kayit = kuyruk.pop(0)

            if not isinstance(kayit, dict):
                continue

            tip = kayit.get("@type", "")
            tipler = tip if isinstance(tip, list) else [tip]

            if "Product" in tipler:
                return kayit

            grafik = kayit.get("@graph", [])
            if isinstance(grafik, list):
                kuyruk.extend(grafik)

    return {}


def duz_metin(deger):
    if isinstance(deger, dict):
        return str(deger.get("name", ""))
    if isinstance(deger, list):
        return ", ".join(
            duz_metin(x) for x in deger if x
        )
    return str(deger or "")


def urun_oku(adres):
    parca = urlparse(adres)

    if (
        parca.scheme != "https"
        or parca.netloc != "www.hirdavatagaci.com"
        or not parca.path.startswith("/urun/")
    ):
        raise ValueError("Gecersiz urun adresi")

    if not robots.can_fetch(USER_AGENT, adres):
        raise RuntimeError(
            "robots.txt urun sayfasina izin vermiyor"
        )

    time.sleep(BEKLEME)

    cevap = oturum.get(adres, timeout=30)
    cevap.raise_for_status()

    html = BeautifulSoup(cevap.text, "html.parser")
    veri = jsonld_urun(html)

    ad = (
        duz_metin(veri.get("name"))
        or metin_bul(html, ["h1", '[itemprop="name"]'])
    )

    stok_kodu = (
        duz_metin(veri.get("sku"))
        or metin_bul(
            html,
            ['[itemprop="sku"]', ".product-code"]
        )
    )

    barkod = (
        duz_metin(
            veri.get("gtin13")
            or veri.get("gtin")
            or veri.get("gtin14")
            or veri.get("gtin12")
        )
        or metin_bul(
            html,
            [
                '[itemprop="gtin13"]',
                '[itemprop="gtin"]'
            ]
        )
    )

    marka = (
        duz_metin(veri.get("brand"))
        or metin_bul(
            html,
            ['[itemprop="brand"]', ".product-brand"]
        )
    )

    teklifler = veri.get("offers", {})
    if isinstance(teklifler, list):
        teklifler = teklifler[0] if teklifler else {}
    if not isinstance(teklifler, dict):
        teklifler = {}

    fiyat = (
        duz_metin(teklifler.get("price"))
        or metin_bul(
            html,
            [
                '[itemprop="price"]',
                ".product-price",
                ".current-price"
            ]
        )
    )

    para_birimi = duz_metin(
        teklifler.get("priceCurrency")
    )

    stok = ""
    stok_alani = html.select_one(
        "#qty-input[data-stockamount], [data-stockamount]"
    )

    if stok_alani:
        stok = str(
            stok_alani.get("data-stockamount", "")
        )

    aciklama = (
        duz_metin(veri.get("description"))
        or metin_bul(
            html,
            [
                '[itemprop="description"]',
                ".product-description"
            ]
        )
    )

    gorsel = ""
    resim = html.select_one(
        'meta[property="og:image"]'
    )

    if resim:
        gorsel = resim.get("content", "")

    if not gorsel:
        gorsel = duz_metin(veri.get("image"))

    if not ad:
        raise ValueError("Urun adi okunamadi")

    return [
        adres,
        ad,
        stok_kodu,
        barkod,
        marka,
        fiyat,
        para_birimi,
        stok,
        aciklama,
        gorsel
    ]


def calistir():
    if not GIRIS.exists():
        raise SystemExit(
            "Urun listesi olusmadi. "
            "Once urunleri_cek.py calismali."
        )

    with GIRIS.open(
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        adresler = [
            satir["url"].strip()
            for satir in csv.DictReader(dosya)
            if satir.get("url", "").strip()
        ]

    if len(adresler) < TEST_ADEDI:
        raise SystemExit(
            "Test icin yeterli urun bulunamadi."
        )

    sonuclar = []

    for sira, adres in enumerate(
        adresler[:TEST_ADEDI], 1
    ):
        print(
            f"Urun {sira}/{TEST_ADEDI}: {adres}",
            flush=True
        )

        try:
            kayit = urun_oku(adres)
            sonuclar.append(kayit)

            print(
                "Okundu:",
                kayit[1],
                "| Fiyat:",
                kayit[5],
                "| Stok:",
                kayit[7],
                flush=True
            )

        except Exception as hata:
            raise SystemExit(
                f"Test durduruldu: {adres} - {hata}"
            )

    with CIKIS.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow([
            "url",
            "urun_adi",
            "stok_kodu",
            "barkod",
            "marka",
            "fiyat",
            "para_birimi",
            "stok",
            "aciklama",
            "gorsel"
        ])
        yazici.writerows(sonuclar)

    print("\nTEST TAMAMLANDI")
    print("Okunan urun:", len(sonuclar))
    print("Dosya:", CIKIS)


if __name__ == "__main__":
    calistir()


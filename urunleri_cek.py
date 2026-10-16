
import csv
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
            deger = eleman.get_text(" ", strip=True)
            if deger:
                return deger
    return ""


def urun_oku(adres):
    parca = urlparse(adres)

    if (
        parca.scheme != "https"
        or parca.netloc != "www.hirdavatagaci.com"
        or not parca.path.startswith("/urun/")
    ):
        raise ValueError("Gecersiz urun adresi")

    if not robots.can_fetch(USER_AGENT, adres):
        raise RuntimeError("robots.txt erisime izin vermiyor")

    time.sleep(BEKLEME)

    cevap = oturum.get(adres, timeout=30)
    cevap.raise_for_status()

    html = BeautifulSoup(cevap.text, "html.parser")

    ad = metin_bul(html, [
        "h1",
        '[itemprop="name"]'
    ])

    fiyat = metin_bul(html, [
        '[itemprop="price"]',
        ".product-price",
        ".current-price"
    ])

    stok_kodu = metin_bul(html, [
        ".product-code",
        '[itemprop="sku"]'
    ])

    marka = metin_bul(html, [
        '[itemprop="brand"]',
        ".product-brand"
    ])

    aciklama = metin_bul(html, [
        '[itemprop="description"]',
        ".product-description"
    ])

    stok = ""
    stok_alani = html.select_one(
        '[data-stockamount]'
    )

    if stok_alani:
        stok = stok_alani.get("data-stockamount", "")

    barkod = ""
    barkod_alani = html.select_one(
        '[itemprop="gtin13"], [itemprop="gtin"]'
    )

    if barkod_alani:
        barkod = (
            barkod_alani.get("content")
            or barkod_alani.get_text(strip=True)
        )

    gorsel = ""
    resim = html.select_one(
        'meta[property="og:image"]'
    )

    if resim:
        gorsel = resim.get("content", "")

    return [
        adres,
        ad,
        stok_kodu,
        barkod,
        marka,
        fiyat,
        stok,
        aciklama,
        gorsel
    ]


def calistir():
    if not GIRIS.exists():
        raise SystemExit(
            "urun_baglantilari.csv bulunamadi."
        )

    with GIRIS.open(
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        adresler = [
            satir["url"]
            for satir in csv.DictReader(dosya)
            if satir.get("url")
        ]

    if not adresler:
        raise SystemExit("Urun adresi bulunamadi.")

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
            "stok",
            "aciklama",
            "gorsel"
        ])
        yazici.writerows(sonuclar)

    print("Test tamamlandi.")
    print("Okunan urun:", len(sonuclar))
    print("Dosya:", CIKIS)


if __name__ == "__main__":
    calistir()

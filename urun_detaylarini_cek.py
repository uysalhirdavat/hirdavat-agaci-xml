
import csv
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
GIRIS = Path("urun_baglantilari.csv")
CIKIS = Path("urun_detay_test.csv")

TEST_ADEDI = 10
BEKLEME = 3
USER_AGENT = "UysalHirdavatXML/1.0"

ALANLAR = [
    "url", "urun_adi", "stok_kodu", "barkod",
    "marka", "kategori", "fiyat", "para_birimi",
    "kdv", "stok", "aciklama", "gorsel"
]

oturum = requests.Session()
oturum.headers.update({"User-Agent": USER_AGENT})

robots = RobotFileParser()
try:
    cevap = oturum.get(SITE + "/robots.txt", timeout=30)
    cevap.raise_for_status()
    robots.parse(cevap.text.splitlines())
except requests.RequestException as hata:
    raise SystemExit(f"robots.txt okunamadi: {hata}")


def temiz_metin(deger):
    if deger is None:
        return ""
    return re.sub(r"\s+", " ", str(deger)).strip()


def duz_metin(deger):
    if isinstance(deger, dict):
        return temiz_metin(
            deger.get("name")
            or deger.get("value")
            or deger.get("url")
            or ""
        )
    if isinstance(deger, list):
        return ", ".join(
            duz_metin(x) for x in deger if x
        )
    return temiz_metin(deger)


def metin_bul(html, seciciler):
    for secici in seciciler:
        eleman = html.select_one(secici)
        if eleman:
            deger = (
                eleman.get("content")
                or eleman.get("value")
                or eleman.get("data-value")
                or eleman.get_text(" ", strip=True)
            )
            if temiz_metin(deger):
                return temiz_metin(deger)
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
    veri = jsonld_urun(html)

    ad = (
        duz_metin(veri.get("name"))
        or metin_bul(html, ["h1", '[itemprop="name"]'])
    )

    stok_kodu = (
        duz_metin(veri.get("sku"))
        or metin_bul(html, [
            '[itemprop="sku"]',
            ".product-code"
        ])
    )

    barkod = (
        duz_metin(
            veri.get("gtin13")
            or veri.get("gtin")
            or veri.get("gtin14")
            or veri.get("gtin12")
        )
        or metin_bul(html, [
            '[itemprop="gtin13"]',
            '[itemprop="gtin"]'
        ])
    )

    marka = (
        duz_metin(veri.get("brand"))
        or metin_bul(html, [
            '[itemprop="brand"]',
            ".product-brand",
            ".product-list-row.product-brands .product-list-content",
            '[data-brand]',
            'meta[property="product:brand"]'
        ])
    )
    # Urun adindan yalnizca kesin taninan marka on ekini kullan.
    if not marka and re.match(r"^AEG(?:\s|$)", ad, re.I):
        marka = "AEG"

    teklifler = veri.get("offers", {})
    if isinstance(teklifler, list):
        teklifler = teklifler[0] if teklifler else {}
    if not isinstance(teklifler, dict):
        teklifler = {}

    fiyat = (
        duz_metin(teklifler.get("price"))
        or metin_bul(html, [
            'meta[itemprop="price"]',
            '[itemprop="price"]',
            ".product-price",
            ".current-price"
        ])
    )

    para_birimi = (
        duz_metin(teklifler.get("priceCurrency"))
        or metin_bul(html, [
            'meta[itemprop="priceCurrency"]'
        ])
    )

    stok = ""
    stok_alani = html.select_one(
        "#qty-input[data-stockamount], [data-stockamount]"
    )
    if stok_alani:
        stok = temiz_metin(
            stok_alani.get("data-stockamount")
        )

    kategori = ""
    # Schema.org breadcrumb yolundan kategori oku.
    for script in html.select('script[type="application/ld+json"]'):
        try:
            kok = json.loads(script.string or script.get_text())
        except (ValueError, TypeError):
            continue
        kuyruk = kok if isinstance(kok, list) else [kok]
        while kuyruk:
            oge = kuyruk.pop(0)
            if not isinstance(oge, dict):
                continue
            tip = oge.get("@type", "")
            tipler = tip if isinstance(tip, list) else [tip]
            if "BreadcrumbList" in tipler:
                elemanlar = oge.get("itemListElement", [])
                if isinstance(elemanlar, list):
                    adlar = []
                    for eleman in elemanlar:
                        if not isinstance(eleman, dict):
                            continue
                        yazi = duz_metin(eleman.get("name") or eleman.get("item"))
                        if yazi and yazi.lower() not in ("anasayfa", "ana sayfa", "home", ad.lower()):
                            adlar.append(yazi)
                    if adlar:
                        kategori = adlar[-1]
            grafik = oge.get("@graph", [])
            if isinstance(grafik, list):
                kuyruk.extend(grafik)
    if not kategori:
        for eleman in html.select(
            '.breadcrumb a[href*="/kategori/"], '
            '.breadcrumbs a[href*="/kategori/"], '
            '[aria-label="breadcrumb"] a[href*="/kategori/"], '
            '.breadcrumb-item a[href*="/kategori/"]'
        ):
            yazi = eleman.get_text(" ", strip=True)
            if yazi:
                kategori = temiz_metin(yazi)
    if not kategori:
        kategori = metin_bul(html, [
            '.product-list-row .product-list-content a[href*="/kategori/"]',
            'ol[typeof="BreadcrumbList"] a[href*="/kategori/"]'
        ])
    if not kategori:
        print(f"UYARI: Kategori bulunamadi: {adres}", flush=True)

    aciklama = (
        duz_metin(veri.get("description"))
        or metin_bul(html, [
            '[itemprop="description"]',
            ".product-description"
        ])
    )

    gorsel = metin_bul(html, [
        'meta[property="og:image"]'
    ])
    if not gorsel:
        gorsel = duz_metin(veri.get("image"))
    if gorsel:
        gorsel = urljoin(adres, gorsel)

    # KDV kaynaktan dogrulanamiyorsa bos birak.
    kdv = ""

    if not ad:
        raise ValueError("Urun adi okunamadi")
    if not fiyat:
        raise ValueError("Fiyat okunamadi")
    if not stok:
        raise ValueError("Stok okunamadi")

    return {
        "url": adres,
        "urun_adi": ad,
        "stok_kodu": stok_kodu,
        "barkod": barkod,
        "marka": marka,
        "kategori": kategori,
        "fiyat": fiyat,
        "para_birimi": para_birimi,
        "kdv": kdv,
        "stok": stok,
        "aciklama": aciklama,
        "gorsel": gorsel
    }


def calistir():
    if not GIRIS.exists():
        raise SystemExit(
            "urun_baglantilari.csv bulunamadi. "
            "Once urunleri_cek.py calismali."
        )

    with GIRIS.open(
        encoding="utf-8-sig", newline=""
    ) as dosya:
        adresler = [
            satir["url"].strip()
            for satir in csv.DictReader(dosya)
            if satir.get("url", "").strip()
        ]

    if len(adresler) < TEST_ADEDI:
        raise SystemExit("Yeterli urun baglantisi yok.")

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
        except Exception as hata:
            raise SystemExit(
                f"Urun okunamadi: {adres} - {hata}"
            )

        sonuclar.append(kayit)

        print(
            "Ad:", kayit["urun_adi"],
            "| Marka:", kayit["marka"],
            "| Kategori:", kayit["kategori"],
            "| Kod:", kayit["stok_kodu"],
            "| Barkod:", kayit["barkod"],
            "| Fiyat:", kayit["fiyat"],
            "| Stok:", kayit["stok"],
            flush=True
        )

    if len(sonuclar) != TEST_ADEDI:
        raise SystemExit("Test eksik. CSV olusturulmadi.")

    with CIKIS.open(
        "w", encoding="utf-8-sig", newline=""
    ) as dosya:
        yazici = csv.DictWriter(
            dosya, fieldnames=ALANLAR
        )
        yazici.writeheader()
        yazici.writerows(sonuclar)

    if not CIKIS.exists() or CIKIS.stat().st_size == 0:
        raise SystemExit("CSV dosyasi olusturulamadi.")

    print("\nTEST TAMAMLANDI", flush=True)
    print("Okunan urun:", len(sonuclar), flush=True)
    print("Dosya:", CIKIS, flush=True)
    print("KDV: Dogrulanamadi, bos birakildi.", flush=True)


if __name__ == "__main__":
    calistir()

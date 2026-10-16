
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
                or eleman.get("value")
                or eleman.get_text(" ", strip=True)
            )
            if deger:
                return str(deger).strip()
    return ""


def duz_metin(deger):
    if isinstance(deger, dict):
        return str(deger.get("name", ""))
    if isinstance(deger, list):
        return ", ".join(
            duz_metin(x) for x in deger if x
        )
    return str(deger or "").strip()


def jsonld_urun(html):
    def tara(nesne):
        if isinstance(nesne, list):
            for oge in nesne:
                sonuc = tara(oge)
                if sonuc:
                    return sonuc

        elif isinstance(nesne, dict):
            tip = nesne.get("@type", [])
            tipler = tip if isinstance(tip, list) else [tip]

            if "Product" in tipler:
                return nesne

            for anahtar in ("@graph", "mainEntity", "itemListElement"):
                sonuc = tara(nesne.get(anahtar))
                if sonuc:
                    return sonuc

        return {}

    for script in html.select('script[type="application/ld+json"]'):
        try:
            veri = json.loads(script.string or script.get_text())
            sonuc = tara(veri)
            if sonuc:
                return sonuc
        except (ValueError, TypeError):
            continue

    return {}


def teklif_bul(veri):
    teklifler = veri.get("offers", {})

    if isinstance(teklifler, list):
        teklifler = teklifler[0] if teklifler else {}

    if not isinstance(teklifler, dict):
        return {}

    return teklifler


def marka_bul(html, veri):
    marka = duz_metin(veri.get("brand"))

    if marka:
        return marka, "JSON-LD"

    marka = metin_bul(html, [
        '[itemprop="brand"]',
        ".product-brand",
        ".brand-name",
        '[class*="brand-name"]'
    ])

    if marka:
        return marka, "HTML"

    # Marka bilinmiyorsa tahmin etmiyoruz.
    return "", "BULUNAMADI"


def fiyat_bul(html, veri):
    teklif = teklif_bul(veri)

    fiyat = duz_metin(teklif.get("price"))
    kaynak = "JSON-LD" if fiyat else ""

    if not fiyat:
        fiyat = metin_bul(html, [
            'meta[itemprop="price"]',
            '[itemprop="price"]',
            ".product-price",
            ".current-price"
        ])
        if fiyat:
            kaynak = "HTML"

    para_birimi = duz_metin(
        teklif.get("priceCurrency")
    )

    if not para_birimi:
        para_birimi = metin_bul(html, [
            'meta[itemprop="priceCurrency"]',
            '[itemprop="priceCurrency"]'
        ])

    if not para_birimi:
        # Yalnizca fiyat metnindeki para birimini kontrol et.
        if re.search(r"\bTRY\b|₺|\bTL\b", fiyat, re.I):
            para_birimi = "TRY"
        elif re.search(r"\bUSD\b|\$", fiyat, re.I):
            para_birimi = "USD"
        elif re.search(r"\bEUR\b|€", fiyat, re.I):
            para_birimi = "EUR"

    return fiyat, para_birimi, kaynak


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
            "robots.txt erisime izin vermiyor"
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
        or metin_bul(html, [
            '[itemprop="sku"]',
            ".product-code"
        ])
    )

    barkod = (
        duz_metin(
            veri.get("gtin13")
            or veri.get("gtin14")
            or veri.get("gtin12")
            or veri.get("gtin")
        )
        or metin_bul(html, [
            '[itemprop="gtin13"]',
            '[itemprop="gtin"]'
        ])
    )

    marka, marka_kaynagi = marka_bul(html, veri)
    fiyat, para_birimi, fiyat_kaynagi = fiyat_bul(
        html, veri
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
        or metin_bul(html, [
            '[itemprop="description"]',
            ".product-description"
        ])
    )

    gorsel = metin_bul(html, [
        'meta[property="og:image"]'
    ])

    if not gorsel:
        resim = veri.get("image", "")
        if isinstance(resim, list):
            resim = resim[0] if resim else ""
        if isinstance(resim, dict):
            resim = resim.get("url", "")
        gorsel = str(resim or "")

    if gorsel:
        gorsel = urljoin(adres, gorsel)

    if not ad:
        raise ValueError("Urun adi okunamadi")

    return {
        "url": adres,
        "urun_adi": ad,
        "stok_kodu": stok_kodu,
        "barkod": barkod,
        "marka": marka,
        "marka_kaynagi": marka_kaynagi,
        "fiyat": fiyat,
        "para_birimi": para_birimi,
        "fiyat_kaynagi": fiyat_kaynagi,
        "kdv_durumu": "DOGRULANMADI",
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
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        adresler = [
            satir["url"].strip()
            for satir in csv.DictReader(dosya)
            if satir.get("url", "").strip()
        ]

    if len(adresler) < TEST_ADEDI:
        raise SystemExit("Yeterli urun bulunamadi.")

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
                "Ad:", kayit["urun_adi"],
                "| Marka:", kayit["marka"] or "BOS",
                "| Fiyat:", kayit["fiyat"] or "BOS",
                "| Para:", kayit["para_birimi"] or "BOS",
                "| Stok:", kayit["stok"] or "BOS",
                flush=True
            )

        except Exception as hata:
            raise SystemExit(
                f"Test durduruldu: {adres} - {hata}"
            )

    alanlar = [
        "url",
        "urun_adi",
        "stok_kodu",
        "barkod",
        "marka",
        "marka_kaynagi",
        "fiyat",
        "para_birimi",
        "fiyat_kaynagi",
        "kdv_durumu",
        "stok",
        "aciklama",
        "gorsel"
    ]

    with CIKIS.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        yazici = csv.DictWriter(
            dosya, fieldnames=alanlar
        )
        yazici.writeheader()
        yazici.writerows(sonuclar)

    print("\nTEST TAMAMLANDI")
    print("Okunan urun:", len(sonuclar))
    print(
        "Markasi bulunan:",
        sum(bool(x["marka"]) for x in sonuclar)
    )
    print(
        "Para birimi bulunan:",
        sum(bool(x["para_birimi"]) for x in sonuclar)
    )
    print("Dosya:", CIKIS)


if __name__ == "__main__":
    calistir()

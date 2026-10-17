
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
    "url",
    "urun_adi",
    "stok_kodu",
    "barkod",
    "marka",
    "kategori",
    "fiyat",
    "para_birimi",
    "kdv",
    "stok",
    "aciklama",
    "gorsel",
]

oturum = requests.Session()
oturum.headers.update({"User-Agent": USER_AGENT})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")

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
        return duz_metin(
            deger.get("name")
            or deger.get("value")
            or deger.get("url")
        )

    if isinstance(deger, list):
        return ", ".join(
            duz_metin(x) for x in deger if x
        )

    return temiz_metin(deger)


def metin_bul(html, seciciler):
    for secici in seciciler:
        eleman = html.select_one(secici)
        if eleman is None:
            continue

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
    kuyruk = []

    for script in html.select(
        'script[type="application/ld+json"]'
    ):
        try:
            veri = json.loads(
                script.string or script.get_text()
            )
        except (ValueError, TypeError):
            continue

        if isinstance(veri, list):
            kuyruk.extend(veri)
        else:
            kuyruk.append(veri)

    while kuyruk:
        kayit = kuyruk.pop(0)

        if isinstance(kayit, list):
            kuyruk.extend(kayit)
            continue

        if not isinstance(kayit, dict):
            continue

        tip = kayit.get("@type", [])
        tipler = tip if isinstance(tip, list) else [tip]

        if any(
            str(x).split("/")[-1] == "Product"
            for x in tipler
        ):
            return kayit

        for anahtar in ("@graph", "mainEntity"):
            alt = kayit.get(anahtar, [])
            if isinstance(alt, list):
                kuyruk.extend(alt)
            elif isinstance(alt, dict):
                kuyruk.append(alt)

    return {}


def kategori_bul(html):
    seciciler = [
        ".breadcrumb li",
        ".breadcrumbs li",
        '[typeof="BreadcrumbList"]',
        ".breadcrumb a",
    ]

    for secici in seciciler:
        elemanlar = html.select(secici)

        if not elemanlar:
            continue

        degerler = [
            temiz_metin(x.get_text(" ", strip=True))
            for x in elemanlar
        ]

        degerler = [
            x for x in degerler
            if x and x.lower() not in (
                "anasayfa", "ana sayfa", "home"
            )
        ]

        if len(degerler) >= 2:
            return degerler[-2]

        if degerler:
            return degerler[-1]

    for script in html.select(
        'script[type="application/ld+json"]'
    ):
        try:
            veri = json.loads(
                script.string or script.get_text()
            )
        except (ValueError, TypeError):
            continue

        kuyruk = veri if isinstance(veri, list) else [veri]

        while kuyruk:
            kayit = kuyruk.pop(0)

            if not isinstance(kayit, dict):
                continue

            tip = kayit.get("@type", [])
            tipler = tip if isinstance(tip, list) else [tip]

            if "BreadcrumbList" in tipler:
                ogeler = kayit.get("itemListElement", [])
                isimler = [
                    duz_metin(x.get("name"))
                    for x in ogeler
                    if isinstance(x, dict)
                ]

                if len(isimler) >= 2:
                    return isimler[-2]

            grafik = kayit.get("@graph", [])
            if isinstance(grafik, list):
                kuyruk.extend(grafik)

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
        or metin_bul(html, [
            "h1",
            '[itemprop="name"]',
        ])
    )

    if not ad:
        raise ValueError("Urun adi bulunamadi")

    stok_kodu = (
        duz_metin(veri.get("sku"))
        or metin_bul(html, [
            '[itemprop="sku"]',
            ".product-code",
        ])
    )

    barkod = duz_metin(
        veri.get("gtin13")
        or veri.get("gtin14")
        or veri.get("gtin12")
        or veri.get("gtin")
    )

    if not barkod:
        barkod = metin_bul(html, [
            '[itemprop="gtin13"]',
            '[itemprop="gtin"]',
        ])

    marka = (
        duz_metin(veri.get("brand"))
        or metin_bul(html, [
            '[itemprop="brand"]',
            ".product-brand",
        ])
    )

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
            ".current-price",
        ])
    )

    para_birimi = (
        duz_metin(teklifler.get("priceCurrency"))
        or metin_bul(html, [
            'meta[itemprop="priceCurrency"]',
            '[itemprop="priceCurrency"]',
        ])
    )

    stok_alani = html.select_one(
        "#qty-input[data-stockamount], "
        "[data-stockamount]"
    )

    stok = ""
    if stok_alani is not None:
        stok = temiz_metin(
            stok_alani.get("data-stockamount")
        )

    kategori = kategori_bul(html)

    aciklama = (
        duz_metin(veri.get("description"))
        or metin_bul(html, [
            '[itemprop="description"]',
            ".product-description",
        ])
    )

    gorsel = metin_bul(html, [
        'meta[property="og:image"]'
    ])

    if not gorsel:
        resim = veri.get("image", "")
        gorsel = duz_metin(resim)

    if gorsel:
        gorsel = urljoin(adres, gorsel)

    # KDV orani dogrulanamiyorsa bos birakilir.
    # Fiyat uzerinden KDV tahmini yapilmaz.
    kdv = ""

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
        "gorsel": gorsel,
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
        okuyucu = csv.DictReader(dosya)

        adresler = list(dict.fromkeys(
            satir.get("url", "").strip()
            for satir in okuyucu
            if satir.get("url", "").strip()
        ))

    if len(adresler) < TEST_ADEDI:
        raise SystemExit(
            "Test icin yeterli urun bulunamadi."
        )

    sonuclar = []

    for sira, adres in enumerate(
        adresler[:TEST_ADEDI], 1
    ):
        print(
            f"\nUrun {sira}/{TEST_ADEDI}: {adres}",
            flush=True
        )

        try:
            kayit = urun_oku(adres)
        except Exception as hata:
            raise SystemExit(
                f"Test durduruldu: {adres} - {hata}"
            )

        sonuclar.append(kayit)

        print(
            "Ad:", kayit["urun_adi"],
            "| Marka:", kayit["marka"],
            "| Kategori:", kayit["kategori"],
            "| Kod:", kayit["stok_kodu"],
            "| Barkod:", kayit["barkod"],
            "| Fiyat:", kayit["fiyat"],
            "| KDV:", kayit["kdv"] or "?",
            "| Stok:", kayit["stok"],
            flush=True
        )

    with CIKIS.open(
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        yazici = csv.DictWriter(
            dosya,
            fieldnames=ALANLAR
        )
        yazici.writeheader()
        yazici.writerows(sonuclar)

    print("\nTEST TAMAMLANDI", flush=True)
    print("Okunan urun:", len(sonuclar))
    print(
        "Markasi bulunan:",
        sum(bool(x["marka"]) for x in sonuclar)
    )
    print(
        "Kategorisi bulunan:",
        sum(bool(x["kategori"]) for x in sonuclar)
    )
    print(
        "Stok kodu bulunan:",
        sum(bool(x["stok_kodu"]) for x in sonuclar)
    )
    print(
        "Barkodu bulunan:",
        sum(bool(x["barkod"]) for x in sonuclar)
    )
    print(
        "Fiyati bulunan:",
        sum(bool(x["fiyat"]) for x in sonuclar)
    )
    print(
        "Stogu bulunan:",
        sum(bool(x["stok"]) for x in sonuclar)
    )
    print(
        "KDV orani bulunan:",
        sum(bool(x["kdv"]) for x in sonuclar)
    )
    print("Dosya:", CIKIS, flush=True)


if __name__ == "__main__":
    calistir()

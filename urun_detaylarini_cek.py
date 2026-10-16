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
oturum.headers.update({
    "User-Agent": USER_AGENT
})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")

try:
    robots.read()
except Exception as hata:
    raise SystemExit(
        f"robots.txt okunamadi: {hata}"
    )


def temiz_metin(deger):
    if deger is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(deger)
    ).strip()


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
            duz_metin(x)
            for x in deger
            if x
        )

    return temiz_metin(deger)


def metin_bul(html, seciciler):
    for secici in seciciler:
        eleman = html.select_one(secici)

        if not eleman:
            continue

        deger = (
            eleman.get("content")
            or eleman.get("value")
            or eleman.get("data-value")
            or eleman.get_text(" ", strip=True)
        )

        deger = temiz_metin(deger)

        if deger:
            return deger

    return ""


def jsonld_verileri(html):
    sonuc = []

    for script in html.select(
        'script[type="application/ld+json"]'
    ):
        icerik = script.string or script.get_text()

        try:
            veri = json.loads(icerik)
        except (ValueError, TypeError):
            continue

        sonuc.append(veri)

    return sonuc


def jsonld_urun(html):
    def tara(nesne):
        if isinstance(nesne, list):
            for oge in nesne:
                bulunan = tara(oge)

                if bulunan:
                    return bulunan

        elif isinstance(nesne, dict):
            tip = nesne.get("@type", [])
            tipler = (
                tip
                if isinstance(tip, list)
                else [tip]
            )

            if "Product" in tipler:
                return nesne

            for deger in nesne.values():
                bulunan = tara(deger)

                if bulunan:
                    return bulunan

        return {}

    for veri in jsonld_verileri(html):
        bulunan = tara(veri)

        if bulunan:
            return bulunan

    return {}


def jsonld_breadcrumb(html):
    def tara(nesne):
        if isinstance(nesne, list):
            for oge in nesne:
                sonuc = tara(oge)

                if sonuc:
                    return sonuc

        elif isinstance(nesne, dict):
            tip = nesne.get("@type", "")
            tipler = (
                tip
                if isinstance(tip, list)
                else [tip]
            )

            if "BreadcrumbList" in tipler:
                return nesne

            for deger in nesne.values():
                sonuc = tara(deger)

                if sonuc:
                    return sonuc

        return {}

    for veri in jsonld_verileri(html):
        sonuc = tara(veri)

        if sonuc:
            return sonuc

    return {}


def etiket_degeri_bul(html, etiketler):
    """
    Marka, Barkod Kodu, Stok Kodu gibi
    ekranda etiket/deger seklinde bulunan
    bilgileri okumaya calisir.
    """

    etiketler = [
        temiz_metin(x)
        for x in etiketler
    ]

    seciciler = [
        "tr",
        "li",
        "dl",
        ".product-property",
        ".product-properties li",
        ".product-feature",
        ".product-features li",
        ".product-info-row",
        ".specification",
        ".specification-row",
        ".detail-row",
        ".product-detail-row"
    ]

    for secici in seciciler:
        for satir in html.select(secici):
            metin = temiz_metin(
                satir.get_text(" ", strip=True)
            )

            if not metin:
                continue

            for etiket in etiketler:
                desen = (
                    r"^"
                    + re.escape(etiket)
                    + r"\s*:?\s*(.+)$"
                )

                eslesme = re.match(
                    desen,
                    metin,
                    flags=re.IGNORECASE
                )

                if eslesme:
                    deger = temiz_metin(
                        eslesme.group(1)
                    )

                    if (
                        deger
                        and deger.lower()
                        != etiket.lower()
                    ):
                        return deger

    # Etiket tek basina bir elementteyse
    for etiket in etiketler:
        desen = re.compile(
            r"^\s*"
            + re.escape(etiket)
            + r"\s*:?\s*$",
            re.IGNORECASE
        )

        for metin_dugumu in html.find_all(
            string=desen
        ):
            parent = metin_dugumu.parent

            if not parent:
                continue

            # Sonraki kardes element
            kardes = parent.find_next_sibling()

            if kardes:
                deger = temiz_metin(
                    kardes.get_text(
                        " ",
                        strip=True
                    )
                )

                if deger:
                    return deger

            # Ayni satirdaki diger hucre
            satir = parent.find_parent("tr")

            if satir:
                hucreler = satir.find_all(
                    ["td", "th"]
                )

                if len(hucreler) >= 2:
                    deger = temiz_metin(
                        hucreler[-1].get_text(
                            " ",
                            strip=True
                        )
                    )

                    if (
                        deger
                        and deger.lower()
                        != etiket.lower()
                    ):
                        return deger

    return ""


def teklif_bul(veri):
    teklifler = veri.get("offers", {})

    if isinstance(teklifler, list):
        teklifler = (
            teklifler[0]
            if teklifler
            else {}
        )

    if not isinstance(teklifler, dict):
        return {}

    return teklifler


def marka_bul(html, veri, urun_adi):
    marka = duz_metin(
        veri.get("brand")
    )

    if marka:
        return marka, "JSON-LD"

    marka = etiket_degeri_bul(
        html,
        [
            "Marka",
            "Brand"
        ]
    )

    if marka:
        return marka, "URUN DETAYI"

    marka = metin_bul(
        html,
        [
            '[itemprop="brand"]',
            ".product-brand",
            ".brand-name",
            '[class*="brand-name"]'
        ]
    )

    if marka:
        return marka, "HTML"

    # Urun adindan marka tahmin ETMIYORUZ.
    return "", "BULUNAMADI"


def stok_kodu_bul(html, veri):
    stok_kodu = duz_metin(
        veri.get("sku")
    )

    if stok_kodu:
        return stok_kodu, "JSON-LD"

    stok_kodu = etiket_degeri_bul(
        html,
        [
            "Stok Kodu",
            "Ürün Kodu",
            "Urun Kodu",
            "SKU"
        ]
    )

    if stok_kodu:
        return stok_kodu, "URUN DETAYI"

    stok_kodu = metin_bul(
        html,
        [
            '[itemprop="sku"]',
            ".product-code"
        ]
    )

    if stok_kodu:
        return stok_kodu, "HTML"

    return "", "BULUNAMADI"


def barkod_bul(html, veri):
    barkod = duz_metin(
        veri.get("gtin13")
        or veri.get("gtin14")
        or veri.get("gtin12")
        or veri.get("gtin8")
        or veri.get("gtin")
        or veri.get("mpn")
    )

    if barkod:
        return barkod, "JSON-LD"

    barkod = etiket_degeri_bul(
        html,
        [
            "Barkod Kodu",
            "Barkod",
            "EAN",
            "GTIN"
        ]
    )

    if barkod:
        return barkod, "URUN DETAYI"

    barkod = metin_bul(
        html,
        [
            '[itemprop="gtin13"]',
            '[itemprop="gtin14"]',
            '[itemprop="gtin"]'
        ]
    )

    if barkod:
        return barkod, "HTML"

    return "", "BULUNAMADI"


def fiyat_bul(html, veri):
    teklif = teklif_bul(veri)

    fiyat = duz_metin(
        teklif.get("price")
    )

    fiyat_kaynagi = (
        "JSON-LD"
        if fiyat
        else ""
    )

    if not fiyat:
        fiyat = metin_bul(
            html,
            [
                'meta[itemprop="price"]',
                '[itemprop="price"]',
                ".product-price",
                ".current-price",
                ".discounted-price"
            ]
        )

        if fiyat:
            fiyat_kaynagi = "HTML"

    para_birimi = duz_metin(
        teklif.get("priceCurrency")
    )

    if not para_birimi:
        para_birimi = metin_bul(
            html,
            [
                'meta[itemprop="priceCurrency"]',
                '[itemprop="priceCurrency"]'
            ]
        )

    if not para_birimi:
        fiyat_metni = temiz_metin(
            fiyat
        )

        if re.search(
            r"\bTRY\b|₺|\bTL\b",
            fiyat_metni,
            re.I
        ):
            para_birimi = "TRY"

        elif re.search(
            r"\bUSD\b|\$",
            fiyat_metni,
            re.I
        ):
            para_birimi = "USD"

        elif re.search(
            r"\bEUR\b|€",
            fiyat_metni,
            re.I
        ):
            para_birimi = "EUR"

    kdv_haric = etiket_degeri_bul(
        html,
        [
            "KDV Hariç",
            "KDV Haric",
            "KDV Hariç Fiyat",
            "KDV Haric Fiyat"
        ]
    )

    return (
        fiyat,
        para_birimi,
        fiyat_kaynagi,
        kdv_haric
    )


def kategori_bul(html):
    breadcrumb = jsonld_breadcrumb(
        html
    )

    kategoriler = []

    if breadcrumb:
        elemanlar = breadcrumb.get(
            "itemListElement",
            []
        )

        if isinstance(elemanlar, list):
            for eleman in elemanlar:
                if not isinstance(
                    eleman,
                    dict
                ):
                    continue

                isim = duz_metin(
                    eleman.get("name")
                    or (
                        eleman.get(
                            "item",
                            {}
                        ).get("name")
                        if isinstance(
                            eleman.get("item"),
                            dict
                        )
                        else ""
                    )
                )

                if isim:
                    kategoriler.append(
                        isim
                    )

    if not kategoriler:
        for link in html.select(
            ".breadcrumb a, "
            ".breadcrumbs a, "
            '[class*="breadcrumb"] a'
        ):
            isim = temiz_metin(
                link.get_text(
                    " ",
                    strip=True
                )
            )

            if isim:
                kategoriler.append(
                    isim
                )

    temiz = []

    for isim in kategoriler:
        if isim.lower() in {
            "anasayfa",
            "ana sayfa",
            "home"
        }:
            continue

        if isim not in temiz:
            temiz.append(isim)

    if not temiz:
        return ""

    return " > ".join(temiz)


def stok_bul(html):
    stok_alani = html.select_one(
        "#qty-input[data-stockamount], "
        "[data-stockamount]"
    )

    if stok_alani:
        return temiz_metin(
            stok_alani.get(
                "data-stockamount",
                ""
            )
        )

    return ""


def gorsel_bul(html, veri, adres):
    gorsel = metin_bul(
        html,
        [
            'meta[property="og:image"]'
        ]
    )

    if not gorsel:
        resim = veri.get(
            "image",
            ""
        )

        if isinstance(resim, list):
            resim = (
                resim[0]
                if resim
                else ""
            )

        if isinstance(resim, dict):
            resim = (
                resim.get("url")
                or resim.get("contentUrl")
                or ""
            )

        gorsel = temiz_metin(
            resim
        )

    if gorsel:
        gorsel = urljoin(
            adres,
            gorsel
        )

    return gorsel


def aciklama_bul(html, veri):
    aciklama = duz_metin(
        veri.get("description")
    )

    if aciklama:
        return aciklama

    return metin_bul(
        html,
        [
            '[itemprop="description"]',
            ".product-description",
            "#product-description",
            ".product-detail-description"
        ]
    )


def urun_oku(adres):
    parca = urlparse(adres)

    if (
        parca.scheme != "https"
        or parca.netloc
        != "www.hirdavatagaci.com"
        or not parca.path.startswith(
            "/urun/"
        )
    ):
        raise ValueError(
            "Gecersiz urun adresi"
        )

    if not robots.can_fetch(
        USER_AGENT,
        adres
    ):
        raise RuntimeError(
            "robots.txt erisime izin vermiyor"
        )

    time.sleep(BEKLEME)

    cevap = oturum.get(
        adres,
        timeout=30
    )

    cevap.raise_for_status()

    html = BeautifulSoup(
        cevap.text,
        "html.parser"
    )

    veri = jsonld_urun(html)

    urun_adi = (
        duz_metin(
            veri.get("name")
        )
        or metin_bul(
            html,
            [
                "h1",
                '[itemprop="name"]'
            ]
        )
    )

    if not urun_adi:
        raise ValueError(
            "Urun adi okunamadi"
        )

    marka, marka_kaynagi = (
        marka_bul(
            html,
            veri,
            urun_adi
        )
    )

    stok_kodu, stok_kodu_kaynagi = (
        stok_kodu_bul(
            html,
            veri
        )
    )

    barkod, barkod_kaynagi = (
        barkod_bul(
            html,
            veri
        )
    )

    (
        fiyat,
        para_birimi,
        fiyat_kaynagi,
        kdv_haric_fiyat
    ) = fiyat_bul(
        html,
        veri
    )

    kategori = kategori_bul(
        html
    )

    stok = stok_bul(
        html
    )

    aciklama = aciklama_bul(
        html,
        veri
    )

    gorsel = gorsel_bul(
        html,
        veri,
        adres
    )

    return {
        "url": adres,
        "urun_adi": urun_adi,

        "marka": marka,
        "marka_kaynagi": marka_kaynagi,

        "stok_kodu": stok_kodu,
        "stok_kodu_kaynagi":
            stok_kodu_kaynagi,

        "barkod": barkod,
        "barkod_kaynagi":
            barkod_kaynagi,

        "kategori": kategori,

        "satis_fiyati": fiyat,
        "para_birimi":
            para_birimi,
        "fiyat_kaynagi":
            fiyat_kaynagi,

        "kdv_haric_fiyat":
            kdv_haric_fiyat,

        "kdv_durumu":
            "DOGRULANMADI",

        "stok": stok,

        "aciklama":
            aciklama,

        "gorsel":
            gorsel
    }


def calistir():
    if not GIRIS.exists():
        raise SystemExit(
            "urun_baglantilari.csv "
            "bulunamadi. "
            "Once urunleri_cek.py "
            "calismali."
        )

    with GIRIS.open(
        encoding="utf-8-sig",
        newline=""
    ) as dosya:

        adresler = [
            satir["url"].strip()
            for satir
            in csv.DictReader(
                dosya
            )
            if satir.get(
                "url",
                ""
            ).strip()
        ]

    if len(adresler) < TEST_ADEDI:
        raise SystemExit(
            "Test icin yeterli "
            "urun bulunamadi."
        )

    sonuclar = []

    for sira, adres in enumerate(
        adresler[:TEST_ADEDI],
        1
    ):

        print(
            f"\nUrun "
            f"{sira}/"
            f"{TEST_ADEDI}: "
            f"{adres}",
            flush=True
        )

        try:
            kayit = urun_oku(
                adres
            )

            sonuclar.append(
                kayit
            )

            print(
                "Ad:",
                kayit["urun_adi"],
                "| Marka:",
                kayit["marka"]
                or "BOS",
                "| Kod:",
                kayit["stok_kodu"]
                or "BOS",
                "| Barkod:",
                kayit["barkod"]
                or "BOS",
                "| Fiyat:",
                kayit["satis_fiyati"]
                or "BOS",
                "| Para:",
                kayit["para_birimi"]
                or "BOS",
                "| Stok:",
                kayit["stok"]
                or "BOS",
                flush=True
            )

        except Exception as hata:
            raise SystemExit(
                f"Test durduruldu: "
                f"{adres} - {hata}"
            )

    alanlar = [
        "url",
        "urun_adi",

        "marka",
        "marka_kaynagi",

        "stok_kodu",
        "stok_kodu_kaynagi",

        "barkod",
        "barkod_kaynagi",

        "kategori",

        "satis_fiyati",
        "para_birimi",
        "fiyat_kaynagi",

        "kdv_haric_fiyat",
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
            dosya,
            fieldnames=alanlar
        )

        yazici.writeheader()
        yazici.writerows(
            sonuclar
        )

    print(
        "\nTEST TAMAMLANDI",
        flush=True
    )

    print(
        "Okunan urun:",
        len(sonuclar)
    )

    print(
        "Markasi bulunan:",
        sum(
            bool(x["marka"])
            for x in sonuclar
        )
    )

    print(
        "Stok kodu bulunan:",
        sum(
            bool(x["stok_kodu"])
            for x in sonuclar
        )
    )

    print(
        "Barkodu bulunan:",
        sum(
            bool(x["barkod"])
            for x in sonuclar
        )
    )

    print(
        "Kategorisi bulunan:",
        sum(
            bool(x["kategori"])
            for x in sonuclar
        )
    )

    print(
        "Fiyati bulunan:",
        sum(
            bool(x["satis_fiyati"])
            for x in sonuclar
        )
    )

    print(
        "Stogu bulunan:",
        sum(
            bool(x["stok"])
            for x in sonuclar
        )
    )

    print(
        "Dosya:",
        CIKIS
    )


if __name__ == "__main__":
    calistir()

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


def sayfa_metinleri(html):
    return [
        temiz_metin(x)
        for x in html.stripped_strings
        if temiz_metin(x)
    ]


def etiket_sonrasi(html, etiket):
    """
    Sayfada ilk kez tam olarak eslesen etiketi bulur
    ve hemen sonraki metni alir.

    Ornek:
    Marka
    AEG

    veya:
    Barkod Kodu
    4058546289652
    """

    metinler = sayfa_metinleri(html)
    hedef = temiz_metin(etiket).lower()

    for i, metin in enumerate(metinler):
        if metin.lower() == hedef:
            if i + 1 < len(metinler):
                return metinler[i + 1]

    return ""


def jsonld_verileri(html):
    sonuclar = []

    for script in html.select(
        'script[type="application/ld+json"]'
    ):
        try:
            veri = json.loads(
                script.string
                or script.get_text()
            )

            sonuclar.append(veri)

        except (ValueError, TypeError):
            continue

    return sonuclar


def jsonld_urun(html):
    def tara(nesne):
        if isinstance(nesne, list):
            for oge in nesne:
                sonuc = tara(oge)

                if sonuc:
                    return sonuc

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
                sonuc = tara(deger)

                if sonuc:
                    return sonuc

        return {}

    for veri in jsonld_verileri(html):
        sonuc = tara(veri)

        if sonuc:
            return sonuc

    return {}


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


def marka_duzelt(marka):
    marka = temiz_metin(marka)

    if not marka:
        return ""

    normal = marka.upper()

    eslesmeler = {
        "AEG POWERTOOLS": "AEG",
        "AEG POWER TOOLS": "AEG",
        "AEG POWERTOOL": "AEG"
    }

    if normal in eslesmeler:
        return eslesmeler[normal]

    return marka


def marka_bul(html, veri):
    # ONCELIK:
    # Sitede urun bilgisinin yaninda gorunen Marka alani.
    marka = etiket_sonrasi(
        html,
        "Marka"
    )

    if marka:
        # Yanlislikla urun adi geldiyse kullanma.
        urun_adi = (
            duz_metin(veri.get("name"))
            or metin_bul(html, ["h1"])
        )

        if (
            urun_adi
            and marka.lower()
            == urun_adi.lower()
        ):
            marka = ""
        else:
            return (
                marka_duzelt(marka),
                "GORUNEN_MARKA"
            )

    marka = duz_metin(
        veri.get("brand")
    )

    if marka:
        return (
            marka_duzelt(marka),
            "JSON-LD"
        )

    marka = metin_bul(
        html,
        [
            '[itemprop="brand"]',
            ".product-brand",
            ".brand-name"
        ]
    )

    if marka:
        return (
            marka_duzelt(marka),
            "HTML"
        )

    return "", "BULUNAMADI"


def kategori_bul(html):
    # Sitede urun bilgisindeki Kategori alani.
    kategori = etiket_sonrasi(
        html,
        "Kategori"
    )

    if kategori:
        return kategori, "GORUNEN_KATEGORI"

    # Breadcrumb yedegi
    adaylar = []

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

        href = link.get(
            "href",
            ""
        )

        if (
            isim
            and "/kategori/" in href
        ):
            adaylar.append(isim)

    if adaylar:
        return (
            adaylar[-1],
            "BREADCRUMB"
        )

    return "", "BULUNAMADI"


def stok_kodu_bul(html, veri):
    # Sitedeki gorunen degeri tercih ediyoruz.
    stok_kodu = etiket_sonrasi(
        html,
        "Stok Kodu"
    )

    if stok_kodu:
        return (
            stok_kodu,
            "GORUNEN_STOK_KODU"
        )

    stok_kodu = duz_metin(
        veri.get("sku")
    )

    if stok_kodu:
        return (
            stok_kodu,
            "JSON-LD"
        )

    return "", "BULUNAMADI"


def barkod_bul(html, veri):
    barkod = etiket_sonrasi(
        html,
        "Barkod Kodu"
    )

    if barkod:
        return (
            barkod,
            "GORUNEN_BARKOD"
        )

    barkod = duz_metin(
        veri.get("gtin13")
        or veri.get("gtin14")
        or veri.get("gtin12")
        or veri.get("gtin8")
        or veri.get("gtin")
    )

    if barkod:
        return (
            barkod,
            "JSON-LD"
        )

    return "", "BULUNAMADI"


def fiyat_sayiya_cevir(deger):
    if deger is None:
        return None

    deger = temiz_metin(deger)

    if not deger:
        return None

    temiz = re.sub(
        r"[^\d,.\-]",
        "",
        deger
    )

    if not temiz:
        return None

    try:
        if "," in temiz and "." in temiz:
            # Turk formati:
            # 12.203,33
            if temiz.rfind(",") > temiz.rfind("."):
                temiz = temiz.replace(".", "")
                temiz = temiz.replace(",", ".")

        elif "," in temiz:
            temiz = temiz.replace(",", ".")

        return float(temiz)

    except ValueError:
        return None


def fiyat_bul(html, veri):
    teklifler = teklif_bul(veri)

    satis_fiyati = duz_metin(
        teklifler.get("price")
    )

    fiyat_kaynagi = (
        "JSON-LD"
        if satis_fiyati
        else ""
    )

    if not satis_fiyati:
        satis_fiyati = metin_bul(
            html,
            [
                'meta[itemprop="price"]',
                '[itemprop="price"]',
                ".current-price",
                ".product-price"
            ]
        )

        if satis_fiyati:
            fiyat_kaynagi = "HTML"

    para_birimi = duz_metin(
        teklifler.get(
            "priceCurrency"
        )
    )

    # Sitenin gorunen "Fiyat" alani:
    # 12.203,33 TL + KDV
    kdv_haric_ham = etiket_sonrasi(
        html,
        "Fiyat"
    )

    kdv_haric_sayi = fiyat_sayiya_cevir(
        kdv_haric_ham
    )

    satis_sayi = fiyat_sayiya_cevir(
        satis_fiyati
    )

    kdv_orani = ""
    kdv_durumu = "DOGRULANMADI"

    if (
        satis_sayi is not None
        and kdv_haric_sayi is not None
        and kdv_haric_sayi > 0
    ):
        oran = (
            satis_sayi
            / kdv_haric_sayi
            - 1
        ) * 100

        if 19 <= oran <= 21:
            kdv_orani = "20"
            kdv_durumu = (
                "SATIS_FIYATI_KDV_DAHIL"
            )

        elif 9 <= oran <= 11:
            kdv_orani = "10"
            kdv_durumu = (
                "SATIS_FIYATI_KDV_DAHIL"
            )

        elif -1 <= oran <= 1:
            kdv_orani = "0"
            kdv_durumu = (
                "FIYATLAR_ESIT"
            )

    if not para_birimi:
        birlesik = (
            str(satis_fiyati)
            + " "
            + str(kdv_haric_ham)
        )

        if re.search(
            r"\bTRY\b|₺|\bTL\b",
            birlesik,
            re.I
        ):
            para_birimi = "TRY"

        elif re.search(
            r"\bUSD\b|\$",
            birlesik,
            re.I
        ):
            para_birimi = "USD"

        elif re.search(
            r"\bEUR\b|€",
            birlesik,
            re.I
        ):
            para_birimi = "EUR"

    return (
        satis_fiyati,
        para_birimi,
        fiyat_kaynagi,
        kdv_haric_ham,
        kdv_orani,
        kdv_durumu
    )


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
        return urljoin(
            adres,
            gorsel
        )

    return ""


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
            veri
        )
    )

    kategori, kategori_kaynagi = (
        kategori_bul(
            html
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
        satis_fiyati,
        para_birimi,
        fiyat_kaynagi,
        kdv_haric_fiyat,
        kdv_orani,
        kdv_durumu
    ) = fiyat_bul(
        html,
        veri
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
        "marka_kaynagi":
            marka_kaynagi,

        "kategori": kategori,
        "kategori_kaynagi":
            kategori_kaynagi,

        "stok_kodu": stok_kodu,
        "stok_kodu_kaynagi":
            stok_kodu_kaynagi,

        "barkod": barkod,
        "barkod_kaynagi":
            barkod_kaynagi,

        "satis_fiyati":
            satis_fiyati,

        "para_birimi":
            para_birimi,

        "fiyat_kaynagi":
            fiyat_kaynagi,

        "kdv_haric_fiyat":
            kdv_haric_fiyat,

        "kdv_orani":
            kdv_orani,

        "kdv_durumu":
            kdv_durumu,

        "stok": stok,

        "aciklama": aciklama,

        "gorsel": gorsel
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
            for satir in csv.DictReader(
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
            "| Kategori:",
            kayit["kategori"]
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
            "| KDV:",
            kayit["kdv_orani"]
            or "?",
            "| Stok:",
            kayit["stok"]
            or "BOS",
            flush=True
        )

    alanlar = [
        "url",
        "urun_adi",

        "marka",
        "marka_kaynagi",

        "kategori",
        "kategori_kaynagi",

        "stok_kodu",
        "stok_kodu_kaynagi",

        "barkod",
        "barkod_kaynagi",

        "satis_fiyati",
        "para_birimi",
        "fiyat_kaynagi",

        "kdv_haric_fiyat",
        "kdv_orani",
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
        "\nTEST TAMAMLANDI"
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
        "Kategorisi bulunan:",
        sum(
            bool(x["kategori"])
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
        "Fiyati bulunan:",
        sum(
            bool(x["satis_fiyati"])
            for x in sonuclar
        )
    )

    print(
        "KDV orani bulunan:",
        sum(
            bool(x["kdv_orani"])
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

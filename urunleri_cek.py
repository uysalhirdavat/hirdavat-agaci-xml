
import csv
import re
import time
from collections import deque, defaultdict
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
BASLANGIC = SITE + "/kategoriler"

BEKLEME = 3
MAKSIMUM_SAYFA = 500
USER_AGENT = "UysalHirdavatXML/1.0"

oturum = requests.Session()
oturum.headers.update({"User-Agent": USER_AGENT})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")

try:
    robots.read()
except Exception as hata:
    raise SystemExit(f"robots.txt okunamadi: {hata}")


def temizle(adres):
    parca = urlparse(adres)

    if (
        parca.scheme != "https"
        or parca.netloc != "www.hirdavatagaci.com"
    ):
        return None

    yol = parca.path.rstrip("/") or "/"

    if yol.startswith("/kategori/"):
        sayfa = parse_qs(parca.query).get("tp", ["1"])[0]

        if not sayfa.isdigit() or int(sayfa) < 1:
            return None

        sorgu = f"tp={int(sayfa)}" if int(sayfa) > 1 else ""
    else:
        sorgu = ""

    return urlunparse((
        "https",
        "www.hirdavatagaci.com",
        yol,
        "",
        sorgu,
        ""
    ))


def sayfa_al(adres):
    if not robots.can_fetch(USER_AGENT, adres):
        raise RuntimeError(f"Erisim izni yok: {adres}")

    time.sleep(BEKLEME)

    cevap = oturum.get(adres, timeout=30)
    cevap.raise_for_status()

    return BeautifulSoup(cevap.text, "html.parser")


def kategori_toplami(html):
    metin = html.get_text(" ", strip=True)

    eslesme = re.search(
        r"Toplam\s+([\d.,]+)\s+ürün",
        metin,
        flags=re.IGNORECASE
    )

    if eslesme:
        return int(re.sub(r"\D", "", eslesme.group(1)))

    return None


def csv_yaz(dosya, basliklar, satirlar):
    with open(
        dosya,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as f:
        yazici = csv.writer(f)
        yazici.writerow(basliklar)
        yazici.writerows(satirlar)


def calistir():
    kuyruk = deque([BASLANGIC])
    planlanan = {BASLANGIC}
    ziyaret = set()

    urunler = set()
    kategori_urunleri = defaultdict(set)
    kategori_sayilari = {}

    while kuyruk:
        if len(ziyaret) >= MAKSIMUM_SAYFA:
            raise SystemExit(
                "Sayfa sinirina ulasildi. "
                "Eksik sonuc yayinlanmadi."
            )

        adres = kuyruk.popleft()

        if adres in ziyaret:
            continue

        print("Kontrol:", adres, flush=True)

        try:
            html = sayfa_al(adres)
        except Exception as hata:
            raise SystemExit(
                f"Tarama durduruldu: {adres} - {hata}"
            )

        ziyaret.add(adres)

        parca = urlparse(adres)
        kategori = SITE + parca.path

        if parca.path.startswith("/kategori/"):
            toplam = kategori_toplami(html)

            if toplam is not None:
                if (
                    kategori in kategori_sayilari
                    and kategori_sayilari[kategori] != toplam
                ):
                    raise SystemExit(
                        f"Kategori sayisi degisti: {kategori}"
                    )

                kategori_sayilari[kategori] = toplam

        for etiket in html.select("a[href]"):
            baglanti = temizle(
                urljoin(adres, etiket["href"])
            )

            if not baglanti:
                continue

            yol = urlparse(baglanti).path

            if yol.startswith("/urun/"):
                urunler.add(baglanti)

                if parca.path.startswith("/kategori/"):
                    kategori_urunleri[kategori].add(baglanti)

            elif (
                yol.startswith("/kategori/")
                or yol == "/kategoriler"
            ):
                if baglanti not in planlanan:
                    planlanan.add(baglanti)
                    kuyruk.append(baglanti)

        print(
            "Sayfa:", len(ziyaret),
            "Bekleyen:", len(kuyruk),
            "Urun:", len(urunler),
            flush=True
        )

    if not urunler:
        raise SystemExit("Hic urun bulunamadi.")

    rapor = []
    farkli_kategoriler = []
    okunamayan = []

    tum_kategoriler = (
        kategori_urunleri.keys() | kategori_sayilari.keys()
    )

    for kategori in sorted(tum_kategoriler):
        beklenen = kategori_sayilari.get(kategori)
        bulunan = len(kategori_urunleri[kategori])

        if beklenen is None:
            durum = "SAYI BULUNAMADI"
            fark = ""
            okunamayan.append(kategori)
        elif bulunan == beklenen:
            durum = "ESLESIYOR"
            fark = 0
        else:
            durum = "FARK VAR"
            fark = beklenen - bulunan
            farkli_kategoriler.append(kategori)

        rapor.append([
            kategori,
            beklenen if beklenen is not None else "",
            bulunan,
            fark,
            durum
        ])

    if farkli_kategoriler or okunamayan:
        print("Kategori kontrolu tamamlanamadi.")
        print("Farkli:", len(farkli_kategoriler))
        print("Okunamayan:", len(okunamayan))
        raise SystemExit(
            "Eksik veya dogrulanamayan kategori var. "
            "Urun listesi yayinlanmadi."
        )

    csv_yaz(
        "urun_baglantilari.csv",
        ["url"],
        [[url] for url in sorted(urunler)]
    )

    csv_yaz(
        "kategori_raporu.csv",
        [
            "kategori",
            "sitedeki_toplam",
            "bulunan_benzersiz",
            "fark",
            "durum"
        ],
        rapor
    )

    print("\nTARAMA TAMAMLANDI")
    print("Toplam sayfa:", len(ziyaret))
    print("Benzersiz urun:", len(urunler))
    print("Kategori:", len(rapor))
    print("Farkli kategori:", len(farkli_kategoriler))
    print("Dosyalar:")
    print("- urun_baglantilari.csv")
    print("- kategori_raporu.csv")


if __name__ == "__main__":
    calistir()

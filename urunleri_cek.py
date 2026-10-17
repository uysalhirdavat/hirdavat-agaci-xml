
import csv
import time
from collections import deque
from urllib.parse import (
    urljoin,
    urlparse,
    urlunparse,
    parse_qs,
)
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
BASLANGIC = SITE + "/kategoriler"

CIKTI = "urun_baglantilari.csv"
RAPOR = "kategori_raporu.csv"

BEKLEME = 3
MAKSIMUM_SAYFA = 500
USER_AGENT = "UysalHirdavatXML/1.0"

oturum = requests.Session()
oturum.headers.update({
    "User-Agent": USER_AGENT
})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")

try:
    cevap = oturum.get(
        SITE + "/robots.txt",
        timeout=30
    )
    cevap.raise_for_status()
    robots.parse(cevap.text.splitlines())
except requests.RequestException as hata:
    raise SystemExit(
        f"robots.txt okunamadi: {hata}"
    )


def temizle(adres):
    parca = urlparse(adres)

    if (
        parca.scheme != "https"
        or parca.netloc != "www.hirdavatagaci.com"
    ):
        return None

    yol = parca.path.rstrip("/") or "/"

    if yol.startswith("/kategori/"):
        parametreler = parse_qs(parca.query)
        sayfa = parametreler.get("tp", ["1"])[0]

        if not sayfa.isdigit():
            return None

        sayfa_no = int(sayfa)

        if sayfa_no < 1:
            return None

        sorgu = (
            f"tp={sayfa_no}"
            if sayfa_no > 1
            else ""
        )

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
        raise RuntimeError(
            f"Erisim izni yok: {adres}"
        )

    time.sleep(BEKLEME)

    cevap = oturum.get(
        adres,
        timeout=30
    )
    cevap.raise_for_status()

    return BeautifulSoup(
        cevap.text,
        "html.parser"
    )


def calistir():
    kuyruk = deque([BASLANGIC])
    planlanan = {BASLANGIC}
    ziyaret = set()
    urunler = set()
    kategoriler = set()
    rapor = []

    while kuyruk:
        if len(ziyaret) >= MAKSIMUM_SAYFA:
            raise SystemExit(
                f"Sayfa sinirina ulasildi: "
                f"{MAKSIMUM_SAYFA}. "
                "Tarama eksik. CSV yayinlanmadi."
            )

        adres = kuyruk.popleft()

        if adres in ziyaret:
            continue

        print(
            "Kontrol:",
            adres,
            flush=True
        )

        try:
            html = sayfa_al(adres)
        except Exception as hata:
            raise SystemExit(
                f"Tarama durduruldu: "
                f"{adres} - {hata}"
            )

        ziyaret.add(adres)

        sayfa_urunleri = set()

        for etiket in html.select("a[href]"):
            baglanti = temizle(
                urljoin(
                    adres,
                    etiket["href"]
                )
            )

            if not baglanti:
                continue

            yol = urlparse(baglanti).path

            if yol.startswith("/urun/"):
                sayfa_urunleri.add(baglanti)
                urunler.add(baglanti)

            elif (
                yol.startswith("/kategori/")
                or yol == "/kategoriler"
            ):
                if yol.startswith("/kategori/"):
                    kategoriler.add(
                        urlunparse((
                            "https",
                            "www.hirdavatagaci.com",
                            yol,
                            "",
                            "",
                            ""
                        ))
                    )

                if baglanti not in planlanan:
                    planlanan.add(baglanti)
                    kuyruk.append(baglanti)

        rapor.append({
            "sayfa": adres,
            "sayfadaki_urun": len(
                sayfa_urunleri
            )
        })

        print(
            "Sayfa:", len(ziyaret),
            "Bekleyen:", len(kuyruk),
            "Urun:", len(urunler),
            flush=True
        )

    if not urunler:
        raise SystemExit(
            "Hic urun bulunamadi."
        )

    with open(
        CIKTI,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(["url"])

        for adres in sorted(urunler):
            yazici.writerow([adres])

    with open(
        RAPOR,
        "w",
        encoding="utf-8-sig",
        newline=""
    ) as dosya:
        yazici = csv.DictWriter(
            dosya,
            fieldnames=[
                "sayfa",
                "sayfadaki_urun"
            ]
        )
        yazici.writeheader()
        yazici.writerows(rapor)

    print("\nTARAMA TAMAMLANDI")
    print(
        "Toplam sayfa:",
        len(ziyaret)
    )
    print(
        "Benzersiz urun:",
        len(urunler)
    )
    print(
        "Kategori:",
        len(kategoriler)
    )
    print(
        "Dosyalar:"
    )
    print("-", CIKTI)
    print("-", RAPOR)


if __name__ == "__main__":
    calistir()

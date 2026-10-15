
import csv
import time
from collections import deque
from urllib.parse import urljoin, urlparse, urlunparse, parse_qs
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
BASLANGIC = SITE + "/kategoriler"
CIKTI = "urun_baglantilari.csv"

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

        if not sayfa.isdigit():
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

def calistir():
    kuyruk = deque([BASLANGIC])
    planlanan = {BASLANGIC}
    ziyaret = set()
    urunler = set()

    while kuyruk:
        if len(ziyaret) >= MAKSIMUM_SAYFA:
            raise SystemExit(
                f"Sayfa sinirina ulasildi: {MAKSIMUM_SAYFA}. "
                "Tarama eksik, CSV yayinlanmadi."
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

        for etiket in html.select("a[href]"):
            baglanti = temizle(
                urljoin(adres, etiket["href"])
            )

            if not baglanti:
                continue

            yol = urlparse(baglanti).path

            if yol.startswith("/urun/"):
                urunler.add(baglanti)

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

    with open(CIKTI, "w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(["url"])

        for adres in sorted(urunler):
            yazici.writerow([adres])

    print("Tarama tamamlandi.")
    print("Toplam sayfa:", len(ziyaret))
    print("Toplam urun:", len(urunler))
    print("Dosya:", CIKTI)

if __name__ == "__main__":
    calistir()

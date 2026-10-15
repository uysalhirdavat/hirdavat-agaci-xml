
import csv
import time
from collections import deque
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

SITE = "https://www.hirdavatagaci.com"
BASLANGIC = SITE + "/kategoriler"
CIKTI = "urun_baglantilari.csv"

BEKLEME = 3
MAKSIMUM_SAYFA = 100
USER_AGENT = "UysalHirdavatXML/1.0"

oturum = requests.Session()
oturum.headers.update({"User-Agent": USER_AGENT})

robots = RobotFileParser()
robots.set_url(SITE + "/robots.txt")

try:
    robots.read()
except Exception:
    raise SystemExit("robots.txt kontrol edilemedi.")

def sayfa_al(adres):
    if not robots.can_fetch(USER_AGENT, adres):
        print("Erisime izin verilmiyor:", adres)
        return None

    time.sleep(BEKLEME)

    try:
        cevap = oturum.get(adres, timeout=20)
        cevap.raise_for_status()
        return BeautifulSoup(cevap.text, "html.parser")
    except requests.RequestException as hata:
        print("Sayfa hatasi:", adres, hata)
        return None

def uygun_baglanti(adres):
    parca = urlparse(adres)
    return (
        parca.scheme == "https"
        and parca.netloc == "www.hirdavatagaci.com"
    )

def calistir():
    kuyruk = deque([BASLANGIC])
    ziyaret = set()
    urunler = set()
    hata_sayisi = 0

    while kuyruk and len(ziyaret) < MAKSIMUM_SAYFA:
        adres = kuyruk.popleft()

        if adres in ziyaret:
            continue

        ziyaret.add(adres)
        print("Kontrol:", adres)

        html = sayfa_al(adres)

        if html is None:
            hata_sayisi += 1
            continue

        for etiket in html.select("a[href]"):
            baglanti = urljoin(adres, etiket["href"])
            parca = urlparse(baglanti)

            if not uygun_baglanti(baglanti):
                continue

            temiz = baglanti.split("#")[0]

            if parca.path.startswith("/urun/"):
                urunler.add(temiz)

            elif (
                parca.path.startswith("/kategori/")
                or parca.path == "/kategoriler"
            ):
                if temiz not in ziyaret:
                    kuyruk.append(temiz)

    if hata_sayisi or kuyruk:
        raise SystemExit(
            "Tarama eksik. Sonuclar yayinlanmadi."
        )

    if not urunler:
        raise SystemExit("Hic urun bulunamadi.")

    with open(CIKTI, "w", encoding="utf-8-sig", newline="") as dosya:
        yazici = csv.writer(dosya)
        yazici.writerow(["url"])

        for adres in sorted(urunler):
            yazici.writerow([adres])

    print("Bulunan urun:", len(urunler))
    print("Dosya:", CIKTI)

if __name__ == "__main__":
    calistir()

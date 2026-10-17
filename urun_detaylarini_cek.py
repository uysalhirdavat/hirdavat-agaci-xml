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


import re
import html
import hashlib
import datetime as dt
import xml.etree.ElementTree as ET

from email.utils import format_datetime
from urllib.parse import urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


# ============================================================
# CONFIGURACIÓN
# ============================================================

BASE_URL = "https://www.elconfidencial.com"
SECTION_URL = "https://www.elconfidencial.com/empresas/"
OUTPUT_FILE = "feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


# ============================================================
# UTILIDADES
# ============================================================

def clean_text(value):
    if not value:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_url(url):
    if not url:
        return ""

    parts = urlsplit(url)

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            "",
            "",
        )
    )


def download(url):
    print(f"Descargando: {url}")

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=45,
    )

    response.raise_for_status()

    return response.text


# ============================================================
# VALIDAR ARTÍCULOS
# ============================================================

def valid_article_url(url):
    if not url:
        return False

    url = clean_url(url)

    if not url.startswith(BASE_URL):
        return False

    if url.rstrip("/") == SECTION_URL.rstrip("/"):
        return False

    # Excluir recursos
    extensions = (
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
        ".svg",
        ".css",
        ".js",
        ".xml",
    )

    if url.lower().endswith(extensions):
        return False

    return True


# ============================================================
# FECHA
# ============================================================

def parse_date(value):
    if not value:
        return None

    value = clean_text(value)

    try:
        value = value.replace(
            "Z",
            "+00:00"
        )

        result = dt.datetime.fromisoformat(value)

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=dt.timezone.utc
            )

        return result

    except Exception:
        pass

    match = re.search(
        r"(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})"
        r"(?:\s+(\d{1,2}):(\d{2}))?",
        value,
    )

    if match:
        try:
            return dt.datetime(
                int(match.group(3)),
                int(match.group(2)),
                int(match.group(1)),
                int(match.group(4) or 0),
                int(match.group(5) or 0),
                tzinfo=dt.timezone.utc,
            )

        except Exception:
            pass

    return None


def extract_date(soup):
    candidates = [
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"property": "og:published_time"},
        {"name": "date"},
        {"name": "pubdate"},
    ]

    for attrs in candidates:
        tag = soup.find(
            "meta",
            attrs=attrs
        )

        if tag and tag.get("content"):
            result = parse_date(
                tag["content"]
            )

            if result:
                return result

    for tag in soup.find_all("time"):
        value = (
            tag.get("datetime")
            or tag.get_text(" ", strip=True)
        )

        result = parse_date(value)

        if result:
            return result

    # JSON-LD
    for script in soup.find_all(
        "script",
        type="application/ld+json"
    ):
        text = script.string

        if not text:
            continue

        match = re.search(
            r'"datePublished"\s*:\s*"([^"]+)"',
            text
        )

        if match:
            result = parse_date(
                match.group(1)
            )

            if result:
                return result

    return None


# ============================================================
# TITULAR
# ============================================================

def extract_title(soup, fallback=""):
    h1 = soup.find("h1")

    if h1:
        title = clean_text(
            h1.get_text(" ", strip=True)
        )

        if title:
            return title

    tag = soup.find(
        "meta",
        attrs={
            "property": "og:title"
        }
    )

    if tag and tag.get("content"):
        title = clean_text(
            tag["content"]
        )

        if title:
            return title

    return clean_text(fallback)


# ============================================================
# DESCRIPCIÓN
# ============================================================

def extract_description(soup):
    for attrs in [
        {"name": "description"},
        {"property": "og:description"},
    ]:
        tag = soup.find(
            "meta",
            attrs=attrs
        )

        if tag and tag.get("content"):
            return clean_text(
                tag["content"]
            )

    return ""


# ============================================================
# OBTENER ARTÍCULOS DE LA SECCIÓN
# ============================================================

def get_article_links():
    source = download(
        SECTION_URL
    )

    soup = BeautifulSoup(
        source,
        "lxml"
    )

    links = {}

    # Buscamos enlaces con texto suficientemente largo.
    # El Confidencial coloca los titulares como enlaces
    # dentro de la página de Empresas.
    for a in soup.find_all(
        "a",
        href=True
    ):
        title = clean_text(
            a.get_text(
                " ",
                strip=True
            )
        )

        # Evitar menús, botones, etc.
        if len(title) < 25:
            continue

        url = urljoin(
            BASE_URL,
            a["href"]
        )

        url = clean_url(url)

        if not valid_article_url(url):
            continue

        # Evitamos secciones generales.
        bad_paths = [
            "/empresas/",
            "/mercados/",
            "/economia/",
            "/vivienda/",
            "/cotizaciones/",
            "/juridico/",
        ]

        if any(
            url.rstrip("/") ==
            (BASE_URL + path).rstrip("/")
            for path in bad_paths
        ):
            continue

        if url not in links:
            links[url] = title

        elif len(title) > len(links[url]):
            links[url] = title

    print(
        f"Enlaces encontrados: {len(links)}"
    )

    return links


# ============================================================
# LEER ARTÍCULO
# ============================================================

def get_article(
    url,
    fallback_title
):
    try:
        source = download(url)

    except Exception as exc:
        print(
            f"ERROR artículo {url}: {exc}"
        )
        return None

    soup = BeautifulSoup(
        source,
        "lxml"
    )

    title = extract_title(
        soup,
        fallback_title
    )

    if not title:
        return None

    published = extract_date(soup)

    description = extract_description(
        soup
    )

    return {
        "title": title,
        "url": url,
        "date": published,
        "description": description,
    }


# ============================================================
# RECOPILAR
# ============================================================

def collect_articles():
    links = get_article_links()

    articles = []
    seen = set()

    for url, fallback_title in links.items():

        article = get_article(
            url,
            fallback_title
        )

        if not article:
            continue

        guid = hashlib.sha256(
            url.encode("utf-8")
        ).hexdigest()

        if guid in seen:
            continue

        seen.add(guid)

        article["guid"] = guid

        articles.append(article)

    articles.sort(
        key=lambda x: (
            x["date"]
            or dt.datetime(
                1970,
                1,
                1,
                tzinfo=dt.timezone.utc
            )
        ),
        reverse=True,
    )

    return articles


# ============================================================
# GENERAR RSS
# ============================================================

def create_rss(articles):

    rss = ET.Element(
        "rss",
        {
            "version": "2.0"
        }
    )

    channel = ET.SubElement(
        rss,
        "channel"
    )

    ET.SubElement(
        channel,
        "title"
    ).text = "El Confidencial - Empresas"

    ET.SubElement(
        channel,
        "link"
    ).text = SECTION_URL

    ET.SubElement(
        channel,
        "description"
    ).text = (
        "Noticias de la sección Empresas "
        "de El Confidencial"
    )

    ET.SubElement(
        channel,
        "language"
    ).text = "es"

    ET.SubElement(
        channel,
        "lastBuildDate"
    ).text = format_datetime(
        dt.datetime.now(
            dt.timezone.utc
        )
    )

    for article in articles:

        item = ET.SubElement(
            channel,
            "item"
        )

        # =========================================
        # SOLO EL TITULAR
        # =========================================

        ET.SubElement(
            item,
            "title"
        ).text = article["title"]

        ET.SubElement(
            item,
            "link"
        ).text = article["url"]

        guid = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false"
            }
        )

        guid.text = article["guid"]

        # Fecha interna para Feedly
        if article["date"]:

            date_value = article["date"]

            if date_value.tzinfo is None:
                date_value = (
                    date_value.replace(
                        tzinfo=dt.timezone.utc
                    )
                )

            ET.SubElement(
                item,
                "pubDate"
            ).text = format_datetime(
                date_value
            )

        if article["description"]:

            ET.SubElement(
                item,
                "description"
            ).text = html.escape(
                article["description"]
            )

    tree = ET.ElementTree(rss)

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 60)

    print(
        "EL CONFIDENCIAL - EMPRESAS"
    )

    print("=" * 60)

    articles = collect_articles()

    print(
        f"\nArtículos obtenidos: "
        f"{len(articles)}"
    )

    if not articles:
        raise RuntimeError(
            "No se encontraron artículos."
        )

    print(
        "\nÚltimos titulares:"
    )

    for article in articles[:20]:
        print(
            "- " + article["title"]
        )

    create_rss(articles)

    print(
        "\nRSS creada correctamente:"
    )

    print(OUTPUT_FILE)


if __name__ == "__main__":
    main()

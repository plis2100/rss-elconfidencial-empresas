import hashlib
import datetime as dt
import xml.etree.ElementTree as ET

from email.utils import parsedate_to_datetime, format_datetime

import requests


# ============================================================
# CONFIGURACIÓN
# ============================================================

SOURCE_RSS = "https://rss.elconfidencial.com/empresas/"

OUTPUT_FILE = "feed.xml"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0 Safari/537.36"
    ),
    "Accept": (
        "application/rss+xml,"
        "application/xml;q=0.9,"
        "text/xml;q=0.8,"
        "*/*;q=0.7"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


# ============================================================
# DESCARGAR RSS OFICIAL
# ============================================================

def download_rss():

    print("=" * 60)
    print("Descargando RSS oficial de El Confidencial")
    print(SOURCE_RSS)
    print("=" * 60)

    response = requests.get(
        SOURCE_RSS,
        headers=HEADERS,
        timeout=45,
    )

    print(
        "Código HTTP:",
        response.status_code
    )

    response.raise_for_status()

    return response.content


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return str(value).strip()


# ============================================================
# PROCESAR FECHA
# ============================================================

def parse_date(value):

    if not value:
        return None

    try:

        result = parsedate_to_datetime(
            value
        )

        if result.tzinfo is None:

            result = result.replace(
                tzinfo=dt.timezone.utc
            )

        return result

    except Exception as exc:

        print(
            "No se pudo interpretar fecha:",
            value,
            exc
        )

        return None


# ============================================================
# LEER RSS OFICIAL
# ============================================================

def collect_articles():

    content = download_rss()

    try:

        root = ET.fromstring(
            content
        )

    except ET.ParseError as exc:

        print(
            "ERROR leyendo XML:",
            exc
        )

        raise

    articles = []

    # ========================================================
    # RSS 2.0
    # ========================================================

    items = root.findall(
        ".//item"
    )

    print(
        "Entradas encontradas en RSS:",
        len(items)
    )

    for item in items:

        # ----------------------------------------------------
        # TITULAR
        # ----------------------------------------------------

        title = clean_text(
            item.findtext(
                "title"
            )
        )

        # ----------------------------------------------------
        # ENLACE
        # ----------------------------------------------------

        link = clean_text(
            item.findtext(
                "link"
            )
        )

        # ----------------------------------------------------
        # DESCRIPCIÓN
        # ----------------------------------------------------

        description = clean_text(
            item.findtext(
                "description"
            )
        )

        # ----------------------------------------------------
        # FECHA
        # ----------------------------------------------------

        pub_date_raw = clean_text(
            item.findtext(
                "pubDate"
            )
        )

        published = parse_date(
            pub_date_raw
        )

        # ----------------------------------------------------
        # VALIDACIÓN
        # ----------------------------------------------------

        if not title:

            print(
                "Entrada ignorada: "
                "sin titular"
            )

            continue

        if not link:

            print(
                "Entrada ignorada: "
                "sin enlace:",
                title
            )

            continue

        # ----------------------------------------------------
        # GUID
        # ----------------------------------------------------

        guid_original = clean_text(
            item.findtext(
                "guid"
            )
        )

        if guid_original:

            guid = guid_original

        else:

            guid = hashlib.sha256(
                link.encode(
                    "utf-8"
                )
            ).hexdigest()

        # ----------------------------------------------------
        # GUARDAR
        # ----------------------------------------------------

        articles.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "date": published,
                "guid": guid,
            }
        )

    # ========================================================
    # ORDENAR POR FECHA
    # ========================================================

    articles.sort(
        key=lambda article: (
            article["date"]
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
# CREAR RSS PARA FEEDLY
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

    # ========================================================
    # INFORMACIÓN DEL CANAL
    # ========================================================

    ET.SubElement(
        channel,
        "title"
    ).text = (
        "El Confidencial - Empresas"
    )

    ET.SubElement(
        channel,
        "link"
    ).text = (
        "https://www.elconfidencial.com/empresas/"
    )

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

    # ========================================================
    # NOTICIAS
    # ========================================================

    for article in articles:

        item = ET.SubElement(
            channel,
            "item"
        )

        # ====================================================
        # IMPORTANTE:
        #
        # SOLO EL TITULAR ORIGINAL
        #
        # No añadimos:
        # - EL CONFIDENCIAL
        # - fecha
        # - hora
        # - categoría
        #
        # Feedly mostrará únicamente el titular.
        # ====================================================

        ET.SubElement(
            item,
            "title"
        ).text = article[
            "title"
        ]

        # ====================================================
        # ENLACE ORIGINAL
        # ====================================================

        ET.SubElement(
            item,
            "link"
        ).text = article[
            "link"
        ]

        # ====================================================
        # GUID
        # ====================================================

        guid_element = ET.SubElement(
            item,
            "guid",
            {
                "isPermaLink": "false"
            }
        )

        guid_element.text = article[
            "guid"
        ]

        # ====================================================
        # FECHA
        #
        # Se mantiene internamente para que Feedly ordene
        # correctamente las noticias.
        #
        # NO se añade al titular.
        # ====================================================

        if article["date"]:

            ET.SubElement(
                item,
                "pubDate"
            ).text = format_datetime(
                article["date"]
            )

        # ====================================================
        # DESCRIPCIÓN
        # ====================================================

        if article["description"]:

            ET.SubElement(
                item,
                "description"
            ).text = article[
                "description"
            ]

    # ========================================================
    # GUARDAR FEED.XML
    # ========================================================

    tree = ET.ElementTree(
        rss
    )

    ET.indent(
        tree,
        space="  "
    )

    tree.write(
        OUTPUT_FILE,
        encoding="utf-8",
        xml_declaration=True,
    )


# ============================================================
# PROGRAMA PRINCIPAL
# ============================================================

def main():

    print()
    print("=" * 60)
    print("EL CONFIDENCIAL - EMPRESAS")
    print("=" * 60)
    print()

    articles = collect_articles()

    print()
    print(
        "Noticias obtenidas:",
        len(articles)
    )
    print()

    # ========================================================
    # EVITAR CREAR RSS VACÍA
    # ========================================================

    if not articles:

        raise RuntimeError(
            "No se encontraron noticias "
            "en la RSS de El Confidencial."
        )

    # ========================================================
    # MOSTRAR TITULARES EN ACTIONS
    # ========================================================

    print(
        "Últimos titulares:"
    )

    print(
        "-" * 60
    )

    for article in articles[:20]:

        print(
            article["title"]
        )

    print(
        "-" * 60
    )

    # ========================================================
    # CREAR RSS
    # ========================================================

    create_rss(
        articles
    )

    print()
    print(
        "RSS creada correctamente:"
    )

    print(
        OUTPUT_FILE
    )

    print()
    print(
        "Total de noticias:",
        len(articles)
    )

    print()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()

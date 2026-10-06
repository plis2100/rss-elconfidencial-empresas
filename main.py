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
        "application/atom+xml,"
        "application/xml,"
        "text/xml,"
        "text/html;q=0.9,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "es-ES,es;q=0.9",
}


# ============================================================
# LIMPIAR TEXTO
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    return " ".join(
        str(value).split()
    )


# ============================================================
# DESCARGAR
# ============================================================

def download_source():

    print("=" * 60)
    print("DESCARGANDO EL CONFIDENCIAL - EMPRESAS")
    print(SOURCE_RSS)
    print("=" * 60)

    response = requests.get(
        SOURCE_RSS,
        headers=HEADERS,
        timeout=45,
        allow_redirects=True,
    )

    print("Código HTTP:", response.status_code)
    print("URL final:", response.url)

    print(
        "Content-Type:",
        response.headers.get(
            "content-type",
            "DESCONOCIDO"
        )
    )

    print(
        "Tamaño:",
        len(response.content),
        "bytes"
    )

    response.raise_for_status()

    return response


# ============================================================
# FECHAS
# ============================================================

def parse_date(value):

    if not value:
        return None

    value = clean_text(value)

    # --------------------------------------------------------
    # RFC 822 / RSS
    # --------------------------------------------------------

    try:

        result = parsedate_to_datetime(
            value
        )

        if result.tzinfo is None:

            result = result.replace(
                tzinfo=dt.timezone.utc
            )

        return result

    except Exception:
        pass

    # --------------------------------------------------------
    # ISO 8601 / ATOM
    # --------------------------------------------------------

    try:

        iso_value = value.replace(
            "Z",
            "+00:00"
        )

        result = dt.datetime.fromisoformat(
            iso_value
        )

        if result.tzinfo is None:

            result = result.replace(
                tzinfo=dt.timezone.utc
            )

        return result

    except Exception:
        pass

    return None


# ============================================================
# NOMBRE LOCAL DE ETIQUETA XML
# ============================================================

def local_name(tag):

    if not isinstance(tag, str):
        return ""

    if "}" in tag:
        return tag.split("}", 1)[1]

    return tag


# ============================================================
# BUSCAR HIJO POR NOMBRE
# ============================================================

def find_child(element, names):

    names = set(names)

    for child in element:

        if local_name(
            child.tag
        ) in names:

            return child

    return None


# ============================================================
# TEXTO DE HIJO
# ============================================================

def child_text(element, names):

    child = find_child(
        element,
        names
    )

    if child is None:
        return ""

    text = "".join(
        child.itertext()
    )

    return clean_text(
        text
    )


# ============================================================
# EXTRAER ENLACE
# ============================================================

def extract_link(element):

    for child in element:

        if local_name(
            child.tag
        ) != "link":

            continue

        # ATOM
        href = child.attrib.get(
            "href"
        )

        if href:

            rel = child.attrib.get(
                "rel",
                "alternate"
            )

            if rel in (
                "",
                "alternate"
            ):

                return clean_text(
                    href
                )

        # RSS
        if child.text:

            link = clean_text(
                child.text
            )

            if link:
                return link

    return ""


# ============================================================
# DETECTAR ENTRADAS
# ============================================================

def find_entries(root):

    entries = []

    for element in root.iter():

        name = local_name(
            element.tag
        )

        if name in (
            "item",
            "entry"
        ):

            entries.append(
                element
            )

    return entries


# ============================================================
# EXTRAER ARTÍCULOS
# ============================================================

def collect_articles():

    response = download_source()

    content = response.content

    # --------------------------------------------------------
    # INTENTAR LEER XML
    # --------------------------------------------------------

    try:

        root = ET.fromstring(
            content
        )

    except ET.ParseError as exc:

        print()
        print("=" * 60)
        print("NO ES XML VÁLIDO")
        print("=" * 60)

        print(
            "Error:",
            exc
        )

        print()
        print(
            "PRIMEROS 2000 CARACTERES "
            "RECIBIDOS:"
        )

        print("-" * 60)

        print(
            response.text[:2000]
        )

        print("-" * 60)

        raise RuntimeError(
            "El servidor no está devolviendo "
            "un RSS/Atom/XML válido."
        )

    # --------------------------------------------------------
    # INFORMACIÓN DEL XML
    # --------------------------------------------------------

    print()
    print(
        "Etiqueta raíz:",
        root.tag
    )

    entries = find_entries(
        root
    )

    print(
        "Entradas item/entry encontradas:",
        len(entries)
    )

    # --------------------------------------------------------
    # SI NO HAY ENTRADAS
    # --------------------------------------------------------

    if not entries:

        print()
        print("=" * 60)
        print("NO SE HAN ENCONTRADO NOTICIAS")
        print("=" * 60)

        print()
        print(
            "Etiquetas XML encontradas:"
        )

        names = []

        for element in root.iter():

            name = local_name(
                element.tag
            )

            if (
                name
                and name not in names
            ):

                names.append(
                    name
                )

        for name in names[:100]:

            print(
                "-",
                name
            )

        print()
        print(
            "PRIMEROS 3000 CARACTERES "
            "DE LA RESPUESTA:"
        )

        print("-" * 60)

        print(
            response.text[:3000]
        )

        print("-" * 60)

        raise RuntimeError(
            "La dirección responde HTTP 200, "
            "pero no contiene entradas RSS/Atom."
        )

    # --------------------------------------------------------
    # PROCESAR ENTRADAS
    # --------------------------------------------------------

    articles = []

    seen = set()

    for entry in entries:

        title = child_text(
            entry,
            [
                "title"
            ]
        )

        link = extract_link(
            entry
        )

        description = child_text(
            entry,
            [
                "description",
                "summary",
                "content",
            ]
        )

        date_raw = child_text(
            entry,
            [
                "pubDate",
                "published",
                "updated",
                "date",
            ]
        )

        published = parse_date(
            date_raw
        )

        guid = child_text(
            entry,
            [
                "guid",
                "id",
            ]
        )

        # ----------------------------------------------------
        # VALIDAR
        # ----------------------------------------------------

        if not title:
            continue

        if not link:
            continue

        # ----------------------------------------------------
        # EVITAR DUPLICADOS
        # ----------------------------------------------------

        key = link.strip()

        if key in seen:
            continue

        seen.add(
            key
        )

        if not guid:

            guid = hashlib.sha256(
                link.encode(
                    "utf-8"
                )
            ).hexdigest()

        articles.append(
            {
                "title": title,
                "link": link,
                "description": description,
                "date": published,
                "guid": guid,
            }
        )

    # --------------------------------------------------------
    # ORDENAR
    # --------------------------------------------------------

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
        "Noticias de Empresas "
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
        # SOLO EL TITULAR
        # ====================================================

        ET.SubElement(
            item,
            "title"
        ).text = article[
            "title"
        ]

        # ----------------------------------------------------
        # ENLACE
        # ----------------------------------------------------

        ET.SubElement(
            item,
            "link"
        ).text = article[
            "link"
        ]

        # ----------------------------------------------------
        # GUID
        # ----------------------------------------------------

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

        # ----------------------------------------------------
        # FECHA
        #
        # Feedly la usa para ordenar,
        # pero NO aparece añadida al titular.
        # ----------------------------------------------------

        if article["date"]:

            ET.SubElement(
                item,
                "pubDate"
            ).text = format_datetime(
                article["date"]
            )

        # ----------------------------------------------------
        # DESCRIPCIÓN
        # ----------------------------------------------------

        if article["description"]:

            ET.SubElement(
                item,
                "description"
            ).text = article[
                "description"
            ]

    # ========================================================
    # GUARDAR
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
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("EL CONFIDENCIAL - EMPRESAS")
    print("=" * 60)
    print()

    articles = collect_articles()

    print()
    print("=" * 60)
    print(
        "NOTICIAS OBTENIDAS:",
        len(articles)
    )
    print("=" * 60)

    if not articles:

        raise RuntimeError(
            "No se encontraron noticias."
        )

    print()
    print(
        "ÚLTIMOS TITULARES:"
    )

    print("-" * 60)

    for article in articles[:30]:

        print(
            "-",
            article["title"]
        )

    print("-" * 60)

    # --------------------------------------------------------
    # CREAR FEED.XML
    # --------------------------------------------------------

    create_rss(
        articles
    )

    print()
    print("=" * 60)
    print(
        "RSS CREADA CORRECTAMENTE"
    )
    print("=" * 60)

    print(
        "Archivo:",
        OUTPUT_FILE
    )

    print(
        "Noticias:",
        len(articles)
    )

    print()


# ============================================================
# EJECUCIÓN
# ============================================================

if __name__ == "__main__":

    main()

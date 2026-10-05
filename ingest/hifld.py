"""Electric retail service territory polygons (HIFLD, EIA utility ID in `ID`). HIFLD Open
was shut down 2025-08-26; this is the community mirror's GeoParquet release."""
from ingest.common import http_get, snapshot

SOURCE_ID = "hifld_territories"
URL = ("https://storage.googleapis.com/hifld-next-portolan-published/hifld/electric-retail-service-territories/"
       "electric-retail-service-territories/v1.0.0/geoparquet/electric-retail-service-territories.parquet")


def run() -> bool:
    return snapshot(SOURCE_ID, http_get(URL, timeout=300).content, "retail_service_territories.parquet") is not None

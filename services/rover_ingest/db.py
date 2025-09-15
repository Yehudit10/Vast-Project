import os
import psycopg2
from .schema import ImageMeta

DSN = os.getenv(
    "PG_DSN",
    "dbname=missions_db user=missions_user host=db password=Missions!ChangeMe123"
)

SQL_UPSERT = """
INSERT INTO rover.images (
  image_id, device_id, captured_at,
  lat, lon, heading_deg, pitch_deg, roll_deg, alt_m, fov_deg, gps_accuracy_m, temp_c,
  s3_key, mime_type, size_bytes, sha256, exif_present, firmware, capture_seq,
  meta_src, schema_ver, source_ts, trace_id
)
VALUES (
  %(image_id)s, %(device_id)s, %(captured_at)s,
  %(lat)s, %(lon)s, %(heading_deg)s, %(pitch_deg)s, %(roll_deg)s, %(alt_m)s, %(fov_deg)s, %(gps_accuracy_m)s, %(temp_c)s,
  %(s3_key)s, %(mime_type)s, %(size_bytes)s, %(sha256)s, %(exif_present)s, %(firmware)s, %(capture_seq)s,
  %(meta_src)s, %(schema_ver)s, %(source_ts)s, %(trace_id)s
)
ON CONFLICT (image_id) DO UPDATE SET
  device_id       = EXCLUDED.device_id,
  captured_at     = EXCLUDED.captured_at,
  lat             = EXCLUDED.lat,
  lon             = EXCLUDED.lon,
  heading_deg     = COALESCE(EXCLUDED.heading_deg, rover.images.heading_deg),
  pitch_deg       = COALESCE(EXCLUDED.pitch_deg, rover.images.pitch_deg),
  roll_deg        = COALESCE(EXCLUDED.roll_deg, rover.images.roll_deg),
  alt_m           = COALESCE(EXCLUDED.alt_m, rover.images.alt_m),
  fov_deg         = COALESCE(EXCLUDED.fov_deg, rover.images.fov_deg),
  gps_accuracy_m  = COALESCE(EXCLUDED.gps_accuracy_m, rover.images.gps_accuracy_m),
  temp_c          = COALESCE(EXCLUDED.temp_c, rover.images.temp_c),
  s3_key          = EXCLUDED.s3_key,
  mime_type       = COALESCE(EXCLUDED.mime_type, rover.images.mime_type),
  size_bytes      = COALESCE(EXCLUDED.size_bytes, rover.images.size_bytes),
  sha256          = COALESCE(EXCLUDED.sha256, rover.images.sha256),
  exif_present    = COALESCE(EXCLUDED.exif_present, rover.images.exif_present),
  firmware        = COALESCE(EXCLUDED.firmware, rover.images.firmware),
  capture_seq     = COALESCE(EXCLUDED.capture_seq, rover.images.capture_seq),
  meta_src        = EXCLUDED.meta_src,
  schema_ver      = GREATEST(rover.images.schema_ver, EXCLUDED.schema_ver),
  source_ts       = COALESCE(EXCLUDED.source_ts, rover.images.source_ts),
  trace_id        = COALESCE(EXCLUDED.trace_id, rover.images.trace_id);
"""

def _row(meta: ImageMeta) -> dict:
    return {
        "image_id": meta.image_id,
        "device_id": meta.device_id,
        "captured_at": meta.captured_at,
        "lat": meta.gps.lat,
        "lon": meta.gps.lon,
        "heading_deg": meta.heading_deg,
        "pitch_deg": meta.pitch_deg,
        "roll_deg": meta.roll_deg,
        "alt_m": meta.alt_m,
        "fov_deg": meta.fov_deg,
        "gps_accuracy_m": meta.gps.gps_accuracy_m,
        "temp_c": meta.temp_c,
        "s3_key": meta.s3_key,
        "mime_type": meta.mime_type,
        "size_bytes": meta.size_bytes,
        "sha256": meta.sha256,
        "exif_present": meta.exif_present,
        "firmware": meta.firmware,
        "capture_seq": meta.capture_seq,
        "meta_src": meta.meta_src,
        "schema_ver": meta.schema_ver,
        "source_ts": meta.source_ts,
        "trace_id": meta.trace_id,
    }

def upsert(meta: ImageMeta) -> None:
    with psycopg2.connect(DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(SQL_UPSERT, _row(meta))

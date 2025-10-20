# # from fastapi import APIRouter, Header, HTTPException
# # from pydantic import BaseModel
# # from typing import Optional, List
# # from db_writer import insert_result  # הפונקציה שלך שמכניסה ל-DB

# # router = APIRouter(prefix="/api/fruit_defect_results", tags=["Fruit Defect"])

# # # Payload של רשומה בודדת
# # class FruitDefectItem(BaseModel):
# #     fruit_id: str
# #     status: str
# #     defect_type: Optional[str] = None
# #     severity: Optional[float] = None
# #     metrics: Optional[dict] = None
# #     latency_ms: Optional[float] = None

# # # Payload של batch
# # class FruitDefectPayload(BaseModel):
# #     results: List[FruitDefectItem]

# # # Endpoint להוספת רשומות
# # @router.post("/")
# # def create_fruit_defect(payload: FruitDefectPayload, x_service_token: str = Header(...)):
# #     # --- בדיקת token פשוטה ---
# #     # פה אפשר לבדוק מול DB או פשוט מול env
# #     from os import getenv
# #     SERVICE_TOKEN = getenv("SERVICE_TOKEN", "changeme")
# #     if x_service_token != SERVICE_TOKEN:
# #         raise HTTPException(status_code=401, detail="Invalid service token")

# #     inserted = 0
# #     for item in payload.results:
# #         try:
# #             insert_result(
# #                 fruit_id=item.fruit_id,
# #                 status=item.status,
# #                 defect_type=item.defect_type,
# #                 severity=item.severity,
# #                 metrics=item.metrics,
# #                 latency_ms=item.latency_ms
# #             )
# #             inserted += 1
# #         except Exception as e:
# #             print(f"[WARNING] Failed to insert {item.fruit_id}: {e}")

# #     return {"inserted": inserted, "total": len(payload.results)}


# # services/db_api_service/app/fruit_defect.py
# # English-only comments to match repo guidelines.

# from __future__ import annotations

# import json
# import os
# from typing import Any, Dict, List, Optional

# from fastapi import APIRouter, Header, HTTPException
# from pydantic import BaseModel, Field, validator
# from sqlalchemy import text
# from sqlalchemy.exc import SQLAlchemyError

# from app.db import session_scope, engine  # engine is used by /ready

# router = APIRouter(prefix="/api/fruit_defect_results", tags=["Fruit Defect"])

# # -----------------------------
# # Models
# # -----------------------------

# class FruitDefectItem(BaseModel):
#     fruit_id: str = Field(..., description="Unique fruit identifier (string)")
#     status: str = Field(..., description='"ok" or "defect"')
#     defect_type: Optional[str] = Field(
#         None, description='Defect type when status="defect" (e.g., "mold", "rot")'
#     )
#     severity: Optional[float] = Field(
#         None, ge=0.0, le=1.0, description="Optional defect severity in [0.0, 1.0]"
#     )
#     metrics: Optional[Dict[str, Any]] = Field(
#         None, description="Arbitrary model metrics to persist as JSONB"
#     )
#     latency_ms: Optional[float] = Field(None, ge=0.0, description="Inference latency")

#     @validator("status")
#     def _validate_status(cls, v: str) -> str:
#         vv = v.lower().strip()
#         if vv not in {"ok", "defect"}:
#             raise ValueError('status must be "ok" or "defect"')
#         return vv

#     @validator("defect_type")
#     def _require_defect_type_if_defect(cls, v: Optional[str], values: Dict[str, Any]):
#         st = values.get("status")
#         if st == "defect" and (v is None or not str(v).strip()):
#             # We allow missing defect_type, but you can flip this to raise if you want.
#             return v
#         return v


# class FruitDefectPayload(BaseModel):
#     results: List[FruitDefectItem] = Field(..., min_items=1)


# # -----------------------------
# # Helpers
# # -----------------------------

# def _require_service_token(x_service_token: str) -> None:
#     expected = os.getenv("SERVICE_TOKEN", "changeme")
#     if not expected or expected == "changeme":
#         # Intentionally strict: fail fast if SERVICE_TOKEN not configured properly.
#         raise HTTPException(
#             status_code=500,
#             detail="SERVICE_TOKEN is not configured on the server",
#         )
#     if x_service_token != expected:
#         raise HTTPException(status_code=401, detail="invalid service token")


# def _json_dumps_safe(d: Optional[Dict[str, Any]]) -> Optional[str]:
#     if d is None:
#         return None
#     # Ensure non-ASCII is preserved and keep it compact.
#     return json.dumps(d, ensure_ascii=False, separators=(",", ":"))


# # -----------------------------
# # Health & Ready
# # -----------------------------

# @router.get("/healthz")
# def healthz():
#     return {"status": "ok"}


# @router.get("/ready")
# def ready():
#     # Lightweight DB check: open a connection and run a trivial query.
#     try:
#         with engine.connect() as conn:
#             conn.execute(text("SELECT 1"))
#         return {"ready": True}
#     except SQLAlchemyError as e:
#         return {"ready": False, "error": str(e)}


# # -----------------------------
# # Main endpoint
# # -----------------------------

# @router.post("/", summary="Insert fruit defect results (bulk)")
# def create_fruit_defect_results(
#     payload: FruitDefectPayload,
#     x_service_token: str = Header(..., convert_underscores=False),
# ):
#     """
#     Inserts a batch of fruit defect results into public.fruit_defect_results.

#     Security: requires header `X-Service-Token` that matches SERVICE_TOKEN env var.

#     Table schema expected (public.fruit_defect_results):
#         fruit_id      TEXT NOT NULL
#         status        TEXT NOT NULL
#         defect_type   TEXT NULL
#         severity      DOUBLE PRECISION NULL
#         metrics       JSONB NULL
#         latency_ms    DOUBLE PRECISION NULL
#         created_at    TIMESTAMPTZ DEFAULT now()
#         (other columns are fine; extra columns will be ignored by this INSERT)
#     """
#     _require_service_token(x_service_token)

#     insert_sql = text(
#         """
#         INSERT INTO public.fruit_defect_results
#             (fruit_id, status, defect_type, severity, metrics, latency_ms)
#         VALUES
#             (:fruit_id, :status, :defect_type, :severity, CAST(:metrics AS jsonb), :latency_ms)
#         """
#     )

#     # Execute within one transaction. If any item fails, the whole batch rolls back.
#     try:
#         with session_scope() as s:
#             for item in payload.results:
#                 s.execute(
#                     insert_sql,
#                     {
#                         "fruit_id": item.fruit_id,
#                         "status": item.status,
#                         "defect_type": item.defect_type,
#                         "severity": item.severity,
#                         "metrics": _json_dumps_safe(item.metrics),
#                         "latency_ms": item.latency_ms,
#                     },
#                 )
#         return {"inserted": len(payload.results)}
#     except SQLAlchemyError as e:
#         # Convert DB errors into a clean 400 for the client, with message attached.
#         raise HTTPException(status_code=400, detail=f"DB error: {e}") from e


# # -----------------------------
# # Optional: small convenience endpoint (single insert)
# # -----------------------------

# @router.post("/single", summary="Insert a single fruit defect result")
# def create_single_fruit_defect_result(
#     item: FruitDefectItem,
#     x_service_token: str = Header(..., convert_underscores=False),
# ):
#     _require_service_token(x_service_token)

#     insert_sql = text(
#         """
#         INSERT INTO public.fruit_defect_results
#             (fruit_id, status, defect_type, severity, metrics, latency_ms)
#         VALUES
#             (:fruit_id, :status, :defect_type, :severity, CAST(:metrics AS jsonb), :latency_ms)
#         """
#     )

#     try:
#         with session_scope() as s:
#             s.execute(
#                 insert_sql,
#                 {
#                     "fruit_id": item.fruit_id,
#                     "status": item.status,
#                     "defect_type": item.defect_type,
#                     "severity": item.severity,
#                     "metrics": _json_dumps_safe(item.metrics),
#                     "latency_ms": item.latency_ms,
#                 },
#             )
#         return {"inserted": 1}
#     except SQLAlchemyError as e:
#         raise HTTPException(status_code=400, detail=f"DB error: {e}") from e

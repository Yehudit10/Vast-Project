# from dotenv import load_dotenv
# load_dotenv()

# import os
# from sqlalchemy import create_engine
# from sqlalchemy.orm import sessionmaker
# from contextlib import contextmanager

# from app.models import Base

# DB_DSN = os.getenv(
#     "DB_DSN",
#     "postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db"
# )

# engine = create_engine(
#     DB_DSN,
#     pool_pre_ping=True,
#     pool_size=10,
#     max_overflow=20
# )

# SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# @contextmanager
# def session_scope():
#     s = SessionLocal()
#     try:
#         yield s
#         s.commit()
#     except:
#         s.rollback()
#         raise
#     finally:
#         s.close()

# def init_models():
#     Base.metadata.create_all(bind=engine)
# app/db.py
from dotenv import load_dotenv
load_dotenv()

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager
from sqlalchemy.pool import StaticPool  # <— הוסיפי

from app.models import Base

DB_DSN = os.getenv(
    "DB_DSN",
    "postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db"
)

# --- Engine setup ---
if DB_DSN.startswith("sqlite"):

    engine = create_engine(
        DB_DSN,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool, 
        echo=False
    )
else:
    pool_size = int(os.getenv("DB_POOL_SIZE", "5"))
    max_overflow = int(os.getenv("DB_MAX_OVERFLOW", "10"))
    engine = create_engine(
        DB_DSN,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_pre_ping=True,
        echo=False
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()

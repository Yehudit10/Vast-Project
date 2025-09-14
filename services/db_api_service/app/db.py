
from dotenv import load_dotenv
load_dotenv()  

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from contextlib import contextmanager

DB_DSN = os.getenv("DB_DSN", "postgresql+psycopg://missions_user:pg123@localhost:5432/missions_db")
engine = create_engine(DB_DSN, pool_pre_ping=True, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except:
        s.rollback()
        raise
    finally:
        s.close()


"""
SQLAlchemy session and engine setup
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.config.settings import settings
from app.models import Base

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
	Base.metadata.create_all(bind=engine)

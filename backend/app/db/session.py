from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.core.config import config
from backend.app.models.database_models import Base

engine = create_engine(
    config.database_url,
    connect_args={"check_same_thread": False}
    if config.database_url.startswith("sqlite")
    else {},
)
Session = sessionmaker(engine, expire_on_commit=False)


def initialize():
    Base.metadata.create_all(engine)


def get_db():
    with Session() as db:
        yield db

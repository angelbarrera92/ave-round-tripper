from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()


class Sqlite():
    def __init__(self, db_file_path: str) -> None:
        self.engine = create_engine(f"sqlite:///{db_file_path}")
        _session = sessionmaker(bind=self.engine)
        self.session = _session()
        Base.metadata.create_all(self.engine)

    def __del__(self):
        try:
            self.session.close()
        except:
            pass

class MySQL():
    def __init__(self, user: str, password: str, host: str, port: int, db: str) -> None:
        self.engine = create_engine(f"mysql://{user}:{password}@{host}:{port}/{db}")
        _session = sessionmaker(bind=self.engine)
        self.session = _session()
        Base.metadata.create_all(self.engine)

    def __del__(self):
        try:
            self.session.close()
        except:
            pass

class PostgreSQL():
    def __init__(self, user: str, password: str, host: str, port: int, db: str) -> None:
        self.engine = create_engine(f"postgresql://{user}:{password}@{host}:{port}/{db}")
        _session = sessionmaker(bind=self.engine)
        self.session = _session()
        Base.metadata.create_all(self.engine)

    def __del__(self):
        try:
            self.session.close()
        except:
            pass

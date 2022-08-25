from datetime import datetime

from src.db.models import Metadata


def update_metadata(db, table):
    m = db.session.query(Metadata).get((table))
    if m:
        m.update_date = datetime.now()
    else:
        m = Metadata(table, datetime.now())
    db.session.add(m)
    db.session.commit()

from datetime import datetime, timedelta

from src.config import RunConfig
from src.db.models import RoundTripTimeSeries


def clean_old_timeseries(cfg: RunConfig, historical_data_days: int):
    now = datetime.now()
    target_date = now - timedelta(days=historical_data_days)
    cfg.log.info(f"cleaning up data before {target_date}")
    cfg.db.session.query(RoundTripTimeSeries).filter(
        RoundTripTimeSeries.date <= target_date).delete()
    cfg.db.session.commit()

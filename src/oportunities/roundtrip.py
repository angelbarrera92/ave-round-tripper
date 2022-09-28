from datetime import datetime, timedelta

from src.config import RunConfig
from src.db.metadata import update_metadata
from src.db.models import RoundTrip, RoundTripTimeSeries, Train
from sqlalchemy.sql.expression import cast, func
import sqlalchemy

# TODO: Think about creating a soft interface like I did for the scrapers


def round_trip(cfg: RunConfig, origin: str, fromOriginAt: str, destination: str, fromDestinationAt: str, notificationTargetPrice: float) -> None:
    cfg.log.info("running round_trip oportunity finder")
    cfg.log.debug("configuration")
    cfg.log.debug(
        f"origin: {origin} | fromOriginAt: {fromOriginAt} | destination: {destination}| fromDestinationAt: {fromDestinationAt} | notificationTargetPrice: {notificationTargetPrice}")
    cfg.log.info("querying origin trains")
    originTrains = cfg.db.session.query(Train).filter(Train.origin_station == origin).filter(
        Train.departure_date >= datetime.now()).filter(cast(Train.departure_date, sqlalchemy.String).contains(fromOriginAt)).filter(Train.price > 0).all()
    cfg.log.debug(f"found {len(originTrains)}")
    _round_trip_trains(cfg, origin, fromOriginAt, destination,
                       fromDestinationAt, notificationTargetPrice, originTrains)


def round_trip(cfg: RunConfig, day: datetime, origin: str, fromOriginAt: str, destination: str, fromDestinationAt: str, notificationTargetPrice: float) -> None:
    cfg.log.info(
        f"running round_trip oportunity finder for {day.strftime('%d/%m/%Y')}")
    cfg.log.debug("configuration")
    cfg.log.debug(
        f"day: {day} | origin: {origin} | fromOriginAt: {fromOriginAt} | destination: {destination}| fromDestinationAt: {fromDestinationAt} | notificationTargetPrice: {notificationTargetPrice}")
    cfg.log.info("querying origin trains")
    nextTargetDate = day + timedelta(days=1)
    day = day.replace(hour=0, minute=0, second=0, microsecond=0)
    nextTargetDate = nextTargetDate.replace(
        hour=0, minute=0, second=0, microsecond=0)
    originTrains = cfg.db.session.query(Train).filter(Train.origin_station == origin).filter(Train.destination_station == destination).filter(Train.departure_date >= datetime.now(
    )).filter(Train.departure_date >= day).filter(Train.departure_date < nextTargetDate).filter(cast(Train.departure_date, sqlalchemy.String).contains(fromOriginAt)).filter(Train.price > 0).all()
    cfg.log.debug(f"found {len(originTrains)}")
    _round_trip_trains(cfg, origin, fromOriginAt, destination,
                       fromDestinationAt, notificationTargetPrice, originTrains)


def _round_trip_trains(cfg: RunConfig, origin: str, fromOriginAt: str, destination: str, fromDestinationAt: str, notificationTargetPrice: float, originTrains):
    for originTrain in originTrains:
        targetDateStr = datetime.strftime(
            originTrain.departure_date, "%d/%m/%Y")
        targetDate = datetime.strptime(targetDateStr, "%d/%m/%Y")
        nextTargetDate = targetDate + timedelta(days=1)
        cfg.log.info(f"querying return trains for {targetDateStr}")
        destinationTrains = cfg.db.session.query(Train).filter(Train.origin_station == destination).filter(Train.destination_station == origin).filter(
            Train.departure_date >= targetDate).filter(Train.departure_date < nextTargetDate).filter(cast(Train.departure_date, sqlalchemy.String).contains(fromDestinationAt)).filter(Train.price > 0).all()
        cfg.log.debug(f"found {len(destinationTrains)}")
        for destinationTrain in destinationTrains:
            cfg.log.debug("destinationTrain: " + str(destinationTrain))
            alert = False
            priceChanged = False
            oldPrice = 0
            newPrice = 0
            newRoundTrip = False
            cfg.log.debug("querying to see if was already registered")
            roundTrip = cfg.db.session.query(RoundTrip).get(
                (originTrain.origin_station, originTrain.departure_date, destinationTrain.origin_station, destinationTrain.departure_date))
            if roundTrip:
                cfg.log.debug("found")
                if roundTrip.departure_price != originTrain.price or roundTrip.return_price != destinationTrain.price:
                    cfg.log.debug("price changed. enqueue to notify")
                    cfg.log.debug("roundTrip.departure_price: " +
                                  str(roundTrip.departure_price))
                    cfg.log.debug("originTrain.price: " +
                                  str(originTrain.price))
                    cfg.log.debug("roundTrip.return_price: " +
                                  str(roundTrip.return_price))
                    cfg.log.debug("destinationTrain.price: " +
                                  str(destinationTrain.price))
                    alert = True
                    priceChanged = True
                    oldPrice = roundTrip.total_price
                    newPrice = originTrain.price + destinationTrain.price
                cfg.log.debug("updating")
                roundTrip.departure_price = originTrain.price
                roundTrip.return_price = destinationTrain.price
                roundTrip.total_price = originTrain.price + destinationTrain.price
                roundTrip.update_date = datetime.now()
            else:
                cfg.log.debug("not found. creating... then enqueue notify")
                roundTrip = RoundTrip(originTrain.origin_station, originTrain.departure_date, originTrain.price,
                                      destinationTrain.origin_station, destinationTrain.departure_date, destinationTrain.price)
                alert = True
                newRoundTrip = True
                newPrice = roundTrip.total_price

            # Add a way to notify the user
            # in case the price is lower than the min price registered
            cfg.log.debug("ready to find the min price for this round trip")
            minPrice = cfg.db.session.query(func.min(RoundTripTimeSeries.total_price)).filter(RoundTripTimeSeries.departure_station == originTrain.origin_station).filter(RoundTripTimeSeries.departure_date == originTrain.departure_date).filter(RoundTripTimeSeries.return_station == destinationTrain.origin_station).filter(RoundTripTimeSeries.return_date == destinationTrain.departure_date).scalar()
            cfg.log.debug(f"minPrice found: {minPrice}")
            if minPrice and newPrice < minPrice:
                cfg.log.debug("new min price. enqueue to notify")
                alert = True
                newMinPrice = True
            else:
                newMinPrice = False

            roundTripTS = RoundTripTimeSeries(originTrain.origin_station, originTrain.departure_date, originTrain.price,
                                              destinationTrain.origin_station, destinationTrain.departure_date, destinationTrain.price)
            cfg.db.session.add(roundTripTS)
            cfg.db.session.add(roundTrip)
            cfg.db.session.commit()

            if alert:
                targetDateStr = datetime.strftime(
                    originTrain.departure_date, "%A %d/%m/%Y")

                # New notifications
                # Only if price drop
                if newMinPrice:
                    cfg.notification.send(
                        f"🔥🔥🔥🔥 {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. From {oldPrice}€ to {newPrice}€. New min price! 🔥🔥🔥🔥")
                elif priceChanged and newPrice < oldPrice:
                    cfg.notification.send(
                        f"↓↓↓↓ {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. From {oldPrice}€ to {newPrice}€")
                # Only if its a new opportunity with a low price
                elif newRoundTrip and (newPrice <= notificationTargetPrice):
                    cfg.notification.send(
                        f"►►►► {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. {newPrice}€")
                # Old notifications
                # if priceChanged and newPrice > oldPrice:
                #     cfg.notification.send(
                #         f"↑↑↑↑ {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. From {oldPrice}€ to {newPrice}€")
                # elif priceChanged and newPrice < oldPrice and (newPrice <= notificationTargetPrice):
                #     cfg.notification.send(
                #         f"↓↓↓↓ {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. From {oldPrice}€ to {newPrice}€")
                # elif newRoundTrip and (newPrice <= notificationTargetPrice):
                #     cfg.notification.send(
                #         f"►►►► {targetDateStr} {origin}-{destination} {fromOriginAt}-{fromDestinationAt}. {newPrice}€")

    update_metadata(cfg.db, RoundTrip.__tablename__)
    update_metadata(cfg.db, RoundTripTimeSeries.__tablename__)

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String
from sqlalchemy.sql import func
from src.db.db import Base


class Metadata(Base):
    __tablename__ = "metadata"
    table = Column(String(50), primary_key=True)
    update_date = Column(DateTime)

    def __init__(self, table, update_date) -> None:
        self.table = table
        self.update_date = update_date

    def copy(self):
        return Metadata(self.table, self.update_date)


class Room(Base):
    __tablename__ = "rooms"
    arrival_date = Column(DateTime, primary_key=True)
    arrival_timestamp = Column(Integer)
    departure_date = Column(DateTime, primary_key=True)
    departure_timestamp = Column(Integer)
    kind = Column(String(100), primary_key=True)
    price = Column(Float)

    def __init__(self, arrival_date, departure_date, kind, price) -> None:
        self.arrival_date = arrival_date
        self.departure_date = departure_date
        self.kind = kind
        self.price = price
        self.arrival_timestamp = int(datetime.timestamp(self.arrival_date))
        self.departure_timestamp = int(datetime.timestamp(self.departure_date))

    def copy(self):
        return Room(self.arrival_date, self.departure_date, self.kind, self.price)


class RoundTrip(Base):
    __tablename__ = "roundtrips"
    departure_station = Column(String(100), primary_key=True)
    departure_date = Column(DateTime, primary_key=True)
    departure_price = Column(Float)
    return_station = Column(String(100), primary_key=True)
    return_date = Column(DateTime, primary_key=True)
    return_price = Column(Float)
    total_price = Column(Float)
    creation_date = Column(DateTime)
    update_date = Column(DateTime)

    def __init__(self, departure_station, departure_date, departure_price, return_station, return_date, return_price):
        self.departure_station = departure_station
        self.departure_date = departure_date
        self.departure_price = departure_price
        self.return_station = return_station
        self.return_date = return_date
        self.return_price = return_price
        self.total_price = departure_price + return_price
        self.creation_date = datetime.now()

    def copy(self):
        return RoundTrip(self.departure_station, self.departure_date, self.departure_price, self.return_station, self.return_date, self.return_price)


class RoundTripTimeSeries(Base):
    __tablename__ = "roundtripsts"
    uid = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime)
    departure_station = Column(String(100))
    departure_date = Column(DateTime)
    departure_price = Column(Float)
    return_station = Column(String(100))
    return_date = Column(DateTime)
    return_price = Column(Float)
    total_price = Column(Float)

    def __init__(self, departure_station, departure_date, departure_price, return_station, return_date, return_price):
        self.departure_station = departure_station
        self.departure_date = departure_date
        self.departure_price = departure_price
        self.return_station = return_station
        self.return_date = return_date
        self.return_price = return_price
        self.total_price = departure_price + return_price
        self.date = datetime.now()

    def copy(self):
        c = RoundTripTimeSeries(self.departure_station, self.departure_date,
                                self.departure_price, self.return_station, self.return_date, self.return_price)
        c.date = self.date
        return c


class Train(Base):
    __tablename__ = "trains"
    origin_station = Column(String(100), primary_key=True)
    departure_timestamp = Column(Integer, primary_key=True)
    departure_date = Column(DateTime)
    destination_station = Column(String(100), primary_key=True)
    arrival_timestamp = Column(Integer, primary_key=True)
    arrival_date = Column(DateTime)
    price = Column(Float)
    kind = Column(String(100))

    def __init__(self, departure_timestamp, origin_station, destination_station, price, arrival_timestamp, kind) -> None:
        self.departure_timestamp = departure_timestamp
        self.origin_station = origin_station
        self.destination_station = destination_station
        self.price = price
        self.arrival_timestamp = arrival_timestamp
        self.kind = kind

    def copy(self):
        newData = Train(self.departure_timestamp, self.origin_station,
                        self.destination_station, self.price, self.arrival_timestamp, self.kind)
        newData.departure_date = self.departure_date
        newData.arrival_date = self.arrival_date
        return newData

    def __repr__(self) -> str:
        return self.origin_station + " (" + datetime.strftime(self.departure_date, "%H.%M %d/%m/%Y") + ") " + self.destination_station + " (" + datetime.strftime(self.arrival_date, "%H.%M %d/%m/%Y")+") " + str(self.price)

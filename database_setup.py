import os
import sys
import datetime
from sqlalchemy import Column, ForeignKey, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy import create_engine

Base = declarative_base()


class User(Base):
    """Table defintion for users"""
    __tablename__ = 'user'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)
    email = Column(String(250), nullable=False)
    picture = Column(String(250))


class Country(Base):
    """Define Categories Table"""
    __tablename__ = 'country'

    id = Column(Integer, primary_key=True)
    name = Column(String(250), nullable=False)

    @property
    def serialize(self):
        # Returns object data in easily serializeable format
        return {
            'id': self.id,
            'name': self.name
        }

class University(Base):
    """Define faculties Table"""
    __tablename__ = 'university'

    id = Column(Integer, primary_key=True)
    university_name = Column(String(255), nullable=False)
    common_abbreviation = Column(String(255))
    year_established = Column(DateTime)
    description = Column(String())
    last_updated = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now)
    country_id = Column(Integer, ForeignKey('country.id'))
    country = relationship(Country)
    user_id = Column(Integer, ForeignKey('user.id'))
    user = relationship(User)

    @property
    def serialize(self):
        # Returns object data in easily serialize-able format
        return {
            'university_name': self.university_name,
            'common_abbreviation': self.common_abbreviation,
            'id': self.id,
            'description': self.description,
            'country': self.country.name,
            'last_updated': self.last_updated
        }

engine = create_engine('sqlite:///catalog.db')
Base.metadata.create_all(engine)
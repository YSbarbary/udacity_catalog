from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database_setup import Country, Base, University, User

import datetime
import csv

engine = create_engine('sqlite:///catalog.db')
# Bind the engine to the metadata of the Base class so that the
# declaratives can be accessed through a DBSession instance
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
# A DBSession() instance establishes all conversations with the database
# and represents a "staging zone" for all the objects loaded into the
# database session object. Any change made against the objects in the
# session won't be persisted into the database until you call
# session.commit(). If you're not happy about the changes, you can
# revert all of them back to the last commit by calling
# session.rollback()
session = DBSession()


# Create dummy user

User2 = User(
    name="yasser",
    email="yasser.al-barbary@live.com",
    picture='#')
session.add(User2)
session.commit()

User3 = User(
    name="yasser2",
    email="smallbarbary@gmail.com",
    picture='#')
session.add(User3)
session.commit()

with open('sample_data/country.csv', 'rb') as csvfile:
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in reader:
        country = Country(name=row[0])
        session.add(country)
        session.commit()

with open('sample_data/university.csv', 'rb') as csvfile:
    reader = csv.reader(csvfile, delimiter=',', quotechar='"')
    for row in reader:
        country = session.query(Country).filter_by(name=row[0]).one()
        year_established = datetime.datetime.strptime(
            row[3], "%d/%m/%Y").date()
        university = University(
            university_name=row[1],
            common_abbreviation=row[2],
            year_established=year_established,
            description=row[4],
            country_id=country.id,
            user_id=User2.id
        )
        session.add(university)
        session.commit()

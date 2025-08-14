# /app/methods/database/init_db.py
from database import Base, engine
from models import User

Base.metadata.create_all(bind=engine)

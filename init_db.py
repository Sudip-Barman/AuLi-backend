from database import Base, engine
from models import User, ChatMessage, Log

Base.metadata.create_all(bind=engine)

print("DB initialized")
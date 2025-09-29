from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from db import Base

class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, nullable=False)
    game = Column(String, nullable=False)
    unique_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    used = Column(Boolean, default=False)  # ✅ статус: False = активен, True = использован

from sqlalchemy import Column, Integer, String, DateTime, Boolean, func
from db import Base

class Registration(Base):
    __tablename__ = "registrations"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(Integer, nullable=False)
    game = Column(String, nullable=False)           # Купимания или Мир проектов
    slot_date = Column(String, nullable=False)      # дата игры (08.10.2025)
    slot_time = Column(String, nullable=False)      # время игры (11:20–12:00)
    unique_id = Column(String, unique=True, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    used = Column(Boolean, default=False)           # статус пропуска

import uuid
from datetime import datetime

from sqlalchemy import String, Text, Boolean, DateTime, Integer, Numeric, JSON
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    whatsapp_id: Mapped[str | None] = mapped_column(String(100))

    # Extracted from CV
    education: Mapped[dict | None] = mapped_column(JSON)
    experience: Mapped[dict | None] = mapped_column(JSON)
    skills: Mapped[list | None] = mapped_column(ARRAY(String))
    languages: Mapped[dict | None] = mapped_column(JSON)
    certifications: Mapped[list | None] = mapped_column(ARRAY(String))
    total_years_exp: Mapped[int | None] = mapped_column(Integer)

    # Kuwait-specific
    visa_status: Mapped[str | None] = mapped_column(String(50))
    nationality: Mapped[str | None] = mapped_column(String(100))
    expected_salary: Mapped[float | None] = mapped_column(Numeric(10, 2))
    availability: Mapped[str | None] = mapped_column(String(100))

    # Files
    cv_url: Mapped[str | None] = mapped_column(String(500))
    cv_text: Mapped[str | None] = mapped_column(Text)
    ai_summary: Mapped[str | None] = mapped_column(Text)

    # Consent
    network_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_date: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    applications: Mapped[list["Application"]] = relationship(back_populates="candidate")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="candidate")

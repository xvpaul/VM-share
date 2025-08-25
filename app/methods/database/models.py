from sqlalchemy import Column, Integer, String, CheckConstraint, text
from .database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    snapshot_storage_capacity = Column(Integer, nullable=False, server_default=text("300"))
    snapshot_stored = Column(Integer, nullable=False, server_default=text("0"))
    role = Column(String, nullable=False, server_default=text("'user'"))
    __table_args__ = (
        CheckConstraint("snapshot_storage_capacity >= 0", name="users_cap_nonneg"),
        CheckConstraint("snapshot_stored >= 0", name="users_stored_nonneg"),
        CheckConstraint("snapshot_stored <= snapshot_storage_capacity", name="users_stored_le_cap"),
    )

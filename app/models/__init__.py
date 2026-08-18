from sqlalchemy.orm import DeclarativeBase


# Modern approach (SQLAlchemy 2.0+)
class Base(DeclarativeBase):
    pass


# Register the models for Migration.
# E402: these imports must run *after* Base is defined above, because each model
# module does `from . import Base`. Moving them to the top is a circular import.
from . import (  # noqa: E402
    admin_activity,  # noqa: F401
    bot_instruction,  # noqa: F401
    document,  # noqa: F401
    document_query_hit,  # noqa: F401
    form_submission,  # noqa: F401
    user,  # noqa: F401
)

"""Time helpers.

`datetime.utcnow()` is deprecated from Python 3.12. The obvious replacement,
`datetime.now(UTC)`, is NOT equivalent: it returns an *aware* datetime, while
`utcnow()` returns a naive one. Swapping them changes behaviour, because:

* the SQLAlchemy columns in this project are naive (`DateTime` without
  `timezone=True`), and mixing aware values into them raises on comparison;
* documents already stored in MongoDB hold naive timestamps, so an aware value
  would compare unequal to data written before the change;
* subtracting an aware from a naive datetime raises TypeError outright.

Stripping the tzinfo again gives exactly the value `utcnow()` produced, with no
deprecation warning, so existing rows and documents stay comparable.
"""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current UTC time as a naive datetime.

    Identical in value to the deprecated `datetime.utcnow()`.
    """
    return datetime.now(UTC).replace(tzinfo=None)

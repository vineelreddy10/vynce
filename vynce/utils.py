from datetime import date


def calculate_age(birth_date: date) -> int:
    """Calculate age from a birth date."""
    today = date.today()
    return today.year - birth_date.year - (
        (today.month, today.day) < (birth_date.month, birth_date.day)
    )


GENDER_MAP = {
    "Male": "M",
    "Female": "F",
    "Non-Binary": "NB",
    "Prefer not to say": "PNS",
}

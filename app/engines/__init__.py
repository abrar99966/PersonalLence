from .base import Engine
from .gosearch import GoSearch
from .holehe import Holehe
from .maigret import Maigret
from .phoneinfoga import PhoneInfoga
from .sherlock import Sherlock

# registry — order = display order
ALL_ENGINES: list[Engine] = [
    Maigret(),
    Sherlock(),
    GoSearch(),
    Holehe(),
    PhoneInfoga(),
]

from .base import Engine
from .gosearch import GoSearch
from .holehe import Holehe
from .ignorant import Ignorant
from .maigret import Maigret
from .phoneinfoga import PhoneInfoga
from .sherlock import Sherlock

# registry — order = display order
ALL_ENGINES: list[Engine] = [
    Maigret(),       # username — deepest (all sites) + profile data
    Sherlock(),      # username — fast confirm
    GoSearch(),      # username — sites + breach (HudsonRock/ProxyNova)
    Holehe(),        # email — registration across 120+ sites
    Ignorant(),      # phone — registration (Instagram/Amazon/Snapchat)
    PhoneInfoga(),   # phone — carrier/region + dork links
]

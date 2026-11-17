"""UGC / SAME geography for the Chicago (LOT) county warning area.

Counties carry the metadata BMH needs: UGC zone (``ILZ014``), state and county
FIPS (used to build SAME ``PSSCCC`` codes), and an approximate centroid used by
the map canvas and the polygon-to-zone resolver.
"""

from __future__ import annotations

from dataclasses import dataclass

STATE_FIPS = {"IL": "17", "IN": "18", "WI": "55", "MI": "26", "IA": "19"}
STATE_NAMES = {
    "IL": "Illinois",
    "IN": "Indiana",
    "WI": "Wisconsin",
    "MI": "Michigan",
    "IA": "Iowa",
}


@dataclass(frozen=True)
class Zone:
    ugc: str
    name: str
    state: str
    fips: str
    lat: float
    lon: float
    marine: bool = False

    @property
    def same(self) -> str:
        """SAME ``PSSCCC`` (part 0 + state FIPS + county FIPS)."""
        return f"0{STATE_FIPS[self.state]}{self.fips}"

    @property
    def label(self) -> str:
        return f"{self.name} {self.state}" if not self.marine else self.ugc

    @property
    def full_name(self) -> str:
        if self.marine:
            return MARINE_NAMES.get(self.ugc, self.ugc)
        return f"{self.name} County"


MARINE_NAMES = {
    "LMZ740": "Calumet Harbor IL to Gary IN",
    "LMZ741": "Gary to Burns Harbor IN",
    "LMZ742": "Burns Harbor to Michigan City IN",
    "LMZ743": "Winthrop Harbor to Wilmette Harbor IL",
    "LMZ744": "Wilmette Harbor to Northerly Island IL",
    "LMZ745": "Northerly Island to Calumet Harbor IL",
}


def _z(ugc: str, name: str, state: str, fips: str, lat: float, lon: float) -> Zone:
    return Zone(ugc, name, state, fips, lat, lon)


ZONE_LIST: list[Zone] = [
    # ---- Illinois: LOT northern / central CWA -------------------------
    _z("ILZ003", "Winnebago", "IL", "201", 42.34, -89.20),
    _z("ILZ004", "Boone", "IL", "007", 42.42, -88.83),
    _z("ILZ005", "McHenry", "IL", "111", 42.32, -88.45),
    _z("ILZ006", "Lake", "IL", "097", 42.43, -88.05),
    _z("ILZ007", "Ogle", "IL", "141", 42.05, -89.35),
    _z("ILZ008", "Lee", "IL", "103", 41.75, -89.30),
    _z("ILZ009", "DeKalb", "IL", "037", 41.90, -88.77),
    _z("ILZ010", "Kane", "IL", "089", 41.95, -88.43),
    _z("ILZ011", "DuPage", "IL", "043", 41.85, -88.03),
    _z("ILZ012", "Cook", "IL", "031", 41.84, -87.78),
    _z("ILZ013", "LaSalle", "IL", "099", 41.35, -88.88),
    _z("ILZ014", "Kendall", "IL", "093", 41.59, -88.43),
    _z("ILZ015", "Grundy", "IL", "063", 41.29, -88.43),
    _z("ILZ016", "Will", "IL", "197", 41.45, -87.98),
    _z("ILZ017", "Kankakee", "IL", "091", 41.15, -87.87),
    _z("ILZ018", "Livingston", "IL", "105", 40.89, -88.58),
    _z("ILZ019", "Iroquois", "IL", "075", 40.75, -87.83),
    _z("ILZ020", "Ford", "IL", "053", 40.60, -88.22),
    _z("ILZ021", "Vermilion", "IL", "183", 40.18, -87.73),
    _z("ILZ022", "Putnam", "IL", "155", 41.20, -89.28),
    _z("ILZ023", "Bureau", "IL", "011", 41.40, -89.53),
    _z("ILZ024", "Henry", "IL", "073", 41.35, -90.15),
    _z("ILZ025", "Mercer", "IL", "131", 41.20, -90.72),
    _z("ILZ026", "Stark", "IL", "175", 40.98, -89.80),
    _z("ILZ027", "Marshall", "IL", "123", 41.03, -89.35),
    _z("ILZ028", "Woodford", "IL", "203", 40.78, -89.20),
    _z("ILZ029", "Tazewell", "IL", "179", 40.51, -89.51),
    _z("ILZ030", "McLean", "IL", "113", 40.49, -88.85),
    _z("ILZ031", "Logan", "IL", "107", 40.13, -89.36),
    _z("ILZ032", "De Witt", "IL", "039", 40.18, -88.95),
    _z("ILZ033", "Piatt", "IL", "147", 40.02, -88.60),
    _z("ILZ034", "Champaign", "IL", "019", 40.14, -88.20),
    _z("ILZ035", "Douglas", "IL", "041", 39.77, -88.22),
    _z("ILZ036", "Coles", "IL", "029", 39.52, -88.22),
    _z("ILZ037", "Edgar", "IL", "045", 39.68, -87.75),
    _z("ILZ038", "Moultrie", "IL", "139", 39.64, -88.62),
    _z("ILZ039", "Shelby", "IL", "173", 39.39, -88.80),
    _z("ILZ040", "Cumberland", "IL", "035", 39.27, -88.24),
    _z("ILZ041", "Effingham", "IL", "049", 39.06, -88.59),
    # ---- Indiana: LOT eastern CWA -------------------------------------
    _z("INZ001", "Lake", "IN", "089", 41.42, -87.37),
    _z("INZ002", "Porter", "IN", "127", 41.46, -87.07),
    _z("INZ003", "LaPorte", "IN", "091", 41.55, -86.74),
    _z("INZ004", "St. Joseph", "IN", "141", 41.62, -86.28),
    _z("INZ005", "Elkhart", "IN", "039", 41.60, -85.87),
    _z("INZ006", "LaGrange", "IN", "087", 41.65, -85.43),
    _z("INZ007", "Steuben", "IN", "151", 41.64, -85.00),
    _z("INZ008", "Noble", "IN", "113", 41.40, -85.42),
    _z("INZ009", "De Kalb", "IN", "033", 41.40, -84.99),
    _z("INZ010", "Allen", "IN", "003", 41.09, -85.07),
    _z("INZ011", "Whitley", "IN", "183", 41.14, -85.50),
    _z("INZ012", "Huntington", "IN", "069", 40.83, -85.49),
    _z("INZ013", "Wells", "IN", "179", 40.73, -85.22),
    _z("INZ014", "Adams", "IN", "001", 40.75, -84.94),
    _z("INZ015", "Grant", "IN", "053", 40.52, -85.65),
    _z("INZ016", "Blackford", "IN", "009", 40.47, -85.32),
    _z("INZ017", "Jay", "IN", "075", 40.43, -85.01),
    _z("INZ018", "Newton", "IN", "111", 40.95, -87.40),
    _z("INZ019", "Jasper", "IN", "073", 41.03, -87.12),
    _z("INZ020", "Benton", "IN", "007", 40.60, -87.31),
    _z("INZ021", "White", "IN", "181", 40.75, -86.87),
    _z("INZ022", "Pulaski", "IN", "131", 41.04, -86.70),
    _z("INZ023", "Starke", "IN", "149", 41.28, -86.65),
    _z("INZ024", "Marshall", "IN", "099", 41.32, -86.26),
    _z("INZ025", "Kosciusko", "IN", "085", 41.24, -85.86),
    _z("INZ026", "Fulton", "IN", "049", 41.05, -86.26),
    _z("INZ027", "Miami", "IN", "103", 40.77, -86.10),
    _z("INZ028", "Wabash", "IN", "169", 40.85, -85.79),
    _z("INZ029", "Cass", "IN", "017", 40.76, -86.35),
    _z("INZ030", "Carroll", "IN", "015", 40.58, -86.56),
    _z("INZ031", "Warren", "IN", "171", 40.35, -87.35),
    _z("INZ032", "Tippecanoe", "IN", "157", 40.39, -86.89),
    _z("INZ033", "Clinton", "IN", "023", 40.30, -86.48),
    _z("INZ034", "Boone", "IN", "011", 40.05, -86.47),
    _z("INZ035", "Hamilton", "IN", "057", 40.04, -86.02),
    _z("INZ036", "Madison", "IN", "095", 40.16, -85.72),
    _z("INZ037", "Delaware", "IN", "035", 40.23, -85.40),
    _z("INZ038", "Randolph", "IN", "135", 40.16, -85.01),
    _z("INZ039", "Henry", "IN", "065", 39.93, -85.40),
    _z("INZ040", "Wayne", "IN", "177", 39.86, -85.01),
    # ---- Nearshore Lake Michigan --------------------------------------
    Zone("LMZ740", "Calumet Harbor to Gary", "IL", "000", 41.75, -87.42, True),
    Zone("LMZ741", "Gary to Burns Harbor", "IN", "000", 41.67, -87.15, True),
    Zone("LMZ742", "Burns Harbor to Michigan City", "IN", "000", 41.70, -86.82, True),
    Zone("LMZ743", "Winthrop Harbor to Wilmette", "IL", "000", 42.22, -87.74, True),
    Zone("LMZ744", "Wilmette to Northerly Island", "IL", "000", 41.96, -87.60, True),
    Zone("LMZ745", "Northerly Island to Calumet Harbor", "IL", "000", 41.83, -87.53, True),
]

ZONES: dict[str, Zone] = {z.ugc: z for z in ZONE_LIST}
LAND_ZONES = [z for z in ZONE_LIST if not z.marine]
MARINE_ZONES = [z for z in ZONE_LIST if z.marine]

CITY_COORDS: dict[str, tuple[float, float]] = {
    "Chicago": (41.878, -87.63),
    "Chicago O'Hare": (41.98, -87.90),
    "Chicago Midway": (41.79, -87.75),
    "Waukegan": (42.36, -87.83),
    "Aurora": (41.76, -88.32),
    "Joliet": (41.53, -88.08),
    "Rockford": (42.27, -89.09),
    "DeKalb": (41.93, -88.75),
    "Ottawa": (41.35, -88.84),
    "Kankakee": (41.12, -87.86),
    "Pontiac": (40.88, -88.63),
    "Morris": (41.36, -88.42),
    "Wheaton": (41.87, -88.11),
    "Evanston": (42.05, -87.69),
    "Oak Lawn": (41.72, -87.76),
    "Calumet City": (41.62, -87.53),
    "Valparaiso": (41.47, -87.06),
    "Gary": (41.59, -87.35),
    "Hammond": (41.60, -87.50),
    "Merrillville": (41.48, -87.33),
    "Crown Point": (41.42, -87.37),
    "Schererville": (41.49, -87.45),
    "Chesterton": (41.61, -87.06),
    "Portage": (41.58, -87.18),
    "Hebron": (41.32, -87.20),
    "Rensselaer": (40.94, -87.15),
    "LaPorte": (41.61, -86.72),
    "Plymouth": (41.34, -86.31),
    "Knox": (41.30, -86.63),
    "Peru": (40.75, -86.07),
    "Winamac": (41.05, -86.60),
    "Morocco": (40.94, -87.45),
    "Benton Harbor": (42.12, -86.45),
    "South Bend": (41.68, -86.25),
    "Michigan City": (41.71, -86.90),
    "Milwaukee": (43.04, -87.90),
}

TRANSMITTERS: dict[str, tuple[float, float]] = {
    "WXJ75": (41.4731, -87.0611),
    "KBB58": (41.5645, -87.3365),
    "KLOT": (41.6047, -88.0846),
}

WATER_POLYGON: list[tuple[float, float]] = [
    (42.52, -87.79), (42.45, -87.74), (42.30, -87.70), (42.10, -87.63),
    (41.95, -87.55), (41.88, -87.53), (41.78, -87.42), (41.73, -87.32),
    (41.66, -87.20), (41.63, -87.02), (41.63, -86.85), (41.70, -86.78),
    (41.80, -86.70), (42.00, -86.60), (42.20, -86.55), (42.50, -86.40),
    (42.55, -87.10), (42.55, -87.60),
]

LISTENING_STATES = ("IL", "IN")

# County seats used in ZFP headlines ("Including the city of ...")
SEATS: dict[str, str] = {
    "ILZ003": "Rockford", "ILZ004": "Belvidere", "ILZ005": "Woodstock",
    "ILZ006": "Waukegan", "ILZ007": "Oregon", "ILZ008": "Dixon",
    "ILZ009": "Sycamore", "ILZ010": "Aurora", "ILZ011": "Wheaton",
    "ILZ012": "Chicago", "ILZ013": "Ottawa", "ILZ014": "Yorkville",
    "ILZ015": "Morris", "ILZ016": "Joliet", "ILZ017": "Kankakee",
    "ILZ018": "Pontiac", "ILZ019": "Watseka", "ILZ020": "Paxton",
    "ILZ021": "Danville", "ILZ022": "Hennepin", "ILZ023": "Princeton",
    "ILZ024": "Cambridge", "ILZ025": "Aledo", "ILZ026": "Toulon",
    "ILZ027": "Lacon", "ILZ028": "Eureka", "ILZ029": "Pekin",
    "ILZ030": "Bloomington", "ILZ031": "Lincoln", "ILZ032": "Clinton",
    "ILZ033": "Monticello", "ILZ034": "Champaign", "ILZ035": "Tuscola",
    "ILZ036": "Charleston", "ILZ037": "Paris", "ILZ038": "Sullivan",
    "ILZ039": "Shelbyville", "ILZ040": "Toledo", "ILZ041": "Effingham",
    "INZ001": "Gary", "INZ002": "Valparaiso", "INZ003": "LaPorte",
    "INZ004": "South Bend", "INZ005": "Elkhart", "INZ006": "LaGrange",
    "INZ007": "Angola", "INZ008": "Albion", "INZ009": "Auburn",
    "INZ010": "Fort Wayne", "INZ011": "Columbia City", "INZ012": "Huntington",
    "INZ013": "Bluffton", "INZ014": "Decatur", "INZ015": "Marion",
    "INZ016": "Hartford City", "INZ017": "Portland", "INZ018": "Kentland",
    "INZ019": "Rensselaer", "INZ020": "Fowler", "INZ021": "Monticello",
    "INZ022": "Winamac", "INZ023": "Knox", "INZ024": "Plymouth",
    "INZ025": "Warsaw", "INZ026": "Rochester", "INZ027": "Peru",
    "INZ028": "Wabash", "INZ029": "Logansport", "INZ030": "Delphi",
    "INZ031": "Williamsport", "INZ032": "Lafayette", "INZ033": "Frankfort",
    "INZ034": "Lebanon", "INZ035": "Noblesville", "INZ036": "Anderson",
    "INZ037": "Muncie", "INZ038": "Winchester", "INZ039": "New Castle",
    "INZ040": "Richmond",
}


def seat(ugc: str, default: str | None = None) -> str:
    zone_obj = ZONES.get(ugc.upper())
    if ugc.upper() in SEATS:
        return SEATS[ugc.upper()]
    return default or (zone_obj.name if zone_obj else ugc)



def zone(ugc: str) -> Zone | None:
    return ZONES.get(ugc.upper())


def zone_name(ugc: str) -> str:
    z = ZONES.get(ugc.upper())
    return z.label if z else ugc


def zone_names(ugc_list: list[str]) -> list[str]:
    return [zone_name(u) for u in ugc_list]


def same_for_ugc(ugc: str) -> str | None:
    z = ZONES.get(ugc.upper())
    return z.same if z else None


def same_list(ugc_list: list[str]) -> list[str]:
    out = []
    for u in ugc_list:
        code = same_for_ugc(u)
        if code and code not in out:
            out.append(code)
    return out


def ugc_for_same(code: str) -> str | None:
    for z in ZONE_LIST:
        if z.same == code:
            return z.ugc
    return None


def zones_in_state(state: str) -> list[Zone]:
    return [z for z in LAND_ZONES if z.state == state]


def ugc_block(ugc_list: list[str], purge: str = "") -> str:
    """NWS style UGC line: ``ILZ014-ILZ103-161530-``."""
    parts = [u for u in ugc_list]
    if not parts:
        return purge or ""
    block = "-".join(parts)
    if purge:
        block = f"{block}-{purge}"
    return block + "-"


def parse_ugc(text: str) -> list[str]:
    found: list[str] = []
    for token in text.replace(",", " ").replace("-", " ").split():
        token = token.strip().upper()
        if len(token) == 6 and token[2] == "Z" and token in ZONES and token not in found:
            found.append(token)
    return found


def zones_near(lat: float, lon: float, radius_deg: float = 0.45) -> list[str]:
    out = []
    for z in LAND_ZONES:
        if abs(z.lat - lat) <= radius_deg and abs(z.lon - lon) <= radius_deg * 1.4:
            out.append(z.ugc)
    return out


def zones_for_polygon(points: list[tuple[float, float]]) -> list[str]:
    """Resolve a storm polygon (lat/lon) to the UGC zones it covers."""
    if not points:
        return []
    out: list[str] = []
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    for z in LAND_ZONES:
        if min(lats) - 0.12 <= z.lat <= max(lats) + 0.12 and \
           min(lons) - 0.16 <= z.lon <= max(lons) + 0.16:
            out.append(z.ugc)
    return out


def describe_area(ugc_list: list[str]) -> str:
    """Human/voice friendly area phrase for a UGC set."""
    names = [z.name for z in (ZONES.get(u) for u in ugc_list) if z and not z.marine]
    states = sorted({ZONES[u].state for u in ugc_list if u in ZONES})
    if not names:
        return "portions of northeast Illinois and northwest Indiana"
    if len(names) == 1:
        base = names[0]
    elif len(names) == 2:
        base = f"{names[0]} and {names[1]}"
    else:
        base = ", ".join(names[:-1]) + f", and {names[-1]}"
    if states == ["IL"]:
        return f"{base} Counties in Illinois"
    if states == ["IN"]:
        return f"{base} Counties in Indiana"
    return f"{base} Counties in Illinois and Indiana"

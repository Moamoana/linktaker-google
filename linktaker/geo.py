"""Country resolution for --geo.

One place that turns whatever the user types — `my`, `malaysia`, `Malaysia`,
`MY` — into a single country record. Each engine then spends that record its own
way (`gl=` on Google, `cc=` on Bing, a regional host on Yahoo), which is why the
mapping lives here instead of inside any one engine.
"""

import difflib
from dataclasses import dataclass

# ISO 3166-1 alpha-2 -> the country's common English name. The code is what the
# engines actually send; the name only ever appears in messages.
COUNTRIES = {
    "af": "Afghanistan", "ax": "Aland Islands", "al": "Albania", "dz": "Algeria",
    "as": "American Samoa", "ad": "Andorra", "ao": "Angola", "ai": "Anguilla",
    "aq": "Antarctica", "ag": "Antigua and Barbuda", "ar": "Argentina",
    "am": "Armenia", "aw": "Aruba", "au": "Australia", "at": "Austria",
    "az": "Azerbaijan", "bs": "Bahamas", "bh": "Bahrain", "bd": "Bangladesh",
    "bb": "Barbados", "by": "Belarus", "be": "Belgium", "bz": "Belize",
    "bj": "Benin", "bm": "Bermuda", "bt": "Bhutan", "bo": "Bolivia",
    "bq": "Bonaire", "ba": "Bosnia and Herzegovina", "bw": "Botswana",
    "bv": "Bouvet Island", "br": "Brazil", "io": "British Indian Ocean Territory",
    "bn": "Brunei", "bg": "Bulgaria", "bf": "Burkina Faso", "bi": "Burundi",
    "cv": "Cabo Verde", "kh": "Cambodia", "cm": "Cameroon", "ca": "Canada",
    "ky": "Cayman Islands", "cf": "Central African Republic", "td": "Chad",
    "cl": "Chile", "cn": "China", "cx": "Christmas Island",
    "cc": "Cocos (Keeling) Islands", "co": "Colombia", "km": "Comoros",
    "cg": "Congo", "cd": "Congo (DRC)", "ck": "Cook Islands", "cr": "Costa Rica",
    "ci": "Cote d Ivoire", "hr": "Croatia", "cu": "Cuba", "cw": "Curacao",
    "cy": "Cyprus", "cz": "Czechia", "dk": "Denmark", "dj": "Djibouti",
    "dm": "Dominica", "do": "Dominican Republic", "ec": "Ecuador", "eg": "Egypt",
    "sv": "El Salvador", "gq": "Equatorial Guinea", "er": "Eritrea",
    "ee": "Estonia", "sz": "Eswatini", "et": "Ethiopia", "fk": "Falkland Islands",
    "fo": "Faroe Islands", "fj": "Fiji", "fi": "Finland", "fr": "France",
    "gf": "French Guiana", "pf": "French Polynesia",
    "tf": "French Southern Territories", "ga": "Gabon", "gm": "Gambia",
    "ge": "Georgia", "de": "Germany", "gh": "Ghana", "gi": "Gibraltar",
    "gr": "Greece", "gl": "Greenland", "gd": "Grenada", "gp": "Guadeloupe",
    "gu": "Guam", "gt": "Guatemala", "gg": "Guernsey", "gn": "Guinea",
    "gw": "Guinea-Bissau", "gy": "Guyana", "ht": "Haiti",
    "hm": "Heard Island and McDonald Islands", "va": "Vatican City",
    "hn": "Honduras", "hk": "Hong Kong", "hu": "Hungary", "is": "Iceland",
    "in": "India", "id": "Indonesia", "ir": "Iran", "iq": "Iraq",
    "ie": "Ireland", "im": "Isle of Man", "il": "Israel", "it": "Italy",
    "jm": "Jamaica", "jp": "Japan", "je": "Jersey", "jo": "Jordan",
    "kz": "Kazakhstan", "ke": "Kenya", "ki": "Kiribati", "kp": "North Korea",
    "kr": "South Korea", "kw": "Kuwait", "kg": "Kyrgyzstan", "la": "Laos",
    "lv": "Latvia", "lb": "Lebanon", "ls": "Lesotho", "lr": "Liberia",
    "ly": "Libya", "li": "Liechtenstein", "lt": "Lithuania", "lu": "Luxembourg",
    "mo": "Macao", "mg": "Madagascar", "mw": "Malawi", "my": "Malaysia",
    "mv": "Maldives", "ml": "Mali", "mt": "Malta", "mh": "Marshall Islands",
    "mq": "Martinique", "mr": "Mauritania", "mu": "Mauritius", "yt": "Mayotte",
    "mx": "Mexico", "fm": "Micronesia", "md": "Moldova", "mc": "Monaco",
    "mn": "Mongolia", "me": "Montenegro", "ms": "Montserrat", "ma": "Morocco",
    "mz": "Mozambique", "mm": "Myanmar", "na": "Namibia", "nr": "Nauru",
    "np": "Nepal", "nl": "Netherlands", "nc": "New Caledonia",
    "nz": "New Zealand", "ni": "Nicaragua", "ne": "Niger", "ng": "Nigeria",
    "nu": "Niue", "nf": "Norfolk Island", "mk": "North Macedonia",
    "mp": "Northern Mariana Islands", "no": "Norway", "om": "Oman",
    "pk": "Pakistan", "pw": "Palau", "ps": "Palestine", "pa": "Panama",
    "pg": "Papua New Guinea", "py": "Paraguay", "pe": "Peru",
    "ph": "Philippines", "pn": "Pitcairn", "pl": "Poland", "pt": "Portugal",
    "pr": "Puerto Rico", "qa": "Qatar", "re": "Reunion", "ro": "Romania",
    "ru": "Russia", "rw": "Rwanda", "bl": "Saint Barthelemy",
    "sh": "Saint Helena", "kn": "Saint Kitts and Nevis", "lc": "Saint Lucia",
    "mf": "Saint Martin", "pm": "Saint Pierre and Miquelon",
    "vc": "Saint Vincent and the Grenadines", "ws": "Samoa", "sm": "San Marino",
    "st": "Sao Tome and Principe", "sa": "Saudi Arabia", "sn": "Senegal",
    "rs": "Serbia", "sc": "Seychelles", "sl": "Sierra Leone", "sg": "Singapore",
    "sx": "Sint Maarten", "sk": "Slovakia", "si": "Slovenia",
    "sb": "Solomon Islands", "so": "Somalia", "za": "South Africa",
    "gs": "South Georgia and the South Sandwich Islands", "ss": "South Sudan",
    "es": "Spain", "lk": "Sri Lanka", "sd": "Sudan", "sr": "Suriname",
    "sj": "Svalbard and Jan Mayen", "se": "Sweden", "ch": "Switzerland",
    "sy": "Syria", "tw": "Taiwan", "tj": "Tajikistan", "tz": "Tanzania",
    "th": "Thailand", "tl": "Timor-Leste", "tg": "Togo", "tk": "Tokelau",
    "to": "Tonga", "tt": "Trinidad and Tobago", "tn": "Tunisia", "tr": "Turkiye",
    "tm": "Turkmenistan", "tc": "Turks and Caicos Islands", "tv": "Tuvalu",
    "ug": "Uganda", "ua": "Ukraine", "ae": "United Arab Emirates",
    "gb": "United Kingdom", "us": "United States",
    "um": "United States Minor Outlying Islands", "uy": "Uruguay",
    "uz": "Uzbekistan", "vu": "Vanuatu", "ve": "Venezuela", "vn": "Vietnam",
    "vg": "British Virgin Islands", "vi": "U.S. Virgin Islands",
    "wf": "Wallis and Futuna", "eh": "Western Sahara", "ye": "Yemen",
    "zm": "Zambia", "zw": "Zimbabwe",
}

# Everything else a country gets called: the shorthand people actually type, the
# older official name, and the Indonesian name — this crawler is run from an
# Indonesian desk, so `--geo jerman` should not be a typo.
ALIASES = {
    # English shorthand, former names, spellings without the accent
    "uk": "gb", "britain": "gb", "great britain": "gb", "england": "gb",
    "scotland": "gb", "wales": "gb",
    "usa": "us", "u.s.": "us", "u.s.a.": "us", "america": "us",
    "united states of america": "us",
    "uae": "ae", "emirates": "ae",
    "korea": "kr", "south korea": "kr", "republic of korea": "kr",
    "north korea": "kp", "dprk": "kp",
    "russian federation": "ru", "czech republic": "cz", "holland": "nl",
    "burma": "mm", "swaziland": "sz", "macedonia": "mk", "cape verde": "cv",
    "ivory coast": "ci", "cote divoire": "ci", "east timor": "tl",
    "turkey": "tr", "vatican": "va", "macau": "mo", "hong kong sar": "hk",
    "drc": "cd", "dr congo": "cd", "democratic republic of the congo": "cd",
    "republic of the congo": "cg", "brunei darussalam": "bn",
    "viet nam": "vn", "syrian arab republic": "sy", "state of palestine": "ps",
    "curacao": "cw", "reunion": "re", "aland": "ax",
    # Indonesian names
    "amerika": "us", "amerika serikat": "us", "inggris": "gb",
    "jerman": "de", "belanda": "nl", "perancis": "fr", "prancis": "fr",
    "spanyol": "es", "italia": "it", "yunani": "gr", "turki": "tr",
    "rusia": "ru", "swedia": "se", "norwegia": "no", "finlandia": "fi",
    "swiss": "ch", "belgia": "be", "polandia": "pl", "irlandia": "ie",
    "hongaria": "hu", "ceko": "cz", "ukraina": "ua", "rumania": "ro",
    "portugis": "pt", "denmark": "dk",
    "jepang": "jp", "tiongkok": "cn", "cina": "cn", "korea selatan": "kr",
    "korea utara": "kp", "singapura": "sg", "filipina": "ph", "kamboja": "kh",
    "timor leste": "tl", "birma": "mm", "papua nugini": "pg",
    "selandia baru": "nz", "kanada": "ca", "meksiko": "mx", "brasil": "br",
    "brazil": "br", "afrika selatan": "za", "arab saudi": "sa",
    "uni emirat arab": "ae", "emirat arab": "ae", "mesir": "eg",
    "maroko": "ma", "aljazair": "dz", "yordania": "jo", "suriah": "sy",
    "irak": "iq", "yaman": "ye", "srilanka": "lk", "etiopia": "et",
}

# The interface language a country's results read best in. Only used where an
# engine wants a language alongside the country (Google News RSS `ceid`);
# anything not listed falls back to English, which every engine accepts.
LANGUAGES = {
    "id": "id", "my": "ms", "bn": "ms", "sg": "en", "th": "th", "vn": "vi",
    "ph": "en", "kh": "km", "la": "lo", "mm": "my", "tl": "pt",
    "jp": "ja", "kr": "ko", "kp": "ko", "cn": "zh-CN", "tw": "zh-TW",
    "hk": "zh-HK", "mo": "zh-TW", "bd": "bn", "lk": "si", "np": "ne",
    "de": "de", "at": "de", "ch": "de", "li": "de",
    "fr": "fr", "be": "fr", "lu": "fr", "mc": "fr", "sn": "fr", "ci": "fr",
    "es": "es", "mx": "es", "ar": "es", "cl": "es", "co": "es", "pe": "es",
    "ve": "es", "ec": "es", "bo": "es", "py": "es", "uy": "es", "cr": "es",
    "pa": "es", "gt": "es", "hn": "es", "ni": "es", "sv": "es", "do": "es",
    "cu": "es", "pr": "es",
    "pt": "pt", "br": "pt", "ao": "pt", "mz": "pt",
    "it": "it", "va": "it", "sm": "it",
    "nl": "nl", "sr": "nl", "ru": "ru", "by": "ru", "kz": "ru", "ua": "uk",
    "pl": "pl", "cz": "cs", "sk": "sk", "hu": "hu", "ro": "ro", "bg": "bg",
    "gr": "el", "cy": "el", "tr": "tr", "se": "sv", "no": "no", "dk": "da",
    "fi": "fi", "is": "is", "ee": "et", "lv": "lv", "lt": "lt", "hr": "hr",
    "rs": "sr", "si": "sl", "ba": "bs", "mk": "mk", "al": "sq", "me": "sr",
    "il": "he", "ir": "fa", "af": "fa",
    "sa": "ar", "ae": "ar", "eg": "ar", "qa": "ar", "kw": "ar", "bh": "ar",
    "om": "ar", "jo": "ar", "lb": "ar", "iq": "ar", "ye": "ar", "sy": "ar",
    "ma": "ar", "dz": "ar", "tn": "ar", "ly": "ar", "sd": "ar",
}

DEFAULT_LANGUAGE = "en"


@dataclass(frozen=True)
class Geo:
    """One resolved country, in the shape the engines ask for it."""

    code: str       # lowercase alpha-2, e.g. "my" — what goes in gl= / cc=
    name: str       # "Malaysia", for the run banner and error messages
    language: str   # best-guess interface language, e.g. "ms"

    @property
    def upper(self) -> str:
        """Uppercase alpha-2, for the parameters that insist on it."""
        return self.code.upper()

    @property
    def base_language(self) -> str:
        """The language without its region tail — `zh-CN` -> `zh`.

        A few languages are only ever written with a region (Chinese), and
        pasting one straight into a `<lang>-<COUNTRY>` slot would produce
        `zh-CN-CN`. Splitting first keeps every market tag two parts long.
        """
        return self.language.split("-")[0]

    @property
    def market(self) -> str:
        """Bing's market tag — `ms-MY`, `id-ID`, `zh-CN`."""
        return f"{self.base_language}-{self.upper}"

    @property
    def ceid(self) -> str:
        """Google News' edition tag — `MY:ms`, `ID:id`, `CN:zh-CN`."""
        return f"{self.upper}:{self.language}"

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"


def normalise(value: str) -> str:
    """Fold a typed country to the form the tables are keyed by."""
    return " ".join(value.strip().lower().replace("_", " ").replace("-", " ").split())


def suggest(value: str, limit: int = 3) -> list:
    """Names close to what was typed, so a wrong --geo can say what was meant."""
    spelled = {name.lower(): name for name in list(COUNTRIES.values()) + list(ALIASES)}
    matches = difflib.get_close_matches(normalise(value), list(spelled), n=limit, cutoff=0.6)
    return [spelled[m] for m in matches]


def resolve(value: str) -> Geo:
    """Turn `my` / `malaysia` / `Malaysia` into a Geo. Raises ValueError otherwise.

    Codes are checked before names, so the two-letter form everybody types is
    the fast path. That order matters for real countries too: `is` is Iceland's
    code, not a word, and looking the codes up first keeps it that way.
    """
    key = normalise(value)
    if not key:
        raise ValueError("--geo needs a country, e.g. --geo my or --geo malaysia")

    code = None
    if key in COUNTRIES:
        code = key
    elif key in ALIASES:
        code = ALIASES[key]
    else:
        for candidate, name in COUNTRIES.items():
            if name.lower() == key:
                code = candidate
                break

    if code is None:
        message = (f"unknown country '{value}' — pass an ISO country code (my) "
                   f"or a country name (malaysia)")
        near = suggest(value)
        if near:
            message += f". Did you mean: {', '.join(near)}?"
        raise ValueError(message)

    return Geo(code=code, name=COUNTRIES[code],
               language=LANGUAGES.get(code, DEFAULT_LANGUAGE))

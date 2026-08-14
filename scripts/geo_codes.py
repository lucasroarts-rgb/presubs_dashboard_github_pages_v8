"""E.164 calling-code -> country lookup, used to bucket CRM leads by country
from a phone number prefix without ever storing or exposing the full number.

Only ever fed a short prefix (first 4-5 characters of a phone number) -
callers must not pass full phone numbers into anything that gets persisted.
"""

from __future__ import annotations

CALLING_CODES: dict[str, str] = {
    # 3-digit codes (checked first)
    "212": "Morocco", "213": "Algeria", "216": "Tunisia", "220": "Gambia",
    "221": "Senegal", "222": "Mauritania", "223": "Mali", "224": "Guinea",
    "225": "Ivory Coast", "226": "Burkina Faso", "227": "Niger", "228": "Togo",
    "229": "Benin", "230": "Mauritius", "231": "Liberia", "232": "Sierra Leone",
    "233": "Ghana", "234": "Nigeria", "235": "Chad", "236": "Central African Republic",
    "237": "Cameroon", "238": "Cape Verde", "241": "Gabon", "242": "Congo-Brazzaville",
    "243": "DR Congo", "244": "Angola", "248": "Seychelles", "250": "Rwanda",
    "251": "Ethiopia", "253": "Djibouti", "254": "Kenya", "255": "Tanzania",
    "257": "Burundi", "261": "Madagascar", "262": "Reunion / Mayotte",
    "263": "Zimbabwe", "264": "Namibia", "265": "Malawi", "267": "Botswana",
    "268": "Eswatini", "269": "Comoros", "290": "Saint Helena",
    "297": "Aruba", "298": "Faroe Islands", "299": "Greenland",
    "350": "Gibraltar", "351": "Portugal", "352": "Luxembourg", "353": "Ireland",
    "354": "Iceland", "355": "Albania", "356": "Malta", "357": "Cyprus",
    "358": "Finland", "359": "Bulgaria", "370": "Lithuania", "371": "Latvia",
    "372": "Estonia", "373": "Moldova", "374": "Armenia", "375": "Belarus",
    "376": "Andorra", "377": "Monaco", "378": "San Marino", "380": "Ukraine",
    "381": "Serbia", "382": "Montenegro", "385": "Croatia", "386": "Slovenia",
    "387": "Bosnia and Herzegovina", "389": "North Macedonia", "420": "Czechia",
    "421": "Slovakia", "423": "Liechtenstein", "500": "Falkland Islands",
    "501": "Belize", "502": "Guatemala", "503": "El Salvador", "504": "Honduras",
    "505": "Nicaragua", "506": "Costa Rica", "507": "Panama", "509": "Haiti",
    "590": "Guadeloupe", "591": "Bolivia", "592": "Guyana", "593": "Ecuador",
    "594": "French Guiana", "595": "Paraguay", "596": "Martinique",
    "597": "Suriname", "598": "Uruguay", "670": "East Timor", "672": "Norfolk Island",
    "673": "Brunei", "674": "Nauru", "675": "Papua New Guinea", "676": "Tonga",
    "677": "Solomon Islands", "678": "Vanuatu", "679": "Fiji", "685": "Samoa",
    "686": "Kiribati", "687": "New Caledonia", "689": "French Polynesia",
    "850": "North Korea", "852": "Hong Kong", "853": "Macau", "855": "Cambodia",
    "856": "Laos", "870": "Pitcairn", "880": "Bangladesh", "886": "Taiwan",
    "960": "Maldives", "961": "Lebanon", "962": "Jordan", "963": "Syria",
    "964": "Iraq", "965": "Kuwait", "966": "Saudi Arabia", "967": "Yemen",
    "968": "Oman", "970": "Palestine", "971": "United Arab Emirates",
    "972": "Israel", "973": "Bahrain", "974": "Qatar", "975": "Bhutan",
    "976": "Mongolia", "977": "Nepal", "992": "Tajikistan", "993": "Turkmenistan",
    "994": "Azerbaijan", "995": "Georgia", "996": "Kyrgyzstan", "998": "Uzbekistan",
    # 2-digit codes
    "20": "Egypt", "27": "South Africa", "30": "Greece", "31": "Netherlands",
    "32": "Belgium", "33": "France", "34": "Spain", "36": "Hungary",
    "39": "Italy", "40": "Romania", "41": "Switzerland", "43": "Austria",
    "44": "United Kingdom", "45": "Denmark", "46": "Sweden", "47": "Norway",
    "48": "Poland", "49": "Germany", "51": "Peru", "52": "Mexico",
    "53": "Cuba", "54": "Argentina", "55": "Brazil", "56": "Chile",
    "57": "Colombia", "58": "Venezuela", "60": "Malaysia", "61": "Australia",
    "62": "Indonesia", "63": "Philippines", "64": "New Zealand", "65": "Singapore",
    "66": "Thailand", "81": "Japan", "82": "South Korea", "84": "Vietnam",
    "86": "China", "90": "Turkey", "91": "India", "92": "Pakistan",
    "93": "Afghanistan", "94": "Sri Lanka", "95": "Myanmar", "98": "Iran",
    # 1-digit codes
    "1": "USA / Canada", "7": "Russia / Kazakhstan",
}

_SORTED_CODES = sorted(CALLING_CODES, key=len, reverse=True)


def resolve_country(phone_prefix: str | None) -> str:
    """Match a phone-number prefix (e.g. '+336...') to a country name.

    Only needs the first few characters of the number - never pass a full
    phone number into code that persists or logs its return value alongside
    the number itself.
    """
    if not phone_prefix:
        return "Unknown"
    digits = phone_prefix.lstrip("+").strip()
    if not digits:
        return "Unknown"
    for code in _SORTED_CODES:
        if digits.startswith(code):
            return CALLING_CODES[code]
    return "Other"

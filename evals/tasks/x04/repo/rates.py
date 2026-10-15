"""State tax rates by two-letter code (codes are lowercase)."""

RATES = {
    "al": 0.040,
    "ak": 0.000,
    "az": 0.056,
    "ar": 0.065,
    "ca": 0.072,
    "co": 0.029,
    "ct": 0.063,
    "de": 0.000,
    "fl": 0.060,
    "ga": 0.040,
    "hi": 0.040,
    "id": 0.060,
    "il": 0.062,
    "in": 0.070,
    "ia": 0.060,
    "ks": 0.065,
    "ky": 0.060,
    "la": 0.044,
    "me": 0.055,
    "md": 0.060,
    "ma": 0.062,
    "mi": 0.060,
    "mn": 0.068,
    "ms": 0.070,
    "mo": 0.042,
    "mt": 0.000,
    "ne": 0.055,
    "nv": 0.068,
    "nh": 0.000,
    "nj": 0.066,
    "nm": 0.051,
    "ny": 0.040,
    "nc": 0.047,
    "nd": 0.050,
    "oh": 0.057,
    "ok": 0.045,
    "or": 0.000,
    "pa": 0.060,
    "ri": 0.070,
    "sc": 0.060,
    "sd": 0.042,
    "tn": 0.070,
    "tx": 0.062,
    "ut": 0.061,
    "vt": 0.060,
    "va": 0.053,
    "wa": 0.065,
    "wv": 0.060,
    "wi": 0.050,
    "wy": 0.040,
    "dc": 0.060,
    "pr": 0.115,
    "gu": 0.040,
    "vi": 0.050,
    "as": 0.040,
    "mp": 0.040,
    "fm": 0.040,
    "mh": 0.040,
    "pw": 0.040,
    "zz": 0.000,
}


def rate_for(code):
    """Return the rate for a state code (any case), or 0.0 if unknown."""
    return RATES.get(code, 0.0)


def with_tax(amount, code):
    """Add tax to amount for the given state code."""
    return amount * (1 + rate_for(code))

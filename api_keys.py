from typing import Mapping

# the allowed keys are a dict of strings, mapping keys to project names. These names are used in the stats message which
# is send regularly, at least in the first days of this API. I use the 4 word "sentences" as below because they are
# funny, but you can do whatever you want. This implementations means a restart of the service is necessary to add a
# new key, but that's not an issue for now
ALLOWED_KEYS: Mapping[str, str] = {"RationalGymsGripOverseas": "VeryCoolProject"}
# these are taken from my.telegram.org, you have to get your own
api_id: int = 1234
api_hash: str = "Wuhu"

from typing import Dict, Any, List
from constants import OPTION_ALIASES

def canonical_option_name(name: str) -> str:
    lname = name.lower()
    for canonical, aliases in OPTION_ALIASES.items():
        if lname in aliases:
            return canonical
    return name.title()

def normalize_options(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    option_map = {}

    for v in raw.get("variants", []):
        for opt in v.get("options", []):
            cname = canonical_option_name(opt["name"])
            option_map.setdefault(cname, set()).add(opt["value"])

    return [
        {"name": name, "values": sorted(values)}
        for name, values in option_map.items()
    ]

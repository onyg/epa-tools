import json
import copy


def deep_merge(base, overlay):
    """Rekursives Merging von zwei verschachtelten Dictionaries"""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        elif key in result and isinstance(result[key], list) and isinstance(value, list):
            result[key] = merge_lists(result[key], value)
        else:
            result[key] = value
    return result

def merge_lists(base_list, overlay_list):
    """Einfache Strategie: Anhängen ohne Duplikaterkennung"""
    return base_list + [item for item in overlay_list if item not in base_list]

# Beispiel-Pfade (kannst du ersetzen)
base_file = "./data/CapabilityStatement-epa-basic-server.json"
overlay_file = "./data/CapabilityStatement-epa-medication-service-server.json"
output_file = "./data/CapabilityStatement-epa-medication-service-server-merged.json"
# overlay_file = "./data/CapabilityStatement-epa-audit-event-server.json"
# output_file = "./data/CapabilityStatement-epa-audit-event-server-merged.json"



# Dateien einlesen
with open(base_file, "r", encoding="utf-8") as f:
    base_cs = json.load(f)

with open(overlay_file, "r", encoding="utf-8") as f:
    overlay_cs = json.load(f)

# Merging durchführen
merged_cs = deep_merge(base_cs, overlay_cs)

# Ergebnis speichern
with open(output_file, "w", encoding="utf-8") as f:
    json.dump(merged_cs, f, indent=2, ensure_ascii=False)

print(f"Merged CapabilityStatement saved to {output_file}")

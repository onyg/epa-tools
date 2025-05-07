import os
import copy
import json
import yaml
from epatools.common import BaseConfig, FHIRArtifactLoader, DEFAULT_DEPENDENCIES_CONFIG


class MergerConfig(BaseConfig):

    def __init__(self, config):
        super().__init__(config)
        self.config_file = config
        self.path_resources = "fsh-generated/resources"
        self.overlay_resources = []

    def from_dict(self, data):
        if 'merger' in data:
            params = data.get('merger')
            self.path_resources = params.get('path-resource', self.path_resources)
            self.overlay_resources = params.get('resource', [])



class Merger(object):

    def __init__(self, config_file):
        self.config = MergerConfig(config=config_file)
        self.extra_merged_file = False
        self.dependencies_config = DEFAULT_DEPENDENCIES_CONFIG

    def load(self):
        self.config.load()
        return self

    def deep_merge(self, base, overlay):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            # Special handling for the "rest" element based on mode ("server", "client")
            if key == "rest":
                result[key] = self.merge_rest(result.get(key, []), value)
            elif key in result and isinstance(result[key], dict) and isinstance(value, dict):
                # Recursively merge nested dictionaries
                result[key] = self.deep_merge(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                # Merge lists by appending non-duplicate items
                result[key] = self.merge_lists(result[key], value)
            else:
                # Override primitive values or add new keys
                result[key] = value
        return result

    def merge_rest(self, base_rest, overlay_rest):
        mode_map = {}
        # Index base_rest entries by their "mode" (e.g., "server", "client")
        for entry in base_rest:
            mode = entry.get("mode")
            if mode:
                mode_map[mode] = copy.deepcopy(entry)
        # Merge overlay_rest entries by "mode"
        for entry in overlay_rest:
            mode = entry.get("mode")
            if mode in mode_map:
                # If the same mode exists, deep merge their contents
                merged_entry = self.deep_merge(mode_map[mode], entry)
                mode_map[mode] = merged_entry
            else:
                # If it's a new mode, simply add it
                mode_map[mode] = copy.deepcopy(entry)
        return list(mode_map.values())

    def merge_lists(self, base_list, overlay_list):
        return base_list + [item for item in overlay_list if item not in base_list]

    def merge(self):
        for overlay_resource in self.config.overlay_resources:
            merged = False
            artifact, filename = FHIRArtifactLoader.load_artifact(path=self.config.path_resources, resource=overlay_resource)
            if artifact:
                for canonical_url in artifact.get("imports", []):
                    base_artifact, _ = FHIRArtifactLoader.load_capabilitystatement_by_canonical(package_path=self.config.path_resources, canonical_url=canonical_url)
                    if base_artifact is None:
                        base_artifact, _ = FHIRArtifactLoader.load_capability_from_dependencies(dependencies_config_path=self.dependencies_config, canonical_url=canonical_url)                    
                    if base_artifact:
                        artifact = self.deep_merge(base=base_artifact, overlay=artifact)
                        merged = True
                if merged:
                    if self.extra_merged_file:
                        name, ext = filename.split('.json')
                        filename = name + "-merged.json"
                    output = os.path.join(self.config.path_resources, filename)
                    with open(output, "w", encoding="utf-8") as f:
                        json.dump(artifact, f, indent=2, ensure_ascii=False)
                    print(f"✅  Merged CapabilityStatement saved to {output}")


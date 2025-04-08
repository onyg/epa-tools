import os
import copy
import json
import yaml
from epatools.common import BaseConfig, FHIRArtifactLoader


class MergerConfig(BaseConfig):

    def __init__(self, config):
        super().__init__(config)
        self.config_file = config
        self.path_resources = "fsh-generated/resources"
        self.version = "current"
        self.package = None
        self.base_resource = None
        self.overlay_resources = []

    def from_dict(self, data):
        if 'merger' in data:
            params = data.get('merger')
            self.path_resources = params.get('path-resource', self.path_resources)
            self.version = params.get('base', {}).get('version', self.version)
            self.package = params.get('base', {}).get('package', None)
            self.base_resource = params.get('base', {}).get('resource', None)
            self.overlay_resources = params.get('resource', [])



class Merger(object):

    def __init__(self, config_file):
        self.config = MergerConfig(config=config_file)
        self.extra_merged_file = False

    def load(self):
        self.config.load()
        return self

    def deep_merge(self, base, overlay):
        result = copy.deepcopy(base)
        for key, value in overlay.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self.deep_merge(result[key], value)
            elif key in result and isinstance(result[key], list) and isinstance(value, list):
                result[key] = self.merge_lists(result[key], value)
            else:
                result[key] = value
        return result

    def merge_lists(self, base_list, overlay_list):
        return base_list + [item for item in overlay_list if item not in base_list]

    def merge(self):
        base_artifact = None
        if self.config.version == "current":
            try:
                _base_resource = os.path.join(self.config.path_resources, self.config.base_resource)
                base_artifact, base_filename = FHIRArtifactLoader.load_artifact(self.config.path_resources, self.config.base_resource)
            except TypeError:
                return
        elif self.config.version is not None:
            try:
                base_artifact, base_filename = FHIRArtifactLoader.load_package_artifact(package=self.config.package, 
                                                                                        version=self.config.version, 
                                                                                        resource=self.config.base_resource)
            except TypeError:
                return
        if base_artifact is None:
            return
        for overlay_resource in self.config.overlay_resources:
            artifact, filename = FHIRArtifactLoader.load_artifact(path=self.config.path_resources, resource=overlay_resource)
            if artifact:
                merged_artifact = self.deep_merge(base=base_artifact, overlay=artifact)
                if self.extra_merged_file:
                    name, ext = filename.split('.json')
                    filename = name + "-merged.json"
                output = os.path.join(self.config.path_resources, filename)
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(merged_artifact, f, indent=2, ensure_ascii=False)
                print(f"✅  Merged CapabilityStatement saved to {output}")


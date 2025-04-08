import os
import copy
import json
import yaml

FHIR_FOLDERS = [
    os.path.join(os.path.expanduser("~"), ".fhir", "packages"),
    os.path.join(os.getcwd(), ".fhir", "packages"),
    os.path.join(os.getcwd(), "dependencies")
]

class MergerConfig(object):

    def __init__(self, config):
        self.config_file = config
        self.path_resources = "fsh-generated/resources"
        self.version = "current"
        self.package = None
        self.base_resource = None
        self.overlay_resources = []

    def load(self):
        # config_filepath = os.path.join(self.path, CONFIG_FILE)
        if not os.path.exists(self.config_file):
            raise ConfigPathNotExists(f"The config filepath {self.config_file} does not exists")
        with open(self.config_file, 'r', encoding='utf-8') as file:
            _data = yaml.safe_load(file)
            self.from_dict(data=_data)

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

    def load(self):
        self.config.load()
        return self

    def deep_merge(self, base, overlay):
        """Rekursives Merging von zwei verschachtelten Dictionaries"""
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
        """Einfache Strategie: Anhängen ohne Duplikaterkennung"""
        return base_list + [item for item in overlay_list if item not in base_list]


    def _generate_possible_filenames(self, resource):
        resource_type, resource_id = resource.split('/')
        return [
            f"{resource_type}-{resource_id}.json",
            f"{resource_id}.{resource_type}.json",
            os.path.join(resource_type, f"{resource_id}.json"),
            os.path.join('examples', f"{resource_type}-{resource_id}.json"),
            os.path.join('examples', f"{resource_id}.{resource_type}.json")
        ]

    def load_artifact(self, path, resource):
        for filename in self._generate_possible_filenames(resource):
            resource_path = os.path.join(path, filename)
            if os.path.exists(resource_path):
                with open(resource_path, "r", encoding="utf-8") as f:
                    artifact = json.load(f)
                return artifact, filename
        return None, None

    def load_package_artifact(self, package, version, resource):
        for fhir_path in FHIR_FOLDERS:
            package_path = os.path.join(fhir_path, f"{package}#{version}", "package")
            if os.path.exists(package_path):
                artifact, filename = self.load_artifact(package_path, resource)
                if artifact:
                    return artifact, filename
        return None, None


    def merge(self):
        base_artifact = None
        if self.config.version == "current":
            try:
                _base_resource = os.path.join(self.config.path_resources, self.config.base_resource)
                base_artifact, base_filename = self.load_artifact(self.config.path_resources, self.config.base_resource)
            except TypeError:
                return
        elif self.config.version is not None:
            try:
                base_artifact, base_filename = self.load_package_artifact(package=self.config.package, 
                                                                          version=self.config.version, 
                                                                          resource=self.config.base_resource)
            except TypeError:
                return
        if base_artifact is None:
            return
        for overlay_resource in self.config.overlay_resources:
            artifact, filename = self.load_artifact(path=self.config.path_resources, resource=overlay_resource)
            if artifact:
                merged_artifact = self.deep_merge(base=base_artifact, overlay=artifact)
                name, ext = filename.split('.json')
                output_file = name + "-merged.json"
                output = os.path.join(self.config.path_resources, output_file)
                with open(output, "w", encoding="utf-8") as f:
                    json.dump(merged_artifact, f, indent=2, ensure_ascii=False)
                print(f"✅  Merged CapabilityStatement saved to {output}")


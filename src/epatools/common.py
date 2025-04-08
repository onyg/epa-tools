import os
import sys
import yaml
import json

FHIR_FOLDERS = [
    os.path.join(os.path.expanduser("~"), ".fhir", "packages"),
    os.path.join(os.getcwd(), ".fhir", "packages"),
    os.path.join(os.getcwd(), "dependencies")
]


class BaseConfig(object):

    def __init__(self, config):
        self.config_file = config


    def load(self):
        if not os.path.exists(self.config_file):
            raise Exception(f"The config filepath {self.config_file} does not exists")
        with open(self.config_file, 'r', encoding='utf-8') as file:
            _data = yaml.safe_load(file)
            self.from_dict(data=_data)

    def from_dict(self, data):
        pass


class FHIRArtifactLoader(object):

    @classmethod
    def fhir_folder(cls):
        return FHIR_FOLDERS

    @classmethod
    def generate_possible_filenames(cls, resource):
        resource_type, resource_id = resource.split('/')
        return [
            f"{resource_type}-{resource_id}.json",
            f"{resource_id}.{resource_type}.json",
            os.path.join(resource_type, f"{resource_id}.json"),
            os.path.join('examples', f"{resource_type}-{resource_id}.json"),
            os.path.join('examples', f"{resource_id}.{resource_type}.json")
        ]

    @classmethod
    def load_artifact(cls, path, resource):
        for filename in cls.generate_possible_filenames(resource):
            resource_path = os.path.join(path, filename)
            if os.path.exists(resource_path):
                with open(resource_path, "r", encoding="utf-8") as f:
                    artifact = json.load(f)
                return artifact, filename
        return None, None

    @classmethod
    def load_package_artifact(cls, package, version, resource):
        for fhir_path in FHIR_FOLDERS:
            package_path = os.path.join(fhir_path, f"{package}#{version}", "package")
            if os.path.exists(package_path):
                artifact, filename = cls.load_artifact(package_path, resource)
                if artifact:
                    return artifact, filename
        return None, None
import os
import sys
import yaml
import json

FHIR_FOLDERS = [
    os.path.join(os.path.expanduser("~"), ".fhir", "packages"),
    os.path.join(os.getcwd(), ".fhir", "packages"),
    os.path.join(os.getcwd(), "dependencies")
]

FHIR_CACHE_DIR = os.path.expanduser("~/.fhir/packages")

DEFAULT_CONFIG = 'epatools.yaml'
DEFAULT_DEPENDENCIES_CONFIG = 'sushi-config.yaml'


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

    @classmethod
    def resolve_package_path(cls, package_name: str, version: str) -> str:
        path = os.path.join(FHIR_CACHE_DIR, package_name, version, "package")
        if not os.path.isdir(path):
            raise FileNotFoundError(f"Package not found: {path}")
        return path

    @classmethod
    def load_capabilitystatement_by_canonical(cls, package_path: str, canonical_url: str):
        for root, _, filenames in os.walk(package_path):
            for filename in filenames:
                if filename.endswith(".json"):
                    with open(os.path.join(root, filename), encoding="utf-8") as f:
                        try:
                            artifact = json.load(f)
                            if artifact.get("resourceType") == "CapabilityStatement":
                                if artifact.get("url") == canonical_url:
                                    return artifact, filename
                        except Exception as e:
                            raise Exception(f"Fehler beim Laden von {filename}: {e}")

        return None, None

    @classmethod
    def load_capability_from_dependencies(cls, dependencies_config_path, canonical_url):
        with open(dependencies_config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        dependencies = config.get("dependencies", {})

        for package_name, version in dependencies.items():
            try:
                print(f"🔍 Prüfe Paket: {package_name}@{version}")
                pkg_path = resolve_package_path(package_name, version)
                cap, filename = load_capabilitystatement_by_canonical(pkg_path, canonical_url)
                if cap:
                    print(f"✅ Gefunden in {package_name}: {filename}")
                    return cap, filename
            except FileNotFoundError as e:
                print(f"⚠️  {e}")
            except Exception as e:
                print(f"❌ Fehler beim Laden von {package_name}: {e}")

        print("❌ Kein passendes CapabilityStatement gefunden.")
        return None, None

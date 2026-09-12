import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from epatools import oaconverter as oa

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/openapi_legacy.json"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def legacy_output(module, filename, operations, enhanced):
    config = module.OpenAPIConfig(None)
    config.with_metadata = enhanced
    config.with_format_parameter = enhanced
    config.with_accept_header = enhanced
    conversion = module.ConvertConfig()
    conversion.search_with_post = enhanced
    with patch.object(module, "load_operation_definitions_from_same_folder", return_value=operations):
        return module.capabilitystatement_to_openapi(
            str(ROOT / "data"), filename.removesuffix(".json").replace("CapabilityStatement-", "CapabilityStatement/", 1),
            config, conversion,
        )


def extension(url, code):
    return {"url": url, "valueCode": code}


class ConverterTests(unittest.TestCase):
    def setUp(self):
        self.config = oa.OpenAPIConfig(None)
        self.silent = contextlib.redirect_stdout(io.StringIO())
        self.silent.__enter__()
        self.addCleanup(self.silent.__exit__, None, None, None)

    def test_existing_artifacts_match_original_converter(self):
        fixture = json.loads(FIXTURE.read_text())
        operations = [json.loads((ROOT / name).read_text()) for name in fixture["operations"]]
        for filename, expected in fixture["outputs"].items():
            for enhanced in (False, True):
                with self.subTest(filename=filename, enhanced=enhanced):
                    self.assertEqual(digest(legacy_output(oa, filename, operations, enhanced)), expected[str(enhanced)])

    def interaction(self, code, parameters):
        paths = oa.interaction_to_paths(
            self.config, "Task", code, parameters, [], [], {}, fhir_formats=["application/fhir+json"])
        return next(iter(next(iter(paths.values())).values()))

    def search(self, name="ac", codes=None):
        result = {"name": name, "type": "token", "documentation": "Zugriffscode",
                  "definition": "https://example.org/SearchParameter/ac",
                  "extension": [extension("http://hl7.org/fhir/StructureDefinition/capabilitystatement-expectation", "SHALL")]}
        if codes is not None:
            result["extension"] += [extension(oa.SEARCH_PARAMETER_INTERACTION_EXTENSION, code) for code in codes]
        return result

    def test_explicit_interactions_only(self):
        for targets in (["read"], ["read", "patch"], ["read", "search-type"], ["read", "read"]):
            parameters = [self.search(codes=targets), self.search("status")]
            original = copy.deepcopy(parameters)
            for code in sorted(oa.RESOURCE_INTERACTIONS) + ["search-type-post", "conditional_update"]:
                with self.subTest(targets=targets, code=code):
                    output = self.interaction(code, parameters)
                    names = [p["name"] for p in output["parameters"] if p["in"] == "query"]
                    target = "search-type" if code == "search-type-post" else code
                    self.assertEqual(names.count("ac"), int(target in targets))
                    self.assertEqual("status" in names, code in ("search-type", "search-type-post", "conditional_update"))
            self.assertEqual(parameters, original)

    def test_legacy_search_metadata_and_pagination(self):
        params = [self.search(name) for name in ("status", "_sort", "_count", "_offset")]
        output = self.interaction("search-type", params)
        for parameter in params:
            rendered = next(p for p in output["parameters"] if p["name"] == parameter["name"])
            self.assertEqual(rendered, oa.query_parameter(parameter))
            self.assertFalse(rendered["required"])
        self.assertNotIn("status", [p["name"] for p in self.interaction("read", params)["parameters"]])

    def test_explicit_pagination_does_not_leak(self):
        params = [self.search("_count", ["read"])]
        self.assertNotIn("_count", [p["name"] for p in self.interaction("search-type", params)["parameters"]])
        self.assertEqual([p["name"] for p in self.interaction("read", params)["parameters"]].count("_count"), 1)

    def operation(self, params, method="POST"):
        definition = {"url": "https://example.org/op", "code": "close", "system": True,
                      "type": True, "instance": True, "resource": ["Task"], "parameter": params,
                      "extension": [extension("https://gematik.de/fhir/ti/StructureDefinition/extension-http-method", method)]}
        capability = {"rest": [{"operation": [{"name": "close", "definition": definition["url"]}]}]}
        result = oa.add_operations_from_capabilitystatement(
            self.config, {"paths": {}}, capability, [definition], ["application/fhir+json"], [], {})
        return result["paths"]

    def test_query_inputs_and_unchanged_outputs(self):
        for minimum in (0, 1):
            for name in ("secret", "resource"):
                parameter = {"name": name, "use": "in", "min": minimum, "max": "1", "type": "date",
                             "documentation": "Secret", "extension": [
                                 extension("https://example.org/unrelated", "body"),
                                 extension(oa.OPERATION_PARAMETER_LOCATION_EXTENSION, "query")]}
                output_param = {"name": "return", "use": "out", "type": "Bundle",
                                "extension": [extension(oa.OPERATION_PARAMETER_LOCATION_EXTENSION, "unsupported")]}
                for path, methods in self.operation([parameter, output_param]).items():
                    with self.subTest(minimum=minimum, name=name, path=path):
                        output = methods["post"]
                        query = next(p for p in output["parameters"] if p["name"] == name)
                        self.assertEqual(query, oa.query_parameter(parameter, minimum > 0))
                        self.assertNotIn("requestBody", output)
                        self.assertNotIn("return", [p["name"] for p in output["parameters"]])

    def test_mixed_body_and_query(self):
        body = {"name": "payload", "use": "in", "min": 1, "type": "Parameters"}
        query = {"name": "secret", "use": "in", "min": 0, "type": "string",
                 "extension": [extension(oa.OPERATION_PARAMETER_LOCATION_EXTENSION, "query")]}
        old = self.operation([body])["/$close"]["post"]
        new = self.operation([body, query])["/$close"]["post"]
        self.assertEqual(new["requestBody"], old["requestBody"])
        self.assertNotIn("secret", json.dumps(new["requestBody"]))
        self.assertEqual(new["responses"], old["responses"])

    def test_get_query_is_not_duplicated(self):
        parameter = {"name": "secret", "use": "in", "type": "string",
                     "extension": [extension(oa.OPERATION_PARAMETER_LOCATION_EXTENSION, "query")]}
        result = self.operation([parameter], "GET")["/$close"]["get"]
        self.assertEqual([p["name"] for p in result["parameters"]], ["secret"])

    def test_full_canonical_urls_only(self):
        parameter = self.search(codes=None)
        parameter["extension"].append(extension("search-parameter-interaction", "read"))
        self.assertNotIn("ac", [p["name"] for p in self.interaction("read", [parameter])["parameters"]])
        self.assertIn("ac", [p["name"] for p in self.interaction("search-type", [parameter])["parameters"]])
        input_param = {"name": "secret", "use": "in", "extension": [
            extension("operation-parameter-location", "query")]}
        self.assertIn("requestBody", self.operation([input_param])["/$close"]["post"])

    def test_extension_does_not_create_interactions(self):
        capability = {"format": ["application/fhir+json"], "rest": [{"resource": [{
            "type": "Task", "interaction": [{"code": "search-type"}],
            "searchParam": [self.search(codes=["read"])]
        }]}]}
        with patch.object(oa.FHIRArtifactLoader, "load_artifact", return_value=(capability, "")), \
                patch.object(oa, "load_operation_definitions_from_same_folder", return_value=[]):
            output = oa.capabilitystatement_to_openapi("", "", self.config, oa.ConvertConfig())
        self.assertEqual(list(output["paths"]), ["/Task"])
        self.assertNotIn("ac", [p["name"] for p in output["paths"]["/Task"]["get"]["parameters"]])

    def test_unextended_operation_keeps_generic_body(self):
        parameter = {"name": "secret", "use": "in", "min": 1, "type": "string"}
        output = self.operation([parameter])["/$close"]["post"]
        self.assertEqual(output["parameters"], [])
        self.assertEqual(output["requestBody"], {
            "required": True,
            "content": {"application/fhir+json": {"schema": {"type": "object"}}}
        })

    def test_unsupported_extensions_raise(self):
        for value in ("unknown", None):
            with self.assertRaises(ValueError):
                self.interaction("read", [self.search(codes=[value])])
            with self.assertRaises(ValueError):
                self.operation([{"name": "secret", "use": "in", "extension": [
                    extension(oa.OPERATION_PARAMETER_LOCATION_EXTENSION, value)]}])


if __name__ == "__main__":
    unittest.main()

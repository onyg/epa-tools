"""Integration coverage for combined capability and operation extensions."""
import contextlib
import copy
import io
import unittest
from unittest.mock import patch

from epatools import oaconverter as oa
from test_conditional_interactions import BASE, http, search


class OpenAPIIntegrationTests(unittest.TestCase):
    def convert(self, resources, *, operations=None, enhanced=False):
        capability = {
            "implementation": {"url": "https://example.org/fhir/v1"},
            "format": ["application/fhir+json", "application/fhir+xml"],
            "rest": [{"resource": resources}],
        }
        original = copy.deepcopy(capability)
        config = oa.OpenAPIConfig(None)
        config.with_format_parameter = enhanced
        conversion = oa.ConvertConfig()
        conversion.search_with_post = enhanced
        with contextlib.redirect_stdout(io.StringIO()), \
                patch.object(oa.FHIRArtifactLoader, "load_artifact", return_value=(capability, "")), \
                patch.object(oa, "load_operation_definitions_from_same_folder", return_value=operations or []):
            output = oa.capabilitystatement_to_openapi("", "", config, conversion)
        self.assertEqual(capability, original)
        return output

    def test_resource_boundaries_prefix_and_conditional_request_bodies(self):
        output = self.convert([
            {"type": "Task", "conditionalUpdate": True, "conditionalDelete": "multiple",
             "searchParam": [search("status")]},
            {"type": "Patient", "conditionalUpdate": True,
             "searchParam": [search("identifier")]},
        ])
        self.assertEqual(output["servers"], [{"url": "https://example.org"}])
        self.assertEqual(set(output["paths"]), {"/fhir/v1/Task", "/fhir/v1/Patient"})
        for path, name in (("/fhir/v1/Task", "status"), ("/fhir/v1/Patient", "identifier")):
            update = output["paths"][path]["put"]
            self.assertEqual([p["name"] for p in update["parameters"]], [name])
            self.assertEqual(set(update["requestBody"]["content"]),
                             {"application/fhir+json", "application/fhir+xml"})
        self.assertNotIn("requestBody", output["paths"]["/fhir/v1/Task"]["delete"])
        self.assertNotIn("delete", output["paths"]["/fhir/v1/Patient"])

    def test_post_search_and_conditional_delete_keep_distinct_assignments(self):
        output = self.convert([{
            "type": "Task", "interaction": [{"code": "search-type"}, {"code": "read"}],
            "conditionalDelete": "single",
            "searchParam": [search("status"), search("ac", "read")],
        }], enhanced=True)
        for path, method in (("/fhir/v1/Task", "get"), ("/fhir/v1/Task/_search", "post")):
            names = [p["name"] for p in output["paths"][path][method]["parameters"]]
            self.assertIn("status", names)
            self.assertNotIn("ac", names)
        names = [p["name"] for p in output["paths"]["/fhir/v1/Task"]["delete"]["parameters"]]
        self.assertEqual(names, ["_format", "status", "ac"])

    def test_conditional_read_modes_emit_exact_headers(self):
        for mode, expected in (
            ("modified-since", {"If-Modified-Since"}),
            ("not-match", {"If-None-Match"}),
            ("full-support", {"If-Modified-Since", "If-None-Match"}),
        ):
            with self.subTest(mode=mode):
                output = self.convert([{"type": "Task", "conditionalRead": mode}])
                read = output["paths"]["/fhir/v1/Task/{id}"]["get"]
                headers = [p for p in read["parameters"] if p["in"] == "header"]
                self.assertEqual({p["name"] for p in headers}, expected)
                self.assertTrue(all(p["required"] is False for p in headers))
                self.assertEqual(read["responses"]["304"], {"description": "Not modified"})

    def test_conflicting_normal_and_conditional_responses_are_preserved(self):
        output = self.convert([{
            "type": "Task", "conditionalRead": "not-match",
            "interaction": [{"code": "read", "extension": [
                http("response-info", statusCode="404", description="Normal missing")]}],
            "extension": [http("response-info", "conditional-read",
                               statusCode="404", description="Conditional missing")],
        }])
        read = output["paths"]["/fhir/v1/Task/{id}"]["get"]
        self.assertEqual(read["responses"]["404"]["description"], "Normal missing")
        self.assertEqual(read["x-fhir-conditional"]["responses"]["404"]["description"],
                         "Conditional missing")

    def test_conditional_header_override_is_unique_and_variant_is_independent(self):
        output = self.convert([{
            "type": "Task", "conditionalCreate": True,
            "interaction": [{"code": "create"}],
            "extension": [http("header", "conditional-create", name="If-None-Exist",
                               type="string", required=True, description="Custom condition")],
        }])
        create = output["paths"]["/fhir/v1/Task"]["post"]
        headers = [p for p in create["parameters"] if p["name"] == "If-None-Exist"]
        self.assertEqual(len(headers), 1)
        self.assertEqual(headers[0]["description"], "Custom condition")
        self.assertIs(headers[0]["required"], False)
        variant = create["x-fhir-conditional"]["parameters"]
        self.assertIs(next(p for p in variant if p["name"] == "If-None-Exist")["required"], True)
        headers[0]["description"] = "Changed"
        self.assertEqual(next(p for p in variant if p["name"] == "If-None-Exist")["description"],
                         "Custom condition")

    def test_resource_response_override_retains_success_content(self):
        output = self.convert([{
            "type": "Task", "interaction": [{"code": "read"}],
            "extension": [http("response-info", "read", statusCode="200",
                               description="Custom success")],
        }])
        response = output["paths"]["/fhir/v1/Task/{id}"]["get"]["responses"]["200"]
        self.assertEqual(response["description"], "Custom success")
        self.assertEqual(set(response["content"]), {"application/fhir+json", "application/fhir+xml"})

    def test_repeated_resource_interaction_selector_is_rejected(self):
        ext = http("header", "read", name="X-Test")
        ext["extension"].append({"url": "interaction", "valueCode": "delete"})
        with self.assertRaisesRegex(ValueError, "requires a supported interaction"):
            self.convert([{"type": "Task", "extension": [ext]}])

    def test_operation_query_schema_and_body_across_http_methods(self):
        for method in ("POST", "PUT", "PATCH", "GET"):
            for fhir_type, schema in (
                ("boolean", {"type": "boolean"}),
                ("integer", {"type": "integer"}),
                ("date", {"type": "string", "format": "date"}),
                ("uri", {"type": "string", "format": "uri"}),
            ):
                with self.subTest(method=method, fhir_type=fhir_type):
                    definition = {
                        "url": "https://example.org/check", "code": "check",
                        "instance": True, "resource": ["Task"],
                        "extension": [{"url": BASE + "extension-http-method", "valueCode": method}],
                        "parameter": [{
                            "name": "input", "use": "in", "min": 1, "max": "1",
                            "type": fhir_type, "documentation": "Query input",
                            "extension": [{"url": oa.OPERATION_PARAMETER_LOCATION_EXTENSION,
                                           "valueCode": "query"}],
                        }],
                    }
                    original = copy.deepcopy(definition)
                    output = self.convert([{
                        "type": "Task", "operation": [{
                            "name": "check", "definition": definition["url"],
                        }],
                    }], operations=[definition])
                    operation = output["paths"]["/fhir/v1/Task/{id}/$check"][method.lower()]
                    query = next(p for p in operation["parameters"] if p["name"] == "input")
                    self.assertEqual(query, {
                        "name": "input", "in": "query", "required": True,
                        "schema": schema, "description": "Query input",
                    })
                    self.assertNotIn("requestBody", operation)
                    self.assertEqual(definition, original)


if __name__ == "__main__":
    unittest.main()

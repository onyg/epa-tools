import contextlib
import copy
import io
import unittest
from unittest.mock import patch

from epatools import oaconverter as oa

BASE = "https://gematik.de/fhir/ti/StructureDefinition/"


def search(name, *codes):
    return {"name": name, "type": "token", "extension": [
        {"url": oa.SEARCH_PARAMETER_INTERACTION_EXTENSION, "valueCode": c} for c in codes]}


def http(kind, interaction=None, **values):
    children = [{"url": k, "valueBoolean" if isinstance(v, bool) else "valueString": v}
                for k, v in values.items()]
    if interaction is not None:
        children.append({"url": "interaction", "valueCode": interaction})
    return {"url": BASE + "extension-http-" + kind, "extension": children}


class ConditionalTests(unittest.TestCase):
    def convert(self, resource):
        capability = {"format": ["application/fhir+json"], "rest": [{"resource": [
            {"type": "Task", **resource}]}]}
        original = copy.deepcopy(capability)
        self.log = io.StringIO()
        with contextlib.redirect_stdout(self.log),                 patch.object(oa.FHIRArtifactLoader, "load_artifact", return_value=(capability, "")),                 patch.object(oa, "load_operation_definitions_from_same_folder", return_value=[]):
            output = oa.capabilitystatement_to_openapi("", "", oa.OpenAPIConfig(None), oa.ConvertConfig())
        self.assertEqual(capability, original)
        return output["paths"]

    def queries(self, operation):
        return [p["name"] for p in operation["parameters"] if p["in"] == "query"]

    def test_delete_modes_and_independent_capability(self):
        for mode in ("single", "multiple", "not-supported", None):
            for normal in (True, False):
                with self.subTest(mode=mode, normal=normal):
                    paths = self.convert({
                        "conditionalDelete": mode,
                        "interaction": [{"code": "delete"}] if normal else [],
                        "searchParam": [search("status", "conditional-delete"), search("authored-on", "conditional-delete"),
                                        search("plain"), search("only-search", "search-type")],
                    })
                    self.assertEqual("/Task/{id}" in paths, normal)
                    self.assertEqual("/Task" in paths, mode in ("single", "multiple"))
                    if "/Task" in paths:
                        self.assertEqual(self.queries(paths["/Task"]["delete"]), ["status", "authored-on", "plain", "only-search"])

    def test_update_modes_and_independent_capability(self):
        for enabled in (True, False, None):
            for normal in (True, False):
                with self.subTest(enabled=enabled, normal=normal):
                    paths = self.convert({
                        "conditionalUpdate": enabled,
                        "interaction": [{"code": "update"}] if normal else [],
                        "searchParam": [search("identifier", "conditional-update"), search("plain"),
                                        search("delete-only", "conditional-delete")],
                    })
                    self.assertEqual("/Task/{id}" in paths, normal)
                    self.assertEqual("/Task" in paths, enabled is True)
                    if "/Task" in paths:
                        self.assertEqual(self.queries(paths["/Task"]["put"]), ["identifier", "plain", "delete-only"])

    def test_all_search_parameters_apply_without_assignment(self):
        for flag, value, method in (("conditionalDelete", "single", "delete"),
                                    ("conditionalDelete", "multiple", "delete"),
                                    ("conditionalUpdate", True, "put")):
            with self.subTest(flag=flag, value=value):
                paths = self.convert({flag: value, "searchParam": [search("plain")]})
                self.assertEqual(self.queries(paths["/Task"][method]), ["plain"])
                self.assertNotIn("⚠️", self.log.getvalue())
                paths = self.convert({flag: value})
                self.assertEqual(self.queries(paths["/Task"][method]), [])
                self.assertIn("no search parameters defined", self.log.getvalue())

    def test_multiple_assignments_and_resource_http_isolation(self):
        paths = self.convert({
            "conditionalDelete": "multiple", "conditionalUpdate": True,
            "interaction": [{"code": c} for c in ("search-type", "delete", "update")],
            "searchParam": [search("status", "conditional-delete", "search-type"),
                            search("identifier", "conditional-update")],
            "extension": [
                http("header", "conditional-delete", name="Delete-Header", type="string", required=True),
                http("header", "conditional-update", name="Update-Header", type="string"),
                *[http("response-info", "conditional-delete", statusCode=c, description="Delete " + c)
                  for c in ("204", "400", "404")],
                http("response-info", "conditional-update", statusCode="409", description="Update conflict"),
            ],
        })
        self.assertIn("status", self.queries(paths["/Task"]["get"]))
        self.assertEqual(self.queries(paths["/Task"]["delete"]), ["status", "identifier"])
        self.assertEqual(self.queries(paths["/Task"]["put"]), ["status", "identifier"])
        for code in ("204", "400", "404"):
            self.assertEqual(paths["/Task"]["delete"]["responses"][code]["description"], "Delete " + code)
        self.assertNotIn("409", paths["/Task/{id}"]["put"]["responses"])
        for method, name in (("delete", "Delete-Header"), ("put", "Update-Header")):
            self.assertIn(name, [p["name"] for p in paths["/Task"][method]["parameters"]])
            self.assertNotIn(name, [p["name"] for p in paths["/Task/{id}"][method]["parameters"]])

    def test_read_assignment_does_not_restrict_conditional_search(self):
        paths = self.convert({
            "conditionalUpdate": True, "conditionalDelete": "multiple",
            "interaction": [{"code": "read"}, {"code": "search-type"}],
            "searchParam": [search("ac", "read"), search("status")],
        })
        for method in ("put", "delete"):
            self.assertEqual(self.queries(paths["/Task"][method]), ["ac", "status"])
        self.assertIn("ac", self.queries(paths["/Task/{id}"]["get"]))
        self.assertNotIn("status", self.queries(paths["/Task/{id}"]["get"]))
        self.assertNotIn("ac", self.queries(paths["/Task"]["get"]))

    def test_shared_read_and_create_variants(self):
        for flag, value, code, normal, method, path, header in (
            ("conditionalCreate", True, "conditional-create", "create", "post", "/Task", "If-None-Exist"),
            ("conditionalRead", "full-support", "conditional-read", "read", "get", "/Task/{id}", "If-None-Match"),
        ):
            for include_normal in (False, True):
                with self.subTest(code=code, normal=include_normal):
                    paths = self.convert({
                        flag: value, "interaction": [{"code": normal}] if include_normal else [],
                        "searchParam": [search("not-a-query", code)],
                        "extension": [
                            http("header", code, name=header, type="string", required=True),
                            http("response-info", code, statusCode="304", description="Conditional response"),
                        ],
                    })
                    self.assertEqual(list(paths), [path])
                    op = paths[path][method]
                    self.assertNotIn("not-a-query", self.queries(op))
                    self.assertIn("304", op["responses"])
                    rendered = next(p for p in op["parameters"] if p["name"] == header)
                    self.assertEqual(rendered["required"], not include_normal)
                    self.assertEqual(op["x-fhir-conditional"]["interaction"], code)
                    variant = op["x-fhir-conditional"]["parameters"]
                    self.assertTrue(next(p for p in variant if p["name"] == header)["required"])

    def test_disabled_capabilities_ignore_scoped_extensions(self):
        for resource in ({}, {"conditionalCreate": False, "conditionalRead": "not-supported",
                             "conditionalDelete": "not-supported", "conditionalUpdate": False}):
            resource["extension"] = [http("header", "conditional-delete", name="X-Delete")]
            self.assertEqual(self.convert(resource), {})

    def test_read_modes(self):
        for mode in ("modified-since", "not-match", "full-support"):
            self.assertIn("/Task/{id}", self.convert({"conditionalRead": mode}))

    def test_existing_interaction_extensions_and_resource_scope(self):
        paths = self.convert({
            "interaction": [{"code": "read", "extension": [
                http("header", name="Legacy", type="string", required=True),
                http("response-info", statusCode="404", description="Legacy missing"),
            ]}, {"code": "update"}],
            "extension": [http("header", "update", name="Scoped", type="string"),
                          http("response-info", "update", statusCode="409", description="Conflict")],
        })
        read, update = paths["/Task/{id}"]["get"], paths["/Task/{id}"]["put"]
        self.assertIn("Legacy", [p["name"] for p in read["parameters"]])
        self.assertEqual(read["responses"]["404"]["description"], "Legacy missing")
        self.assertNotIn("Scoped", [p["name"] for p in read["parameters"]])
        self.assertIn("Scoped", [p["name"] for p in update["parameters"]])
        self.assertIn("409", update["responses"])

    def test_operation_extensions_remain_unscoped(self):
        definition = {"url": "https://example.org/op", "code": "example", "system": True,
                      "parameter": [], "extension": [
                          {"url": BASE + "extension-http-method", "valueCode": "POST"}]}
        op = {"name": "example", "definition": definition["url"], "extension": [
            http("header", name="Operation-Header", type="string", required=True),
            http("response-info", statusCode="400", description="Operation error"),
        ]}
        for resource_level in (False, True):
            rest = {"resource": [{"type": "Task", "operation": [op]}]} if resource_level else {"operation": [op]}
            with self.subTest(resource_level=resource_level), contextlib.redirect_stdout(io.StringIO()):
                result = oa.add_operations_from_capabilitystatement(
                    oa.OpenAPIConfig(None), {"paths": {}}, {"rest": [rest]},
                    [definition], ["application/fhir+json"], [], {})
                output = result["paths"]["/$example"]["post"]
                self.assertIn("Operation-Header", [p["name"] for p in output["parameters"]])
                self.assertEqual(output["responses"]["400"]["description"], "Operation error")

    def test_resource_header_false_is_boolean(self):
        paths = self.convert({"interaction": [{"code": "read"}], "extension": [
            http("header", "read", name="Optional", type="string", required=False)]})
        header = next(p for p in paths["/Task/{id}"]["get"]["parameters"] if p["name"] == "Optional")
        self.assertIs(header["required"], False)

    def test_resource_http_requires_valid_interaction(self):
        for code in (None, "unknown"):
            with self.assertRaises(ValueError):
                self.convert({"extension": [http("header", code, name="Invalid")]})


if __name__ == "__main__":
    unittest.main()

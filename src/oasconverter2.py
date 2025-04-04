import os
import json
import yaml
from urllib.parse import urlparse

# # Original-Dateipfade
input_path = "./data/CapabilityStatement-epa-medication-service-server-merged.json"
output_json_path = "./output/epa-medication-openapi.json"
output_yaml_path = "./output/epa-medication-openapi.yaml"
manual_operations_path = "./openapis/manual-operations.yaml"  # << Neue Datei mit eigenen Operationen

# Original-Dateipfade
# input_path = "./data/CapabilityStatement-epa-audit-event-server.json"
# output_json_path = "./output/epa-audit-openapi.json"
# output_yaml_path = "./output/epa-audit-openapi.yaml"


def fhir_to_openapi_type(fhir_type):
    mapping = {
        "string": ("string", None),
        "token": ("string", None),
        "date": ("string", "date"),
        "reference": ("string", "uri"),
        "uri": ("string", "uri"),
        "number": ("number", None),
        "quantity": ("string", None),
        "composite": ("string", None),
        "special": ("string", None),
        "boolean": ("boolean", None),
        "integer": ("integer", None)
    }
    return mapping.get(fhir_type, ("string", None))

def extract_http_headers(extensions):
    headers = []
    for ext in extensions:
        if ext.get("url") == "https://gematik.de/fhir/epa/StructureDefinition/http-header":
            header = {}
            for sub in ext.get("extension", []):
                header[sub["url"]] = sub.get("valueString") or sub.get("valueBoolean")
            headers.append(header)
    return headers

def extract_http_errors(extensions):
    errors = {}
    for ext in extensions:
        if ext.get("url") == "https://gematik.de/fhir/epa/StructureDefinition/http-error":
            code = None
            description = None
            for sub in ext.get("extension", []):
                if sub["url"] == "statusCode":
                    code = sub["valueString"]
                if sub["url"] == "description":
                    description = sub["valueString"]
            if code:
                errors[code] = {"description": description}
    return errors

def extract_base_url_parts(extensions):
    for ext in extensions:
        if ext.get("url") == "https://gematik.de/fhir/epa/StructureDefinition/base-url":
            full_url = ext.get("valueString")
            if full_url:
                parsed = urlparse(full_url)
                host = f"{parsed.scheme}://{parsed.netloc}"
                path = parsed.path.rstrip("/")
                return host, path
    return None, ""

def build_responses(global_errors, success_code="200", success_description="Successful operation"):
    responses = {
        success_code: {
            "description": success_description,
            "content": {
                "application/fhir+json": {
                    "schema": {
                        "type": "object"
                    }
                }
            }
        }
    }
    for code, info in global_errors.items():
        if code != success_code:  # avoid overwriting the success code
            responses[code] = {
                "description": info.get("description", "")
            }
    return responses if responses else {
        "default": {
            "description": "Default error response"
        }
    }

def build_request_body(resource_type: str, formats: list) -> dict:
    """
    Erstellt ein requestBody-Objekt für OpenAPI auf Basis des FHIR-Resource-Typs
    und der unterstützten Formate (application/fhir+json, application/fhir+xml).
    request_body = {
        "required": True,
        "content": {
            "application/fhir+json": {"schema": {"type": "object"}},
            "application/fhir+xml": {"schema": {"type": "object"}}
        }
    }
    """
    content = {}
    if "application/fhir+json" in formats:
        content["application/fhir+json"] = {
            "schema": {
                "type": "object"
            }
        }
    if "application/fhir+xml" in formats:
        content["application/fhir+xml"] = {
            "schema": {
                "type": "object"
            }
        }
    return {
        "required": True,
        "content": content
    } if content else None



def build_format_query_param(fhir_formats):
    if len(fhir_formats) > 1:
        return {
            "name": "_format",
            "in": "query",
            "required": False,
            "description": "Specifies the return format",
            "schema": {
                "type": "string",
                "enum": fhir_formats
            }
        }
    return None


def build_pagination_query_params():
    return [
        {
            "name": "_count",
            "in": "query",
            "required": False,
            "description": "With _count, the client can specify the maximum number of elements to be included on one page of the response. This means the Medication Service limits the result set to this maximum specified number. If no value for _count is provided, the default value set is 25.",
            "schema": {
                "type": "string"
            }
        },
        {
            "name": "_offset",
            "in": "query",
            "required": False,
            "description": "This URL parameter indicates the (zero-based) offset of the first returned element in the collection. If no value for _offset is provided, the default value set is 0.",
            "schema": {
                "type": "integer"
            }
        },
        {
            "name": "_total",
            "in": "query",
            "required": False,
            "description": "This parameter controls whether and how the AuditEvent Service returns the total number of search results.",
            "schema": {
                "type": "string"
            }
        }
    ]



def build_include_query_param(search_include):
    if search_include:
        return {
            "name": "_include",
            "in": "query",
            "required": False,
            "description": "Including other resources",
            "schema": {
                "type": "string",
            }
        }
    return None

def build_revinclude_query_param(search_rev_include):
    if search_rev_include:
        return {
            "name": "_revinclude",
            "in": "query",
            "required": False,
            "description": "Reverse include other resources",
            "schema": {
                "type": "string",
            }
        }
    return None


def build_header_params(headers):
    params = []
    for header in headers:
        name = header.get("name")
        if name:
            param = {
                "name": name,
                "in": "header",
                "required": header.get("required", False),
                "description": header.get("description", ""),
                "schema": {
                    "type": header.get("type", "string")
                }
            }
            if "format" in header:
                param["schema"]["format"] = header["format"]
            if "pattern" in header:
                param["schema"]["pattern"] = header["pattern"]
            params.append(param)
    return params

def interaction_to_paths(resource_type, interaction_code, search_params, search_include, search_rev_include, global_errors,
                         prefix_path="", format_query_param=None, header_params=None, fhir_formats=None):
    paths = {}

    base_parameters = []
    if format_query_param:
        base_parameters.append(format_query_param)
    if header_params:
        base_parameters.extend(header_params)

    # def build_request_body(resource_type: str, formats: list) -> dict:
    #     content = {}
    #     if "application/fhir+json" in formats:
    #         content["application/fhir+json"] = {
    #             "schema": {
    #                 "$ref": f"https://hl7.org/fhir/R4/fhir.schema.json#/definitions/{resource_type}"
    #             }
    #         }
    #     if "application/fhir+xml" in formats:
    #         content["application/fhir+xml"] = {
    #             "schema": {
    #                 "$ref": f"https://hl7.org/fhir/R4/{resource_type.lower()}.xsd"
    #             }
    #         }
    #     return {"required": True, "content": content} if content else None

    def path_obj(method, summary, parameters, responses, request_body=None):
        obj = {
            method: {
                "summary": summary,
                "parameters": parameters,
                "responses": responses
            }
        }
        if request_body:
            obj[method]["requestBody"] = request_body
        return obj

    if interaction_code == "read":
        responses = build_responses(global_errors, success_code="200", success_description=f"{resource_type} successfully read")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = base_parameters + [{
            "name": "id", "in": "path", "required": True,
            "schema": { "type": "string" }, "description": "Resource ID"
        }]
        paths[path] = path_obj("get", f"Read a specific {resource_type}", params, responses)

    elif interaction_code == "vread":
        responses = build_responses(global_errors, success_code="200", success_description=f"{resource_type} version read")
        path = f"{prefix_path}/{resource_type}/{{id}}/_history/{{vid}}"
        params = base_parameters + [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Resource ID"},
            {"name": "vid", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Version ID"}
        ]
        paths[path] = path_obj("get", f"Read version of {resource_type}", params, responses)

    elif interaction_code == "history-instance":
        responses = build_responses(global_errors, success_code="200", success_description="History retrieved")
        path = f"{prefix_path}/{resource_type}/{{id}}/_history"
        params = base_parameters + [{
            "name": "id", "in": "path", "required": True,
            "schema": { "type": "string" }, "description": "Resource ID"
        }]
        params.extend(build_pagination_query_params())
        paths[path] = path_obj("get", f"History of a specific {resource_type}", params, responses)

    elif interaction_code == "history-type":
        responses = build_responses(global_errors, success_code="200", success_description="History for type retrieved")
        path = f"{prefix_path}/{resource_type}/_history"
        params = base_parameters + build_pagination_query_params()
        paths[path] = path_obj("get", f"History for all {resource_type}", params, responses)

    elif interaction_code == "search-type":
        responses = build_responses(global_errors, success_code="200", success_description="Search successful")
        path = f"{prefix_path}/{resource_type}"
        params = base_parameters.copy()
        params.extend(build_pagination_query_params())
        if search_include:
            params.append(build_include_query_param(search_include))
        if search_rev_include:
            params.append(build_revinclude_query_param(search_rev_include))
        for sp in search_params:
            param_type, param_format = fhir_to_openapi_type(sp.get("type", "string"))
            param = {
                "name": sp.get("name"),
                "in": "query",
                "required": False,
                "schema": { "type": param_type },
                "description": sp.get("documentation", "")
            }
            if param_format:
                param["schema"]["format"] = param_format
            params.append(param)
        paths[path] = path_obj("get", f"Search for {resource_type}", params, responses)

    elif interaction_code == "create":
        responses = build_responses(global_errors, success_code="201", success_description="Resource created")
        path = f"{prefix_path}/{resource_type}"
        # request_body = {
        #     "required": True,
        #     "content": {
        #         "application/fhir+json": {"schema": {"type": "object"}},
        #         "application/fhir+xml": {"schema": {"type": "object"}}
        #     }
        # }
        request_body = build_request_body(resource_type, fhir_formats or [])
        paths[path] = path_obj("post", f"Create a new {resource_type}", base_parameters, responses, request_body)

    elif interaction_code == "update":
        responses = build_responses(global_errors, success_code="200", success_description="Resource updated")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = base_parameters + [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        # request_body = {
        #     "required": True,
        #     "content": {
        #         "application/fhir+json": {"schema": {"type": "object"}},
        #         "application/fhir+xml": {"schema": {"type": "object"}}
        #     }
        # }
        request_body = build_request_body(resource_type, fhir_formats or [])
        paths[path] = path_obj("put", f"Update {resource_type} by ID", params, responses, request_body)

    elif interaction_code == "patch":
        responses = build_responses(global_errors, success_code="200", success_description="Resource patched")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = base_parameters + [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        # request_body = {
        #     "required": True,
        #     "content": {
        #         "application/json-patch+json": {
        #             "schema": {
        #                 "type": "array",
        #                 "items": {"type": "object"}
        #             }
        #         }
        #     }
        # }
        request_body = build_request_body(resource_type, fhir_formats or [])
        paths[path] = path_obj("patch", f"Patch {resource_type} by ID", params, responses, request_body)

    elif interaction_code == "delete":
        responses = build_responses(global_errors, success_code="204", success_description="Resource deleted")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = base_parameters + [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        paths[path] = path_obj("delete", f"Delete {resource_type} by ID", params, responses)

    return paths


def load_operation_definitions_from_same_folder(capability_path):
    folder = os.path.dirname(capability_path)
    operation_definitions = []

    for filename in os.listdir(folder):
        if filename.endswith(".json") and "OperationDefinition" in filename:
            with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                content = json.load(f)
                if content.get("resourceType") == "OperationDefinition":
                    operation_definitions.append(content)
                elif content.get("resourceType") == "Bundle":
                    for entry in content.get("entry", []):
                        res = entry.get("resource")
                        if res and res.get("resourceType") == "OperationDefinition":
                            operation_definitions.append(res)
    return operation_definitions

def try_download_operation_definition(url):
    try:
        with urllib.request.urlopen(url) as response:
            content = json.load(response)
            if content.get("resourceType") == "OperationDefinition":
                return content
    except Exception as e:
        print(f"❌ Fehler beim Herunterladen von OperationDefinition: {e}")
    return None


def add_operations_from_capabilitystatement(openapi, capability, operation_definitions, fhir_formats, header_params, global_errors, path_prefix=""):
    def build_responses(success_code="200", success_description="Successful operation"):
        responses = {
            success_code: {
                "description": success_description,
                "content": {
                    "application/fhir+json": {
                        "schema": {
                            "type": "object"
                        }
                    }
                }
            }
        }
        for code, info in global_errors.items():
            if code != success_code:
                responses[code] = {"description": info.get("description", "")}
        return responses

    def build_parameters(params, location="query"):
        result = []
        for param in params:
            p = {
                "name": param["name"],
                "in": location,
                "required": param.get("use") == "in" and param.get("min", 0) > 0,
                "description": param.get("documentation", ""),
                "schema": {
                    "type": fhir_to_openapi_type(param.get("type", "string"))[0]
                }
            }
            result.append(p)
        return result

    for rest in capability.get("rest", []):
        for op in rest.get("operation", []):
            op_name = op["name"]
            definition_obj = op.get("definition")
            if isinstance(definition_obj, dict):
                definition_ref = definition_obj.get("reference")
            else:
                definition_ref = definition_obj

            operation_definition = None
            for od in operation_definitions:
                if od.get("url") == definition_ref or od.get("id") == definition_ref.split("/")[-1]:
                    operation_definition = od
                    break

            if not operation_definition:
                print(f"⚠️ OperationDefinition nicht gefunden für: {definition_ref}")
                continue

            # http_method = operation_definition.get("code", "post").lower()
            http_method = "post"
            op_responses = build_responses()
            op_params = operation_definition.get("parameter", [])
            params = header_params.copy()
            params.extend(build_parameters(op_params))

            # system-level operation
            if operation_definition.get("system") is True:
                path = f"{path_prefix}/${op_name}"
                openapi["paths"].setdefault(path, {})[http_method] = {
                    "summary": f"System-level FHIR Operation ${op_name}",
                    "operationId": f"system_${op_name}",
                    "parameters": params,
                    "responses": op_responses
                }

            # type-level operation
            if operation_definition.get("type") is True:
                for resource_type in operation_definition.get("resource", []):
                    path = f"{path_prefix}/{resource_type}/${op_name}"
                    openapi["paths"].setdefault(path, {})[http_method] = {
                        "summary": f"Type-level FHIR Operation ${op_name}",
                        "operationId": f"{resource_type}_${op_name}",
                        "parameters": params,
                        "responses": op_responses
                    }

            # instance-level operation
            if operation_definition.get("instance") is True:
                for resource_type in operation_definition.get("resource", []):
                    path = f"{path_prefix}/{resource_type}/{{id}}/${op_name}"
                    openapi["paths"].setdefault(path, {})[http_method] = {
                        "summary": f"Instance-level FHIR Operation ${op_name}",
                        "operationId": f"{resource_type}_instance_${op_name}",
                        "parameters": params + [{
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Resource ID"
                        }],
                        "responses": op_responses
                    }
    print("✅ OperationDefinition(s) wurden hinzugefügt.")
    return openapi



# Am Ende von capabilitystatement_to_openapi hinzufügen:
def merge_manual_operations(openapi, manual_path):
    if not os.path.exists(manual_path):
        print(f"⚠️ Keine manuelle OpenAPI-Datei gefunden unter {manual_path}")
        return openapi

    with open(manual_path, "r", encoding="utf-8") as f:
        manual = yaml.safe_load(f)

    for path, methods in manual.get("paths", {}).items():
        if path not in openapi["paths"]:
            openapi["paths"][path] = {}
        openapi["paths"][path].update(methods)

    print("✅ Manuelle Operationen wurden hinzugefügt.")
    return openapi


def capabilitystatement_to_openapi(capability_json):
    openapi = {
        "openapi": "3.0.3",
        "info": {
            "title": capability_json.get("title"),
            "version": capability_json.get("version"),
            "description": capability_json.get("description")
        },
        "paths": {},
        "components": {
            "responses": {},
            "headers": {}
        }
    }

    extensions = capability_json.get("extension", [])
    host_url, path_prefix = extract_base_url_parts(extensions)
    if host_url:
        openapi["servers"] = [{
            "url": host_url,
            "description": "Base host as defined in FHIR Extension"
        }]
    else:
        path_prefix = ""

    fhir_formats = capability_json.get("format", [])
    format_query_param = build_format_query_param(fhir_formats)

    headers = extract_http_headers(extensions)
    header_params = build_header_params(headers)

    for header in headers:
        name = header.get("name")
        if name:
            openapi["components"]["headers"][name] = {
                "description": header.get("description", ""),
                "required": header.get("required", False),
                "schema": {
                    "type": header.get("type", "string")
                }
            }
            if "format" in header:
                openapi["components"]["headers"][name]["schema"]["format"] = header["format"]
            if "pattern" in header:
                openapi["components"]["headers"][name]["schema"]["pattern"] = header["pattern"]

    errors = extract_http_errors(extensions)
    for code, info in errors.items():
        openapi["components"]["responses"][code] = {
            "description": info.get("description", "")
        }

    for rest in capability_json.get("rest", []):
        for res in rest.get("resource", []):
            resource_type = res.get("type")
            interactions = res.get("interaction", [])
            search_params = res.get("searchParam", [])
            search_include = res.get("searchInclude", [])
            search_rev_include = res.get("searchRevInclude", [])

            for interaction in interactions:
                interaction_code = interaction.get("code")
                new_paths = interaction_to_paths(
                    resource_type,
                    interaction_code,
                    search_params,
                    search_include,
                    search_rev_include,
                    errors,
                    prefix_path=path_prefix,
                    format_query_param=format_query_param,
                    header_params=header_params,
                    fhir_formats=fhir_formats
                )
                for path, item in new_paths.items():
                    if path not in openapi["paths"]:
                        openapi["paths"][path] = {}
                    openapi["paths"][path].update(item)

    # # Optional: OperationDefinition-Dateien einlesen (hier Beispiel mit leeren Array)
    # operation_definitions = load_operation_definitions_from_same_folder(input_path)
    # openapi = add_operations_from_capabilitystatement(
    #     openapi=openapi,
    #     capability=capability_json,
    #     operation_definitions=operation_definitions,
    #     fhir_formats=fhir_formats,
    #     header_params=header_params,
    #     global_errors=errors,
    #     path_prefix=path_prefix
    # )

    openapi = merge_manual_operations(openapi, manual_operations_path)

    return openapi

if __name__ == "__main__":
    with open(input_path, "r", encoding="utf-8") as f:
        capability = json.load(f)

    openapi_spec = capabilitystatement_to_openapi(capability)

    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_spec, f, indent=2, ensure_ascii=False)

    class NoAliasDumper(yaml.SafeDumper):
        def ignore_aliases(self, data):
            return True

    with open(output_yaml_path, "w", encoding="utf-8") as f:
        yaml.dump(openapi_spec, f, indent=2, sort_keys=False, allow_unicode=True, Dumper=NoAliasDumper)

    print(f"✅ OpenAPI gespeichert als:\n- JSON: {output_json_path}\n- YAML: {output_yaml_path}")

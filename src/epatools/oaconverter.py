import os
import json
import yaml
from urllib.parse import urlparse

from epatools.common import BaseConfig, FHIRArtifactLoader

class ConvertConfig(object):

    def __init__(self):
        self.input = None
        self.output = None
        self.additional_openapi = None
        self.search_with_post = False

class OpenAPIConfig(BaseConfig):

    def __init__(self, config):
        super().__init__(config)
        self.config_file = config
        self.path_resource = "fsh-generated/resources"
        self.path_output = "openapi"
        self.with_metadata = False
        self.with_format_parameter = False
        self.with_accept_header = False
        self.capability_statement = []

    def from_dict(self, data):
        if 'openapi' in data:
            params = data.get('openapi')
            self.path_resource = params.get('path-resource', self.path_resource)
            self.path_output = params.get('path-output', self.path_output)
            self.with_metadata = params.get('with-metadata', self.with_metadata)
            self.with_format_parameter = params.get('with-format-parameter', self.with_format_parameter)
            self.with_accept_header = params.get('with-accept-header', self.with_accept_header)
            self.capability_statement = []
            for cs in params.get('capability-statement', []):
                convert_config = ConvertConfig()
                convert_config.input = cs.get('input', None)
                convert_config.output = cs.get('output', None)
                convert_config.additional_openapi = cs.get('additional-openapi', None)
                convert_config.search_with_post = cs.get('post-search', False)
                self.capability_statement.append(convert_config)
            

class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


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

###
# Operations
###
def load_operation_definitions_from_same_folder(capability_path):
    # folder = capability_path
    operation_definitions = []

    for filename in os.listdir(capability_path):
        if filename.endswith(".json") and "OperationDefinition" in filename:
            with open(os.path.join(capability_path, filename), "r", encoding="utf-8") as f:
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
        print(f"❌ Error while downloading OperationDefinition: {e}")
    return None



def add_operations_from_capabilitystatement(config, openapi, capability, operation_definitions, formats, header_params, http_errors, path_prefix=""):

    def add_operation(openapi, op):
        op_name = op["name"].lstrip("$")
        op_http_errors = http_errors
        op_header_params = header_params
        http_methods = ['post']
        if not op_header_params:
            op_header_params = []
        if not op_http_errors:
            op_http_errors = {}
        if op.get('extension', None):
            extension = op.get('extension')
            op_http_errors = {**extract_http_response_info(extension), **op_http_errors}
            op_header_params.extend(extract_http_headers(extension))
            http_methods = extract_http_methods(extension)
        
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
            print(f"⚠️ OperationDefinition not found for: {definition_ref}")
            return openapi

        op_name = operation_definition["code"]

        http_methods.extend(extract_http_methods(operation_definition.get('extension', [])))
        http_methods = list(set(http_methods))
        op_responses = build_responses(
                            op_http_errors,
                            formats, 
                            success_codes=["200"],
                            success_description="Successful operation"
        )
        op_params = operation_definition.get("parameter", [])
        for http_method in http_methods:
            oas_params = []
            request_body = None
            if config.with_accept_header:
                accept_header_param = build_accept_header_param(formats)
                if accept_header_param:
                    oas_params.append(accept_header_param)
            # if http_method == "get":
            #     oas_params.extend(build_header_params(op_header_params))
            #     if config.with_format_parameter:
            #         format_param = build_format_query_param(formats)
            #         if format_param:
            #             oas_params.append(format_param)
                        
            #     oas_params.extend(build_parameters(op_params))
                
            # else:
            #     oas_params.extend(build_header_params(op_header_params))
            #     request_body = build_request_body(formats)
            oas_params.extend(build_header_params(op_header_params))
            if config.with_format_parameter:
                format_param = build_format_query_param(formats)
                if format_param:
                    oas_params.append(format_param)
                    
            oas_params.extend(build_parameters(op_params))

            # system-level operation
            if operation_definition.get("system") is True:
                path = f"{path_prefix}/${op_name}"
                openapi["paths"].setdefault(path, {})[http_method] = {
                    "summary": f"System-level FHIR Operation ${op_name}",
                    "tags": ["System-level FHIR Operation"],
                    "parameters": oas_params.copy(),
                    "responses": op_responses
                }
                if request_body:
                    openapi["paths"][path][http_method]["requestBody"] = request_body

            # type-level operation
            if operation_definition.get("type") is True:
                for resource_type in operation_definition.get("resource", []):
                    path = f"{path_prefix}/{resource_type}/${op_name}"
                    openapi["paths"].setdefault(path, {})[http_method] = {
                        "summary": f"Type-level FHIR Operation ${op_name}",
                        "tags": [resource_type],
                        "parameters": oas_params.copy(),
                        "responses": op_responses
                    }
                    if request_body:
                        openapi["paths"][path][http_method]["requestBody"] = request_body

            # instance-level operation
            if operation_definition.get("instance") is True:
                for resource_type in operation_definition.get("resource", []):
                    path = f"{path_prefix}/{resource_type}/{{id}}/${op_name}"
                    openapi["paths"].setdefault(path, {})[http_method] = {
                        "summary": f"Instance-level FHIR Operation ${op_name}",
                        "tags": [resource_type],
                        
                        "parameters": oas_params.copy() + [{
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                            "description": "Resource ID"
                        }],
                        "responses": op_responses
                    }
                    if request_body:
                        openapi["paths"][path][http_method]["requestBody"] = request_body
            
        return openapi


    def build_parameters(params, location="query", format_param=None):
        result = []
        for param in params:
            if param.get("use", "") == "in" and param.get("name", "") != "resource":
                p = {
                    "name": param["name"],
                    "in": location,
                    "required": param.get("use", "") == "in" and param.get("min", 0) > 0,
                    "description": param.get("documentation", ""),
                    "schema": {
                        "type": fhir_to_openapi_type(param.get("type", "string"))[0]
                    }
                }
                result.append(p)
        if format_param:
            result.append(format_param)
        return result

    for rest in capability.get("rest", []):
        for op in rest.get("operation", []):
            openapi = add_operation(openapi, op)
            print(f"✅ Added OperationDefinition ${op.get("name", "")}.")
        for resource in rest.get("resource", []):
            for op in resource.get("operation", []):
                openapi = add_operation(openapi, op)
                print(f"✅ Added OperationDefinition {resource.get("type", "")}/${op.get("name", "")}.")

    return openapi

####
# END Operations
####

def extract_http_methods(extensions):
    http_method_urls = [
        "https://gematik.de/fhir/epa/StructureDefinition/http-method",
        "https://gematik.de/fhir/ti/StructureDefinition/http-method",
        "https://gematik.de/fhir/ti/StructureDefinition/extension-http-method"
    ]
    methods = []
    for ext in extensions:
        if ext.get("url") in http_method_urls:
            method = ext.get("valueCode", None)
            if method:
                methods.append(str(method).lower())
    return list(set(methods))


def extract_http_headers(extensions):
    header_header_urls = [
        "https://gematik.de/fhir/epa/StructureDefinition/http-header-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/http-header-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/extension-http-header"
    ]
    headers = []
    for ext in extensions:
        if ext.get("url") in header_header_urls:
            header = {}
            for sub in ext.get("extension", []):
                header[sub["url"]] = sub.get("valueString") or sub.get("valueBoolean")
            headers.append(header)
    return headers


def extract_http_response_info(extensions):
    http_response_info_urls = [
        "https://gematik.de/fhir/epa/StructureDefinition/http-response-info-extenstion",
        "https://gematik.de/fhir/epa/StructureDefinition/http-error-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/http-response-info-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/extension-http-response-info"
    ]
    errors = {}
    for ext in extensions:
        if ext.get("url") in http_response_info_urls:
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
    base_url_urls = [
        "https://gematik.de/fhir/epa/StructureDefinition/base-url-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/base-url-extenstion",
        "https://gematik.de/fhir/ti/StructureDefinition/extension-base-url"
    ]
    for ext in extensions:
        if ext.get("url") in base_url_urls:
            full_url = ext.get("valueString")
            if full_url:
                parsed = urlparse(full_url)
                host = f"{parsed.scheme}://{parsed.netloc}"
                path = parsed.path.rstrip("/")
                return host, path
    return None, ""


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


def build_responses(http_errors, formats, success_codes=["200"], success_description="Successful operation"):
    content = {"application/fhir+json": {"schema": {"type": "object"}}}
    for format in formats:
        content[str(format)] = {"schema":{"type":"object"}}
    responses = {}
    for success_code in success_codes:
        responses[success_code] = {
            "description": success_description,
            "content": content
        }

    for code, info in http_errors.items():
        if code != success_code:  # avoid overwriting the success code
            append_responses_code(responses=responses, code=code, info=info)
    return responses if responses else {
        "default": {
            "description": "Default error response"
        }
    }


def append_responses_code(responses, code, info):
    responses[code] = {"description": info.get("description", "")}



def build_request_body(formats: list) -> dict:
    """
    Erstellt ein requestBody-Objekt für OpenAPI auf Basis des FHIR-Resource-Typs
    und der unterstützten Formate (application/fhir+json, application/fhir+xml).
    """
    content = {"application/fhir+json": {"schema": {"type": "object"}}}
    for format in formats:
        content[str(format)] = {"schema":{"type":"object"}}
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
            "description": "Specify alternative response formats by their MIME-types (when a client is unable acccess accept: header)",
            "schema": {
                "type": "string",
                "enum": fhir_formats
            }
        }
    return None


def build_accept_header_param(fhir_formats):
    enum_values = fhir_formats if fhir_formats else ["*/*"]
    description = "The Accept header indicates the format in which the client wishes to receive the FHIR response."
    return {
        "name": "Accept",
        "in": "header",
        "required": False,
        "description": description,
        "schema": {
            "type": "string",
            "enum": enum_values
        }
    }


def build_pagination_query_params():
    return [
        {
            "name": "_count",
            "in": "query",
            "required": False,
            "description": "With _count, the client can specify the maximum number of elements to be included on one page of the response. This means the FHIR Data Service limits the result set to this maximum specified number. If no value for _count is provided, the default value set is 25.",
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
            "description": "This parameter controls whether and how the FHIR Data Service returns the total number of search results.",
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


def build_metadata_interaction(prefix_path, fhir_formats, parameters):
    paths = {}
    path = f"{prefix_path}/metadata"
    method = "get"
    responses = build_responses(http_errors={}, formats=fhir_formats, success_codes=["200"], success_description="OK")
    paths[path] = {
        method: {
            "summary": "Get CapabilityStatement",
            "tags": ["metadata"],
            "parameters": parameters,
            "responses": responses
        }
    }
    print(f"✅ Added metadata interaction.")
    return paths



def merge_custom_openapi(openapi, openapi_path):
    if not os.path.exists(openapi_path):
        print(f"⚠️ No custom OpenAPI file found at {openapi_path}")
        return openapi

    with open(openapi_path, "r", encoding="utf-8") as f:
        manual = yaml.safe_load(f)

    for path, methods in manual.get("paths", {}).items():
        if path not in openapi["paths"]:
            openapi["paths"][path] = {}
        openapi["paths"][path].update(methods)

    print(f"✅ Added custom OpenAPI {openapi_path}.")
    return openapi


def interaction_to_paths(config, resource_type, interaction_code, search_params, search_include, search_rev_include, http_errors,
                         prefix_path="", fhir_formats=None, extension=None):
    paths = {}

    base_parameters = []
    if not http_errors:
        http_errors = {}
    if extension:
        http_errors = extract_http_response_info(extension)
        _headers = extract_http_headers(extension)
        base_parameters.extend(build_header_params(_headers))

    format_param = None
    accept_header_param = None

    if config.with_format_parameter:
        format_param = build_format_query_param(fhir_formats)
    if config.with_accept_header:
        accept_header_param = build_accept_header_param(fhir_formats)


    def path_obj(method, summary, parameters, responses, request_body=None):
        obj = {
            method: {
                "summary": summary,
                "tags": [resource_type],
                "parameters": parameters,
                "responses": responses
            }
        }
        if request_body:
            obj[method]["requestBody"] = request_body
        return obj
        

    ###
    # GET /ResourceType/{rid}
    ###
    if interaction_code == "read":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description=f"{resource_type} successfully read")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = [{
            "name": "id", "in": "path", "required": True,
            "schema": { "type": "string" }, "description": "Resource ID"
        }]
        params += base_parameters
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
        paths[path] = path_obj("get", f"Read a specific {resource_type}", params, responses)

    ###
    # GET /ResourceType/{rid}/_history/
    ###
    elif interaction_code == "history-instance":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="History retrieved")
        path = f"{prefix_path}/{resource_type}/{{id}}/_history"
        params = [{
            "name": "id", "in": "path", "required": True,
            "schema": { "type": "string" }, "description": "Resource ID"
        }]
        params += base_parameters
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
        params.extend(build_pagination_query_params())
        paths[path] = path_obj("get", f"History of a specific {resource_type}", params, responses)

    ###
    # GET /ResourceType/{rid}/_history/{vid}
    ###
    elif interaction_code == "vread":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description=f"{resource_type} version read")
        path = f"{prefix_path}/{resource_type}/{{id}}/_history/{{vid}}"
        params = [
            {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Resource ID"},
            {"name": "vid", "in": "path", "required": True, "schema": {"type": "string"}, "description": "Version ID"}
        ] 
        params += base_parameters
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
        paths[path] = path_obj("get", f"Read version of {resource_type}", params, responses)

    ###
    # GET /ResourceType/{rid}/_history/
    ###
    elif interaction_code == "history-type":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="History for type retrieved")
        path = f"{prefix_path}/{resource_type}/_history"
        params = base_parameters + build_pagination_query_params()
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
        paths[path] = path_obj("get", f"History for all {resource_type}", params, responses)

    ###
    # GET /ResourceType/
    ###
    elif interaction_code == "search-type":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="Search successful")
        path = f"{prefix_path}/{resource_type}"
        params = base_parameters.copy()
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
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

    ###
    # POST /ResourceType/_search
    ###
    elif interaction_code == "search-type-post":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="Search successful")
        path = f"{prefix_path}/{resource_type}/_search"
        params = base_parameters.copy()
        if accept_header_param:
            params += [accept_header_param]
        if format_param:
            params += [format_param]
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
        paths[path] = path_obj("post", f"Search for {resource_type}", params, responses)

    ###
    # POST /ResourceType/
    ###
    elif interaction_code == "create":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["201"], success_description="Resource created")
        path = f"{prefix_path}/{resource_type}"
        request_body = build_request_body(fhir_formats or [])
        params = []
        if format_param:
            params += [format_param]
        paths[path] = path_obj("post", f"Create a new {resource_type}", params, responses, request_body)

    ###
    # PUT /ResourceType/{rid}
    ###
    elif interaction_code == "update":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="Resource updated")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        if format_param:
            params += [format_param]
        request_body = build_request_body(fhir_formats or [])
        paths[path] = path_obj("put", f"Update {resource_type} by ID", params, responses, request_body)

    
    ###
    # PUT /ResourceType?searchparameter=value
    ###
    elif interaction_code == "conditional_update":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200", "201"], success_description="Resource conditional update")
        path = f"{prefix_path}/{resource_type}/"
        request_body = build_request_body(fhir_formats or [])
        params = []
        if format_param:
            params += [format_param]
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
        paths[path] = path_obj("put", f"Conditional update: Create or Update a {resource_type} depending on search criteria", params, responses, request_body)

    ###
    # PATCH /ResourceType/{rid}
    ###
    elif interaction_code == "patch":
        responses = build_responses(http_errors, formats=fhir_formats, success_codes=["200"], success_description="Resource patched")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        if format_param:
            params += [format_param]
        request_body = build_request_body(fhir_formats or [])
        paths[path] = path_obj("patch", f"Patch {resource_type} by ID", params, responses, request_body)

    ###
    # DELETE /ResourceType/{rid}
    ###
    elif interaction_code == "delete":
        responses = build_responses(http_errors, formats=fhir_formats,  success_codes=["204"], success_description="Resource deleted")
        path = f"{prefix_path}/{resource_type}/{{id}}"
        params = [{
            "name": "id", "in": "path", "required": True,
            "schema": {"type": "string"}, "description": "Resource ID"
        }]
        if format_param:
            params += [format_param]
        params += base_parameters
        paths[path] = path_obj("delete", f"Delete {resource_type} by ID", params, responses)


    print(f"✅ Added interaction {interaction_code} for {resource_type}.")
    return paths


def capabilitystatement_to_openapi(path_resource, resource, config, cs_config):
    
    def update_openapi(openapi, new_paths):
        for path, item in new_paths.items():
            if path not in openapi["paths"]:
                openapi["paths"][path] = {}
            openapi["paths"][path].update(item)
        return openapi
    
    capability, filename = FHIRArtifactLoader.load_artifact(path=path_resource, resource=resource)

    if capability is None:
        return None

    openapi = {
        "openapi": "3.0.3",
        "info": {
            "title": capability.get("title"),
            "version": capability.get("version"),
            "description": capability.get("description")
        },
        "paths": {},
        "components": {
            "responses": {},
            "headers": {}
        }
    }

    extensions = capability.get("extension", [])

    host_url, path_prefix = extract_base_url_parts(extensions)
    if host_url:
        openapi["servers"] = [{
            "url": host_url
        }]
    else:
        path_prefix = ""
    
    fhir_formats = capability.get("format", [])

    ###
    # Add /metadata
    ###
    if config.with_metadata:
        base_fhir_parameters = []
        if config.with_accept_header:
            accept_header_param = build_accept_header_param(fhir_formats)
            if accept_header_param:
                base_fhir_parameters.append(accept_header_param)
        if config.with_format_parameter:
            format_query_param = build_format_query_param(fhir_formats)
            if format_query_param:
                base_fhir_parameters.append(format_query_param)
        new_path = build_metadata_interaction(prefix_path=path_prefix, fhir_formats=fhir_formats, parameters=base_fhir_parameters)
        openapi = update_openapi(openapi, new_path)

    ###
    # FHIR Interaction
    ###
    
    for rest in capability.get("rest", []):
        for res in rest.get("resource", []):
            resource_type = res.get("type")
            interactions = res.get("interaction", [])
            search_params = res.get("searchParam", [])
            search_include = res.get("searchInclude", [])
            search_rev_include = res.get("searchRevInclude", [])
            if res.get("conditionalUpdate", False):
                conditional_update = {"code":"conditional_update", "extension":[]}
                # Check for update interaction extension
                for interaction in interactions:
                    if interaction.get("code", "") == "update":
                        conditional_update["extension"].extend(interaction.get("extension", []))
                interactions.append(conditional_update)
            if cs_config.search_with_post:
                post_search = {"code":"post_search", "extension":[]}
                for interaction in interactions:
                    if interaction.get("code", "") == "search-type":
                        post_search = {"code":"search-type-post", "extension":[]}
                        post_search["extension"].extend(interaction.get("extension", []))
                        interactions.append(post_search)
                        break
            for interaction in interactions:
                interaction_code = interaction.get("code")
                interaction_extension = interaction.get("extension", [])
                new_paths = interaction_to_paths(
                    config,
                    resource_type,
                    interaction_code,
                    search_params,
                    search_include,
                    search_rev_include,
                    http_errors={},
                    prefix_path=path_prefix,
                    fhir_formats=fhir_formats,
                    extension=interaction_extension
                )
                openapi = update_openapi(openapi, new_paths)
                # for path, item in new_paths.items():
                #     if path not in openapi["paths"]:
                #         openapi["paths"][path] = {}
                #     openapi["paths"][path].update(item)


    ###
    # OperationDefinition-Dateien einlesen (hier Beispiel mit leeren Array)
    ###
    operation_definitions = load_operation_definitions_from_same_folder(path_resource)
    openapi = add_operations_from_capabilitystatement(
        config=config,
        openapi=openapi,
        capability=capability,
        operation_definitions=operation_definitions,
        formats=fhir_formats,
        header_params=[],
        http_errors={},
        path_prefix=path_prefix
    )

    ###
    # Loads the OpenAPI with manual operations.
    ###
    if cs_config.additional_openapi:
        openapi = merge_custom_openapi(openapi, cs_config.additional_openapi)

    ###
    # Set the global headers
    ###
    base_parameters = []
    headers = extract_http_headers(extensions)
    base_parameters.extend(build_header_params(headers))
    for path in openapi.get("paths", []):
        for method in openapi["paths"][path]:
            openapi["paths"][path][method].setdefault("parameters", [])[0:0] = base_parameters

    ###
    # Set the global errors
    ###
    base_http_errors = extract_http_response_info(extensions)
    for path in openapi.get("paths", []):
        for method in openapi["paths"][path]:
            openapi["paths"][path][method].setdefault("responses", [])
            for code, info in base_http_errors.items():
                    append_responses_code(responses=openapi["paths"][path][method]['responses'], code=code, info=info)
    

    return openapi


class OpenApiConverter(object):

    def __init__(self, config_file):
        self.config = OpenAPIConfig(config=config_file)

    def load(self):
        self.config.load()
        return self

    def convert(self):
        for c in self.config.capability_statement:
            openapi_spec = capabilitystatement_to_openapi(path_resource=self.config.path_resource, resource=c.input, config=self.config, cs_config=c)
            if openapi_spec is None:
                print(f"❌ Error: not foud {c.input} in {self.config.path_resource}")
            output = os.path.join(self.config.path_output, c.output)
            
            os.makedirs(os.path.dirname(output), exist_ok=True)
            with open(output, "w", encoding="utf-8") as f:
                _, ext = os.path.splitext(output.lower())
                if ext == ".json":
                    json.dump(openapi_spec, f, indent=2, ensure_ascii=False)
                elif ext in [".yaml", ".yml"]:
                    yaml.dump(openapi_spec, f, indent=2, sort_keys=False, allow_unicode=True, Dumper=NoAliasDumper)
                else:
                    raise ValueError(f"Unsupported file format: {ext}")


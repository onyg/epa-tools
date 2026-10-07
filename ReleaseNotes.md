# Release Notes

## 0.1.5

### Bug fix

OpenAPI generation now includes HTTP headers defined in resource interaction extensions for `create` (POST), `update` (PUT), `conditional update` (PUT) and `patch` (PATCH). Previously, these header parameters were missing from the generated OpenAPI document for these interactions.

### Example data

- Added a CapabilityStatement for the MHD Update Responder.
- Extended the example configuration to generate `epa-mhd-update-responder.openapi.json` and added the generated OpenAPI file.

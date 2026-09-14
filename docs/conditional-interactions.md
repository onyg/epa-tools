# Conditional Interactions

Der Converter unterscheidet normale FHIR-Interaktionen von
`conditional-create`, `conditional-read`, `conditional-update` und
`conditional-delete`. Conditional-Endpunkte werden aus den Resource-Feldern
`conditionalCreate`, `conditionalRead`, `conditionalUpdate` und
`conditionalDelete` abgeleitet. Eine normale Create-, Read-, Update- oder
Delete-Capability ist dafür nicht erforderlich.

`conditional_interaction_paths` erzeugt die bedingten Varianten.
Conditional Update und Delete verwenden `PUT /Resource` bzw.
`DELETE /Resource` und alle unter `rest.resource.searchParam` angegebenen
Suchparameter, unabhängig von deren `search-parameter-interaction`-Extensions.
Für normale Interaktionen gelten die expliziten Zuordnungen weiterhin.
Ohne definierte Suchparameter wird eine Warnung ausgegeben und der Endpunkt ohne
Suchkriterien beschrieben. Allgemeine konfigurierte Parameter wie `_format`
bleiben davon unabhängig.

Resource-level `extension-http-header` und `extension-http-response-info`
werden durch `resource_interaction_extensions` anhand ihrer verpflichtenden
`interaction`-Subextension zugeordnet. Fehlende oder unbekannte Zuordnungen
lösen `ValueError` aus. Bestehende Extensions auf Interaktionen, Operationen
und dem CapabilityStatement behalten ihre bisherige Verarbeitung.

Conditional Create verwendet `If-None-Exist`. Conditional Read verwendet je
nach Modus `If-None-Match` und/oder `If-Modified-Since`. Explizite
resource-level Angaben können die erzeugten Header und Responses überschreiben.
Diese Varianten teilen sich Methode und URL mit normalem Create bzw. Read.
OpenAPI kann pro Methode und Pfad nur eine Operation darstellen:
`merge_conditional_paths` ergänzt deshalb die gemeinsame Operation und speichert
die bedingten Parameter und Responses zusätzlich unter `x-fhir-conditional`.
Bei gleichzeitig vorhandener normaler Interaktion bleiben zusätzliche
Conditional-Header auf der gemeinsamen Operation optional; ihre bedingte
Pflichtangabe bleibt in `x-fhir-conditional` erhalten. Bei Response-Code-Konflikten
bleibt die normale Response auf der gemeinsamen Operation erhalten, die bedingte
Beschreibung steht in `x-fhir-conditional`.

Die neue Vorgabe ersetzt gezielt das frühere Conditional-Update-Verhalten:
kein abschließender Slash und keine Übernahme normaler Update-Extensions.
Alle definierten Suchparameter werden bei Conditional Update und Delete übernommen. Die Regressionstests vergleichen bei den zwei
betroffenen Patient-Beispielen alle anderen Operationen mit der vorherigen
Ausgabe. Für die übrigen sieben Beispiele bleibt der vollständige Vergleich
bestehen, jeweils mit Standard- und erweiterter Konfiguration.

Tests ausführen:

```sh
PYTHONPATH=src python -m unittest discover -s tests -v
```

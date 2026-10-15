# API pública

Todos los endpoints son whitelisted de Frappe y exigen sesión autenticada. Los
permisos se vuelven a validar en el servidor.

## Contexto reutilizable

`POST bimap_data_engine.api.integration.create_editor_context`

```json
{
  "doctype": "Quotation",
  "mode": "Edit",
  "allowed_fields": ["transaction_date", "valid_till"],
  "filters": {"docstatus": 0},
  "source_app": "bimap_document_engine"
}
```

La respuesta incluye `context_id` y una ruta Desk. El contexto dura ocho horas,
pertenece al usuario que lo creó y sólo puede restringir permisos nativos. Las
APIs de metadata, consulta, preview, aplicación y jobs aceptan `context_id`.

Los modos generan rutas distintas: `Edit`/`Export` abren el editor y `Import`
abre el importador. El cliente incluido globalmente permite crear el contexto y
navegar con una sola llamada:

```js
await window.BimapDataEngineIntegration.open({
  doctype: "Sales Order",
  mode: "Edit",
  allowedFields: ["delivery_date"],
  filters: { docstatus: 0 },
  sourceApp: "bimap_document_engine",
});
```

## Lectura y cambios

- `GET bimap_data_engine.api.metadata.get_schema`
- `GET bimap_data_engine.api.records.list_records`
- `GET bimap_data_engine.api.records.list_child_rows`
- `POST bimap_data_engine.api.changes.preview_changes`
- `POST bimap_data_engine.api.changes.apply_changes`
- `POST bimap_data_engine.api.jobs.create_job`
- `GET bimap_data_engine.api.jobs.get_job`
- `POST bimap_data_engine.api.jobs.cancel_job`
- `POST bimap_data_engine.api.jobs.resume_job`

Las operaciones admitidas son `set`, `clear`, `add_child`, `update_child` y
`delete_child`. `delete_child` exige `confirmed=true`.

## Archivos, sesiones y perfiles

- `POST bimap_data_engine.api.imports.inspect_file`
- `POST bimap_data_engine.api.imports.suggest`
- `POST bimap_data_engine.api.imports.save_profile`
- `GET bimap_data_engine.api.imports.get_profile`
- `POST bimap_data_engine.api.imports.save_work_session`
- `GET bimap_data_engine.api.imports.get_work_session`

## Plan multihoja

```json
{
  "nodes": [{
    "id": "orders",
    "doctype": "Sales Order",
    "sheet": "Orders",
    "external_key": "Order ID",
    "mapping": [{"source": "Customer", "target": "customer"}],
    "defaults": {"company": "My Company"},
    "submit": false,
    "children": [{
      "table_field": "items",
      "sheet": "Lines",
      "parent_key": "Order ID",
      "mapping": [{"source": "Item", "target": "item_code"}]
    }],
    "references": [{
      "source": "Customer External ID",
      "target": "customer",
      "node": "customers"
    }]
  }]
}
```

`preview_import` produce registros y errores. `start_import` rechaza planes con
errores salvo `valid_only=1`. Los resultados se descargan con
`GET bimap_data_engine.api.exports.download_job_results`.

Cuando existe `context_id`, tanto `preview_import` como `start_import` vuelven a
validar DocType y campos; no se confía en el mapeo recibido del navegador.

`submit: true` sólo se acepta en DocTypes enviables y exige permiso `submit`.
El preview ejecuta el envío dentro de rollback y el job lo ejecuta realmente.

Un nodo puede usar un origen ERPNext existente:

```json
{
  "id": "invoices",
  "doctype": "Sales Invoice",
  "sheet": "Invoices",
  "external_key": "External ID",
  "mapping": [],
  "native_source": {"doctype": "Delivery Note", "source": "Delivery Note"}
}
```

Pares registrados: Quotation→Sales Order, Sales Order→Delivery Note/Sales Invoice,
Delivery Note→Sales Invoice, Supplier Quotation→Purchase Order, Purchase Order→
Purchase Receipt/Purchase Invoice y Purchase Receipt→Purchase Invoice.

## Partidas en documentos abiertos

- `POST bimap_data_engine.api.integration.map_document_lines`
- `POST bimap_data_engine.api.integration.prepare_document_lines`

El segundo endpoint recibe encabezado, filas actuales, filas externas, política de
combinación y campos de coincidencia. Siempre revierte su preparación nativa.

## CFDI

- `POST bimap_data_engine.api.cfdi.inspect_cfdi`
- `POST bimap_data_engine.api.cfdi.preview_document`
- `POST bimap_data_engine.api.cfdi.create_draft`

`create_draft` sólo acepta un preview válido y crea Purchase Invoice o uno/más
Payment Entry en borrador. Cada creación queda auditada.

## Exportación

`GET bimap_data_engine.api.exports.download_records` genera XLSX con hasta
25,000 filas y aplica permisos, campos y filtros del contexto.

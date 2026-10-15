# Arquitectura implementada

## Límites

`bimap_data_engine` posee las sesiones, mapeos, conjuntos de cambios, trabajos y
auditoría. No posee reglas comerciales de ERPNext ni duplica el motor documental.

```text
Spreadsheet Widget / API pública
              |
       Session + Mapping
              |
 Metadata -> Validation -> Change / Import Plan
              |                    |
       Preview seguro       Dependency Graph
              \                    /
               Batch Orchestrator
                      |
             Frappe Document API
                      |
                   ERPNext
```

## Subsistemas

### Metadata Engine

Entrega metadatos sanitizados y campos legibles/escribibles para el usuario
actual. Nunca expone un campo sólo porque exista en SQL.

### Query Engine

Consulta con `frappe.get_list`, páginas con cursor estable y selección explícita
de columnas. Cada fila incluye `name` y `modified` como identidad/snapshot.

### Change Engine

Contrato mínimo de una operación:

```json
{
  "operation": "set",
  "doctype": "Item",
  "name": "ITEM-001",
  "fieldname": "description",
  "original": "Anterior",
  "value": "Nueva",
  "snapshot_modified": "2026-10-13 10:00:00.000000"
}
```

Operaciones implementadas: `set`, `clear`, `add_child`, `update_child` y
`delete_child`. La ausencia de una celda o fila no genera una operación.

Vista previa y aplicación comparten el mismo validador. Al aplicar se vuelve a
leer y bloquear el documento, se compara el snapshot y el valor original, se
asignan únicamente campos aprobados y se ejecuta `save()`.

### Import Engine

Normaliza hojas a documentos propuestos, valida links y construye un grafo de
dependencias. Cada nodo usa una clave de operación idempotente. Tablas hijas se
persisten con el padre, nunca como documentos independientes.

La especificación relaciona cada nodo con una hoja, una clave externa, un mapeo,
predeterminados, tablas hijas y referencias a otros nodos. El orden topológico se
materializa en `BIMAP Data Job Record`; una referencia sólo se resuelve contra un
registro previo en estado `Success`. Un maestro ausente no se crea salvo que sea
un nodo explícito autorizado del mismo plan.

Cada nodo puede declarar `submit: true`. En ese caso el preview ejecuta
`insert()` y `submit()` dentro de un savepoint que siempre se revierte; la
ejecución real repite el mismo ciclo bajo el usuario solicitante. El modo por
defecto continúa siendo borrador.

Para documentos ligados ya existentes, `native_source` selecciona un mapeador
registrado que llama las funciones oficiales de ERPNext. No se reconstruyen a
mano campos como `dn_detail`, `sales_order` o `purchase_receipt_item`.

### Batch Orchestrator

`BIMAP Data Job` conserva estado, solicitante, `operation_id` y contadores.
`BIMAP Data Job Record` conserva el conjunto de cambios y resultado de cada
documento. Cada lote confirma cambios, auditoría y checkpoint en una misma
transacción. La reanudación omite registros `Success`; el reintento de fallos es
explícito. La cancelación se comprueba entre lotes, nunca en medio de un `save()`.

### Spreadsheet Adapter

Traduce entre el store BIMAP y Univer. Fórmulas son una capa de edición; sólo sus
resultados materializados y validados entran en un plan de cambios. El adaptador
de archivos está separado del grid. Las celdas editadas materializan `set`; una
celda vacía se reporta como ignorada y sólo el control separado de limpieza crea
una operación `clear`.

El preview masivo también es un job persistente. Conserva el libro/especificación,
valida documentos por lotes sin insertarlos y pagina resultados de 500 en 500.
En la UI, las incidencias tienen hoja, fila, columna y campo destino; `Solo errores`
oculta filas válidas sin eliminarlas y las ediciones disparan revalidación.

### Integración de partidas abiertas

`prepare_document_lines` combina las filas existentes y externas mediante
`append`, `consolidate`, `update` o `reject_duplicates`. Prepara el documento
completo con ERPNext dentro de rollback y devuelve filas/totales al host. El host
decide cuándo guardar; el Data Engine no persiste el documento abierto.

### Fuentes fiscales CFDI

El parser XML está aislado de la importación universal. Rechaza DTD/entidades,
no usa red y limita el archivo a 5 MB. Un adaptador fiscal traduce los hechos a
Purchase Invoice o Payment Entry, pero las cuentas, artículos, impuestos y tipos
de cambio siguen perteneciendo a ERPNext. El total calculado debe coincidir con
el XML; de otro modo el preview bloquea la creación.

## Integración pública

La API acepta contexto opcional:

```json
{
  "doctype": "Sales Order",
  "source_app": "bimap_document_engine",
  "mode": "edit",
  "allowed_fields": ["delivery_date"]
}
```

`allowed_fields` restringe todavía más los permisos nativos; nunca los amplía.
La invocación crea un `BIMAP Data Context` temporal, ligado al usuario y validado
Los contextos de importación se revalidan sobre la especificación y el plan ya
materializado. `window.BimapDataEngineIntegration.open(...)` es el cliente único
para que cualquier host BIMAP abra las pantallas sin copiar su implementación.

## Extensión

El núcleo usa metadatos. Los comportamientos especiales se registran mediante
hooks (`bimap_data_engine_adapters`) y deben declarar por qué el flujo genérico no
es suficiente, sus efectos secundarios y sus pruebas.

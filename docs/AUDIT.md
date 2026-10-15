# Auditoría técnica inicial

Fecha de corte: 2026-10-13.

## Entorno confirmado

- Frappe `15.106.0` y ERPNext `15.105.0`.
- Sitio de desarrollo BIMAP: `mi-sitio.local`.
- `alcorsa.local` sólo contiene Frappe y ERPNext y queda fuera de las pruebas.
- Las aplicaciones son repositorios Git independientes; el bench no es un
  repositorio monolítico.
- `bimap_document_engine` y `tests/bimap_e2e` contienen cambios locales previos.
  La integración posterior añadió únicamente una acción de grid en la pantalla
  de Pedido; se preservaron los demás cambios locales.

## Correspondencia de repositorios solicitados

| Solicitado | Ubicación real | Observación |
| --- | --- | --- |
| `bimap_core` | `apps/bimap_core` | Biblioteca y APIs compartidas. |
| `bimap_ui_next` | `apps/bimap_ui_next` | Shell/UI de nueva generación. |
| `bimap_document_engine` | `apps/bimap_document_engine` | Motor documental y pruebas maduras. |
| `bimap_pedidos_next` | `apps/bimap_pedidos` + UI Next | No existe con el nombre solicitado. |
| `bimap_ventas` | `apps/bimap_ventas` | Publicación de páginas comerciales. |
| `bimap_seguridad` | `apps/bimap_seguridad` | Filtros y política comercial. |
| `bimap_e2e_tests` | `tests/bimap_e2e` | Repositorio independiente con cambios locales. |
| `bimap_documentacion` | `bimap_documentacion` y `docs` | Repositorio y copia de consulta. |

También existe `bimap_trazabilidad`; se auditó porque su patrón de consultas y
permisos puede ser relevante para el motor.

## Hallazgos reutilizables

### Frappe y ERPNext

- `frappe.get_meta()` y `Meta.get_permitted_fieldnames()` son la base correcta
  para descubrimiento y permisos por nivel de campo.
- `frappe.get_list()` aplica permisos, condiciones de consulta y User Permissions.
- `Document.check_permission()`, `insert()` y `save()` preservan validaciones y
  eventos nativos.
- Data Import ya contiene parsing CSV/XLSX, exportación, agrupación padre/hijo,
  trabajos de fondo, progreso, logs, reintento y lotes configurables.
- Data Import actualiza con `Document.update()` y no expresa la diferencia entre
  sin cambio, limpiar y eliminar. Tampoco implementa snapshot optimista por
  documento ni dependencias entre varios DocTypes. Por eso se reutilizarán piezas
  puntuales, no el flujo completo.

### BIMAP

- `bimap_document_engine` demuestra el patrón correcto de concurrencia: permiso
  documental, lock `FOR UPDATE`, comparación de `modified` y `doc.save()`.
- Su registro extensible por hooks evita ramas centrales por cada dominio.
- Su mecanismo de idempotencia enlaza usuario, perfil, clave y hash de payload en
  una operación transaccional.
- `bimap_seguridad` añade filtros `permission_query_conditions`; usar
  `frappe.get_list()` permite que el Data Engine los herede.
- `bimap_core` tiene buscadores y utilidades comerciales útiles, pero el Data
  Engine no debe depender de APIs sesgadas a `Sales Order`.
- Los contratos UI oficiales definen Definition, Store, Widget Context, Services,
  Capabilities y eventos. El editor se integrará como widget/servicio, sin copiarse
  dentro de cada documento.

## Riesgos y decisiones

| Riesgo | Tratamiento inicial |
| --- | --- |
| Sobrescritura silenciosa | Snapshot `modified` obligatorio y lock al aplicar. |
| Campos no autorizados | Allowlist dinámica de metadatos y permlevel de escritura. |
| Vacío ambiguo | Operaciones explícitas; `clear` es distinto de `set`. |
| Pérdida de hijos | `name` persistente y operaciones por fila; ausencia no elimina. |
| Reglas no visibles en metadata | Guardar mediante Document API y adaptadores explícitos. |
| 25,000 artículos | Consulta paginada, selección de campos y jobs por lotes. |
| Cambios locales ajenos | No tocar repositorios sucios; integración por API/hook. |
| Licencia del grid | Univer OSS como base; capacidades no OSS tras adaptador. |

## Evaluación de hoja de cálculo

- Handsontable requiere licencia comercial para producción comercial.
- Jspreadsheet Pro y sus extensiones requieren licencia; XLSX y fórmulas avanzadas
  forman parte de planes comerciales.
- Univer publica su núcleo bajo Apache-2.0 y ofrece grid, fórmulas, filtros y
  búsqueda. Algunas capacidades avanzadas se anuncian fuera del núcleo OSS.

Decisión: prototipar con paquetes OSS de Univer fijados por versión. El acceso a
XLSX/CSV se encapsulará en un adaptador para poder usar parsing servidor de Frappe
o sustituir el proveedor sin cambiar el Change Engine.

## Cierre de riesgos medidos

La auditoría inicial se contrastó después con implementación y pruebas. El flujo
completo de 25,000 Items pasó con lotes y commits reales; Item Price, Sales Order,
Purchase Order, dependencias multi-DocType, recuperación y concurrencia tienen
cobertura automatizada. Los límites vigentes se mantienen en
`COMPATIBILITY.md` y no se desplegó ni probó sobre producción.

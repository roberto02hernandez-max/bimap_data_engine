# BIMAP Data Engine

Motor universal de importación y edición masiva para ERPNext. La aplicación es
independiente del motor documental y conserva a ERPNext como autoridad de datos,
permisos, validaciones y efectos derivados.

## Estado

El motor cubre edición parcial de padres e hijos, importación CSV/XLSX multihoja,
dependencias entre DocTypes, preview masivo persistente, jobs reanudables y
auditoría. La hoja muestra por defecto sólo filas con errores, marca la celda y
revalida correcciones sin obligar a descargar otro archivo.

Los documentos comerciales usan preparación nativa de ERPNext. Las conversiones
Quotation→Sales Order, Sales Order→Delivery Note/Sales Invoice,
Delivery Note→Sales Invoice y sus equivalentes de compras conservan referencias
nativas. La ejecución puede crear borradores o, con confirmación y permiso
`submit`, enviar documentos y producir sus efectos contables/de inventario.

También se pueden agregar cientos de partidas desde CSV/XLSX a un documento BIMAP
abierto. CFDI 4.0 de proveedor y Pagos 2.0 cuentan con preview especializado,
UUID idempotente y creación de Purchase Invoice/Payment Entry en borrador.

El Caso A de 25,000 Items pasó con cero fallos y conservación comprobada de los
campos y tablas hijas no seleccionados.

- Editor: `/app/bimap-data-engine`
- Importador: `/app/bimap-data-import`
- [Instalación](docs/INSTALLATION.md)
- [Guía de usuario](docs/USER_GUIDE.md)
- [API pública](docs/PUBLIC_API.md)
- [Compatibilidad y limitaciones](docs/COMPATIBILITY.md)

## Principios no negociables

- Aplicar solamente operaciones explícitas (`set`, `clear`, `add_child`,
  `update_child`, `delete_child`).
- Nunca interpretar una celda vacía como eliminación.
- Identificar filas hijas existentes por su `name` persistente.
- Usar `insert()` y `save()` de Frappe; no saltar validaciones con escrituras SQL.
- Verificar permisos en servidor y detectar snapshots obsoletos antes de guardar.
- Procesar volúmenes grandes fuera de la petición HTTP.

## Desarrollo local

```bash
bench --site mi-sitio.local install-app bimap_data_engine
bench --site mi-sitio.local run-tests --app bimap_data_engine
```

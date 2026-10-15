# Plan de implementación

## Fase 0 — Auditoría y esqueleto

- [x] Inventariar repositorios y sitios.
- [x] Contrastar documentación con implementación.
- [x] Evaluar patrones de permisos, concurrencia e idempotencia.
- [x] Evaluar licencias de grids.
- [x] Crear app independiente y documentación persistente.
- [x] Instalar la app sólo en `mi-sitio.local`.

## Fase 1 — Corte vertical: `Item.description`

- [x] Metadata API con campos permitidos.
- [x] Consulta paginada de Item con snapshot.
- [x] Contrato explícito `set`/`clear`.
- [x] Vista previa estructural sin escritura.
- [x] Aplicación parcial con lock y control de concurrencia.
- [x] Auditoría transaccional de cambio.
- [x] Pruebas de permisos, preview, conflicto y preservación de campos.
- [x] Validación profunda de reglas del documento durante el preview.
- [x] Widget de hoja de cálculo para este flujo.
- [x] Prueba de volumen de 25,000 artículos.

## Fase 2 — `Item Barcodes`

- [x] Consultar tabla hija con `name` persistente.
- [x] Agregar y modificar filas sin reemplazar la colección.
- [x] Eliminación explícita y confirmada.
- [x] Pruebas de conservación de filas no seleccionadas.
- [x] Integrar estas operaciones en el widget.

## Fase 3 — Sesiones, grid y archivos

- [x] Sesiones persistentes y store.
- [x] Adaptador Univer OSS para consulta y cambios padre.
- [x] CSV y XLSX detrás de adaptador.
- [x] Mapeos manuales, sugeridos y reutilizables.

## Fase 4 — Jobs universales

- [x] Núcleo de jobs, checkpoints, idempotencia, cancelación y reanudación.
- [x] Progreso, cancelación y aplicación masiva desde UI.
- [x] Exportación de resultados y errores.
- [x] Reanudación desde UI.
- [x] Resultados descargables y ejecución parcial válida.
- [x] `Item Price` y política de atributos estructurales.

## Fase 5 — Importación y dependencias

- [x] Grafo multi-DocType y referencias externas.
- [x] Sales Order y Purchase Order con hijos.
- [x] Política explícita para maestros ausentes.

## Fase 6 — Integración y aceptación

- [x] API de contexto restringido y pantallas generales.
- [x] Cliente global para acciones visuales del motor documental, sin duplicar el editor.
- [x] Caso A de 25,000 actualizaciones; B–H tienen cobertura automatizada.
- [x] Guías de instalación/usuario y matriz de compatibilidad.

## Fase 7 — Preview operativo y documentos nativos

- [x] Preview persistente para 500+ documentos sin escrituras destino.
- [x] Vista embebida `Solo errores`, celda marcada y revalidación incremental.
- [x] Conversiones nativas ventas/compras con referencias ERPNext.
- [x] Modos explícitos Borrador/Enviar y simulación de submit en preview.
- [x] Importación de partidas CSV/XLSX dentro de Pedido BIMAP abierto.
- [x] Prueba Delivery Note→Sales Invoice: CxC/GL sin doble salida de inventario.

## Fase 8 — Fuentes fiscales

- [x] Parser seguro CFDI 4.0 y Pagos 2.0.
- [x] Purchase Invoice nativa, UUID único, total fiscal y auditoría.
- [x] Payment Entry conciliado por UUID/saldo y clave idempotente por pago.
- [x] Flujo visual CFDI probado en navegador.
- [ ] Verificación de sello/estado SAT mediante proveedor externo autorizado.

# Registro de progreso

## 2026-10-13

- Se conectó `Importar Excel` al grid vigente del Motor Documental mediante un
  contrato neutral: el archivo se mapea, combina y prepara con ERPNext, actualiza
  la captura abierta y no guarda hasta la acción normal del usuario. El smoke real
  verificó botón, modal, assets y ausencia de errores de página.
- Se añadieron modos explícitos `Borrador` y `Enviar con ERPNext`. El segundo exige
  permiso `submit`, simula insert/submit dentro del rollback de preview y durante
  ejecución llama el ciclo nativo real. Una prueba con stock confirmó que
  Delivery Note→Sales Invoice enviada creó GL/CxC, conservó `dn_detail` y generó
  cero movimientos de inventario adicionales.
- El flujo CFDI especializado prepara y crea Purchase Invoice en borrador, conserva
  Serie/Folio, archivo y UUID único, audita la creación y bloquea duplicados o
  diferencias entre total ERPNext/XML. No crea maestros faltantes.
- Pagos 2.0 resuelve Purchase Invoices enviadas por UUID, verifica saldo, empresa,
  proveedor y suma asignada, usa `get_payment_entry` de ERPNext y crea Payment Entry
  en borrador con clave idempotente UUID+número de pago.
- Se añadieron campos administrados `bimap_cfdi_*` mediante patch/after_migrate y
  un smoke CFDI en navegador que verificó carga XML, preview válido, acción de
  creación y bloqueo visual en borrador.

- Se inició la siguiente etapa del objetivo: el preview devuelve ahora incidencias
  estructuradas con hoja, fila, columna de origen, campo destino, severidad y código,
  manteniendo compatibilidad con el contrato anterior.
- La importación activa por defecto la vista `Solo errores`: las filas válidas se
  ocultan sin eliminarse, la celda identificada se colorea y cada incidencia permite
  enfocar su posición dentro de la hoja embebida. `Todos` restaura el lote completo.
- Los errores sin campo inequívoco marcan la fila completa; los errores de tablas
  hijas sin padre señalan directamente la clave de relación.
- Después del primer preview, cualquier edición en la hoja dispara revalidación con
  debounce. En nodos padres independientes se envían sólo las filas modificadas y
  el resultado parcial se fusiona con el plan completo; una fila corregida desaparece
  de `Solo errores`. Los grafos con tablas hijas vuelven temporalmente al preview
  completo para no dejar desactualizado al padre anterior al mover una partida.
- Las claves externas vacías o duplicadas dejaron de abortar todo el preview: ahora
  son incidencias dirigidas a la celda exacta y se pueden corregir en la misma hoja.
- Se añadió el tipo de trabajo persistente `Preview`. A partir de 250 documentos la
  UI guarda la solicitud, valida por lotes bajo el usuario solicitante, muestra avance,
  pagina los resultados de 500 en 500 y reconstruye el plan sin crear documentos.
- Las tablas hijas se validan junto con su padre y una unidad estructural separada
  reporta filas huérfanas una sola vez. El payload grande del preview no se devuelve
  durante el polling.
- Una prueba persistente procesó 500 documentos en lotes de 100, obtuvo 500 éxitos
  técnicos y confirmó cero escrituras en el DocType destino.
- Se creó el adaptador de fuente CFDI con parser XML endurecido (sin red, DTD ni
  entidades), límite de 5 MB y normalización de CFDI 4.0, conceptos, impuestos,
  relaciones, Timbre Fiscal y Complemento de Pagos 2.0. Produce el mismo contrato
  multihoja que CSV/XLSX; la UI ya acepta XML y propone Purchase Invoice o Payment
  Entry según el tipo de comprobante.
- Los adaptadores comerciales nativos abarcan ahora Quotation, Sales Order, Delivery
  Note, Sales Invoice, Purchase Order, Purchase Receipt y Purchase Invoice.
- Se añadió un registro explícito de conversiones nativas ERPNext para cotización→
  pedido, pedido→remisión/factura, remisión→factura y sus equivalentes de compras.
  Un nodo `native_source` parte del documento ERPNext existente en vez de copiar sus
  campos. La prueba Quotation→Sales Order conservó `prevdoc_docname` y la cantidad.
- Se añadió el contrato de `Importar partidas` para documentos aún no guardados:
  recibe encabezado, filas existentes e importadas, aplica append/consolidate/update/
  reject_duplicates, prepara el documento completo con ERPNext dentro de un savepoint
  y devuelve filas y totales sin persistir. El cliente global puede reemplazar la
  cuadrícula abierta conservando el guardado como decisión posterior del usuario.
- La compilación final de assets terminó correctamente y las 58 pruebas del app
  pasaron. Tres smoke contra un servidor temporal verificaron el importador
  universal con persistencia real, el modal de partidas del Motor Documental y el
  flujo CFDI; los tres terminaron sin errores de página. Los 404 observados fueron
  únicamente intentos de Socket.IO porque el servidor temporal fue sólo WSGI.

- Se creó el objetivo persistente del proyecto.
- Se localizaron los ocho repositorios solicitados bajo nombres/ubicaciones reales.
- Se preservaron cambios locales existentes en motor documental y E2E.
- Se confirmó `mi-sitio.local` como sitio BIMAP de desarrollo.
- Se auditó Data Import nativo y los patrones BIMAP de permisos, idempotencia y
  concurrencia.
- Se seleccionó Univer OSS como base provisional por licencia Apache-2.0, con un
  adaptador independiente para archivos y funciones no OSS.
- Se creó `bimap_data_engine` y se registró en el entorno Python del bench.
- Se instaló sólo en `mi-sitio.local`; se habilitaron pruebas en ese sitio local.
- Se implementaron API de esquema, consulta paginada y consulta de tablas hijas.
- Se implementó Change Engine con `set`, `clear`, `add_child`, `update_child` y
  `delete_child`; las bajas exigen confirmación y las filas existentes usan `name`.
- Se implementó control optimista con snapshot `modified`, comparación del valor
  original y lock `FOR UPDATE` antes del `save()` nativo.
- Se creó auditoría transaccional `BIMAP Data Change Log`.
- El preview ejecuta la tubería nativa de validación del documento dentro de un
  savepoint que siempre se revierte.
- Se integró Univer OSS 1.0.4 en una página Desk genérica, con identidad y snapshot
  ocultos/protegidos, encabezado protegido y materialización de cambios explícitos.
- El smoke E2E real de navegador cargó la página, editó `Item.description`, mostró
  preview, aplicó y verificó el valor en base de datos sin errores de página.
- Se implementaron trabajos persistentes por documento, `operation_id` estable,
  checkpoints atómicos por lote, cancelación, reanudación y reintento selectivo.
- La pantalla consulta en páginas de 500 hasta un máximo configurable de 25,000,
  divide el preview en bloques y deriva automáticamente más de 500 cambios al job;
  muestra progreso y permite solicitar cancelación.
- Evidencia: 14 pruebas de integración satisfactorias en 2.056 s, cubriendo
  preview sin escritura, cambio exclusivo de descripción, conflicto, campo de
  sistema, usuario sin permiso, lectura/alta/cambio/baja de códigos de barras,
  conservación de filas, auditoría, idempotencia de jobs, lote mixto, reintento y
  cancelación.
- El sitio local contiene 23,862 artículos; por ello la prueba exigida de 25,000
  todavía no se declara cumplida. Se ejecutará con fixtures sintéticos aislados y
  limpieza verificable cuando el flujo masivo quede conectado a la UI.
- Riesgo medido: el bundle de desarrollo de Univer ronda 20 MB sin minificar. Se
  requiere división/carga diferida y medición de producción antes de aceptación.
- El smoke E2E se repitió después de conectar paginación y jobs: HTTP, montaje,
  persistencia y ausencia de errores de página volvieron a resultar correctos.
- Se implementaron parser CSV/XLSX multihoja, sugerencias de mapeo, perfiles
  reutilizables, transformaciones declarativas y sesiones privadas reanudables.
- El Import Engine agrupa hijos con su padre, rechaza huérfanos, ordena un grafo
  de dependencias, resuelve claves externas y guarda con `Document.insert()`.
- Sales Order y Purchase Order con dos partidas cada uno se crearon en pruebas
  mediante adaptadores explícitos que llaman lógica nativa de ERPNext.
- Se cubrió `Item Price.price_list_rate` verificando que lista, moneda, UOM e Item
  permanecen intactos. Los cambios estructurales de variantes quedan bloqueados.
- Se añadió contexto público ligado a usuario, campos y filtros, exportación XLSX
  y descarga CSV de resultados/errores por registro.
- El E2E de tabla hija modifica un barcode, agrega otro y conserva el no
  seleccionado. Un segundo E2E abre un CSV, mapea, previsualiza, ejecuta un job y
  comprueba el Item creado.
- Evidencia actual: 36 pruebas Python satisfactorias en 4.260 s y dos smoke E2E
  satisfactorios. El Caso G interrumpe tras el primer checkpoint y reanuda con
  intentos `[1, 1, 1]`, sin repetir el documento confirmado.
- El Caso A se ejecutó con 25,000 Items sintéticos aislados, lotes reales de 100
  y commits por checkpoint: 25,000 éxitos, cero fallos, 25,000 descripciones y
  filas de auditoría, campos no objetivo y tablas hijas sin cambios. El job tardó
  764.522 s, el recorrido completo 779.926 s y el RSS máximo fue 371.07 MB.
  La limpieza posterior dejó cero Items, jobs y auditorías sintéticas.
- La UI lista trabajos recientes y permite observar, cancelar, reanudar y optar
  explícitamente por reintentar fallos. También expone una acción `clear`
  separada: vaciar una celda continúa sin significar eliminación.
- La auditoría de `add_child` conserva ahora el `name` persistente asignado a la
  nueva fila hija.
- Los contextos públicos `Import` se validan tanto sobre la especificación como
  sobre el plan materializado; un plan manipulado no puede ampliar DocTypes o
  campos. Se añadió un cliente global para abrir Edit, Import o Export desde
  otros módulos sin copiar el editor.
- La compilación de producción redujo el bundle Univer de aproximadamente 20 MB
  a 12.06 MB y lo mantiene bajo carga diferida. Los dos smoke E2E pasaron de
  nuevo contra ese artefacto de producción.
- Evidencia final: 38 pruebas Python satisfactorias en 4.598 s. El smoke del
  editor verificó `set`, `clear`, controles de reanudación, actualización/alta
  de barcodes y conservación de filas; el smoke del importador verificó preview,
  job y documento creado. Ambos terminaron sin errores de página y su limpieza
  dejó cero Items, archivos y fixtures de rendimiento residuales.

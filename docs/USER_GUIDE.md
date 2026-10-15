# Guía de usuario

## Editar registros existentes

1. Abra `/app/bimap-data-engine`.
2. Indique el DocType, cargue sus campos y seleccione solamente las columnas que
   necesita.
3. Aplique filtros JSON y un máximo de registros; la consulta pagina en bloques
   de 500.
4. Edite en la hoja y ejecute **Vista previa**.
5. Revise errores/conflictos y confirme **Aplicar cambios**.

Una celda vacía se ignora. No significa limpiar. Para limpiar, seleccione
**Documento a limpiar**, **Campo a limpiar** y pulse **Marcar limpieza
explícita**. La instrucción aparece como una operación `clear` separada y se
valida en el preview.

Con más de 500 cambios, la pantalla crea un job, muestra su progreso y permite
solicitar cancelación. Al terminar se puede descargar un CSV con el resultado de
cada documento.

En **Trabajos recientes** se puede volver a observar un job cancelado o fallido
y pulsar **Reanudar**. Active **Reintentar registros fallidos** sólo cuando haya
corregido la causa; los registros ya confirmados como `Success` nunca se repiten.

## Tablas hijas

1. Cargue el esquema del DocType padre.
2. Seleccione una tabla hija e indique el nombre del documento padre.
3. Abra la tabla. Las filas existentes conservan internamente su `name` de
   Frappe, aunque la columna esté oculta.
4. Edite valores existentes o escriba en una fila vacía para agregarla.
5. Escriba/marque `true` en **Eliminar** para una baja explícita.
6. Ejecute preview y confirme.

Las filas no seleccionadas nunca se eliminan.

## Guardar y continuar una sesión

Use **Guardar sesión** para conservar DocType, columnas, filtros, tabla hija y
cambios pendientes. **Continuar sesión** vuelve a consultar datos actuales y
reaplica los cambios pendientes sobre un snapshot nuevo. Las sesiones creadas
desde un contexto restringido sólo se abren dentro del mismo contexto.

## Importar CSV o XLSX

1. Abra `/app/bimap-data-import` y elija primero el área en español: **Ventas**,
   **Compras**, **Almacén e inventario** o **Catálogos**.
2. Elija el documento permitido para su usuario.
3. Pulse **Crear plantilla aquí**. BIMAP genera los encabezados a partir de la
   metadata real de ERPNext. La barra **Columnas de la hoja** activa y bloquea los
   campos obligatorios; los opcionales agregan o quitan inmediatamente su columna.
   Los marcados con `*` son obligatorios. Puede escribir o pegar filas directamente
   en la hoja embebida, que utiliza la mayor parte de la pantalla.
4. Los documentos con partidas se capturan en una sola hoja plana: cada fila es
   un producto y repite **Folio externo**, cliente/proveedor, fecha y demás datos
   generales. BIMAP agrupa internamente todas las filas del mismo folio en una
   cabecera con sus partidas y marca como error cualquier dato general que se
   contradiga dentro del grupo.
5. Identifique clientes con **Clave de cliente** (`bimap_customer_number`),
   proveedores con **Clave de proveedor** (`bimap_supplier_number`) y productos
   con **Clave de producto** (`item_code`). BIMAP completa a la derecha el nombre
   correspondiente en una columna protegida. Una clave inexistente o restringida
   para el usuario se marca en su misma celda y no se sustituye por una búsqueda
   ambigua por nombre.
6. Ejecute **Vista previa** y luego **Iniciar importación**.

**Abrir un Excel existente** permanece como alternativa. Admite `.csv` o `.xlsx`;
el límite actual es 25 MB, 100,000 filas por hoja y 500 columnas. En ese flujo se
elige la clave externa, se solicitan sugerencias y se revisa el mapeo antes del
preview. La configuración JSON y las transformaciones declarativas `trim`,
`upper` o `lower` quedan como opciones avanzadas.

Elija **Borrador** para revisar cada documento antes de enviarlo. Elija **Enviar
con ERPNext** únicamente si desea ejecutar el ciclo `submit` nativo: el sistema
advierte que esto puede generar existencias, CxC/CxP y pólizas, vuelve a validar
el permiso `submit` en servidor y lo simula durante el preview.

Después del preview se activa **Solo errores**. Las filas correctas quedan ocultas,
no borradas. Cada problema señala la celda correspondiente; al corregirla se
revalida y la fila desaparece de esa vista cuando queda válida. **Todos** vuelve a
mostrar el lote completo.

Para documentos multihoja, el panel avanzado acepta la especificación descrita
en `PUBLIC_API.md`. Las tablas hijas se agrupan con su padre; las referencias
entre nodos forman un grafo y se crean en orden topológico.

Nunca se crean maestros faltantes implícitamente: deben ser nodos autorizados del
plan o referencias existentes válidas.

La hoja se carga de forma diferida: el paquete actual pesa aproximadamente 20 MB
sin comprimir y 3.6 MB con gzip. Las plantillas nuevas exponen 1,000 filas
virtualizadas para captura/pegado. El servidor procesa los trabajos en lotes y fue
validado con 25,000 actualizaciones, pero el flujo de archivo todavía entrega las
filas inspeccionadas al navegador. Para archivos de decenas de miles de filas se
recomienda usar el job en servidor; una futura vista paginada/streaming evitará
montar el libro completo en memoria del navegador.

## Agregar partidas a un documento abierto

En Pedido BIMAP, pulse **Importar Excel** dentro del grid. Abra CSV/XLSX, relacione
columnas y elija una política: agregar, sumar coincidencias, actualizar o rechazar
duplicados. ERPNext prepara el documento completo y devuelve precios, valores por
defecto y totales; las filas se agregan a la captura, pero el documento no se
guarda hasta que usted use la acción normal de guardar.

## Documentos relacionados

En una especificación avanzada use `native_source` cuando el origen ya existe.
Por ejemplo, Delivery Note→Sales Invoice conserva `dn_detail`; al enviar la
factura genera CxC pero no vuelve a afectar inventario. Las conversiones sólo están
disponibles para pares registrados y siempre verifican lectura del origen y alta
del destino.

## CFDI de gastos y pagos a proveedores

1. Abra el importador y seleccione un XML.
2. Para factura, indique en **Valores predeterminados JSON** la empresa/proveedor
   cuando el RFC no permita resolverlos de forma única. Puede usar
   `{"company":"...","supplier":"...","item_map":{"CLAVE":"ITEM"}}` o
   `default_item_code` para conceptos sin `NoIdentificacion` utilizable.
3. Pulse **Preparar CFDI**. ERPNext completa cuentas, UOM, impuestos y totales
   según su configuración; si su total no coincide con el XML, la creación queda
   bloqueada.
4. Pulse **Crear borrador** y revise/envíe la Purchase Invoice en ERPNext.

Para Pagos 2.0, las facturas relacionadas deben estar enviadas y contener el UUID
CFDI. Configure `bank_account` si la empresa no tiene una cuenta bancaria/caja
predeterminada. El motor valida saldo, proveedor, empresa y suma asignada, y crea
Payment Entry en borrador. El UUID/índice evita importar dos veces el mismo pago.

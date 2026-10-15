# Compatibilidad y limitaciones

Fecha de corte: 2026-10-13.

## Matriz verificada

| Componente | Versión/alcance | Estado |
| --- | --- | --- |
| Frappe | 15.106.0 | Integración y Desk verificados |
| ERPNext | 15.105.0 | Maestros, ventas, compras, stock, CxC/CxP y pagos verificados |
| Python | 3.12 del bench | Verificado |
| Univer | OSS 1.0.4, Apache-2.0 | Edición, copy/paste, fórmulas, grid |
| CSV | UTF-8/UTF-8 BOM | Verificado |
| XLSX/XLSM | Lectura `data_only` con openpyxl | Verificado |
| CFDI | 4.0 y Pagos 2.0 | Parser, preview, UUID, Purchase Invoice y Payment Entry verificados |

## Decisiones de licencia

Univer OSS se fija en `1.0.4`. Handsontable y las funciones comerciales de
Jspreadsheet no se incluyeron. La conversión XLSX no depende de Univer Pro: se
realiza en el servidor mediante openpyxl/Frappe.

## Limitaciones conocidas

- El bundle de producción de Univer mide aproximadamente 12.06 MB y se carga
  sólo al abrir una hoja. Sigue siendo un artefacto grande y conviene medir CDN,
  caché y tiempo de carga en la infraestructura objetivo antes del despliegue.
- XLSX se lee con valores calculados almacenados (`data_only`); el servidor no
  recalcula fórmulas de Excel.
- La UI no infiere `clear` desde una celda vacía; ofrece una acción separada para
  marcar la limpieza explícita.
- Los cambios estructurales de variantes de Item y valores de Item Attribute se
  bloquean hasta disponer de un adaptador seguro.
- Los adaptadores comerciales registrados son Quotation, Sales Order, Delivery
  Note, Sales Invoice, Purchase Order, Purchase Receipt y Purchase Invoice. Las
  conversiones nativas soportadas están enumeradas en `PUBLIC_API.md`.
- El parser CFDI no consulta el SAT ni valida criptográficamente sello, cadena,
  vigencia o estado de cancelación. Esas comprobaciones requieren un servicio SAT
  separado antes de automatizar aprobación fiscal.
- CFDI no crea artículos, proveedores, cuentas ni impuestos faltantes. Los conceptos
  requieren artículo existente/mapeado; los impuestos se obtienen de la configuración
  ERPNext y una diferencia de total bloquea el borrador.
- Pagos 2.0 concilia únicamente Purchase Invoices enviadas que tengan
  `bimap_cfdi_uuid`, con una sola empresa/proveedor por nodo Pago. Monedas y tipos de
  cambio complejos quedan sujetos a la validación nativa y deben probarse con la
  configuración contable del sitio.
- `native_source` no admite todavía agregar tablas hijas externas en el mismo nodo;
  usa íntegramente las partidas que produce el mapeador ERPNext.
- El Caso A de 25,000 actualizaciones pasó con lotes reales de 100, cero fallos,
  invariantes de campos/hijos y limpieza sintética verificadas.
- No se ha realizado ningún despliegue ni prueba sobre producción.

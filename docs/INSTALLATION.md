# Instalación

## Requisitos

- Frappe 15 y ERPNext 15.
- Node/Yarn compatibles con el bench.
- Redis y workers de Frappe, incluida la cola `long`.
- `openpyxl`, incluido por Frappe, para XLSX.
- `lxml`, incluido por Frappe, para lectura endurecida de CFDI.

## Instalación en un sitio

Desde la raíz del bench:

```bash
bench get-app /ruta/a/bimap_data_engine
bench --site NOMBRE_DEL_SITIO install-app bimap_data_engine
bench build --app bimap_data_engine
bench --site NOMBRE_DEL_SITIO migrate
bench --site NOMBRE_DEL_SITIO clear-cache
```

No instale la aplicación en producción sin respaldo, ventana de cambio y
autorización. Los trabajos masivos requieren que los workers procesen la cola
`long`; en desarrollo puede iniciarse el conjunto normal de procesos del bench.

La migración crea campos administrados por la app en `Purchase Invoice` y
`Payment Entry`: UUID, archivo CFDI y clave idempotente por pago. Revise nombres
de campos personalizados en un clon antes de instalar si el sitio ya usa campos
con prefijo `bimap_cfdi_`.

## Desarrollo y verificación

```bash
bench --site mi-sitio.local set-config allow_tests true
bench --site mi-sitio.local run-tests --app bimap_data_engine
bench build --app bimap_data_engine
```

Los smoke tests de navegador se encuentran en `tests/e2e/` y reutilizan la
instalación de Playwright de `tests/bimap_e2e` mediante `NODE_PATH`.

## Desinstalación

Los DocTypes propios contienen sesiones, perfiles, contextos, jobs y auditoría.
Exporte o conserve esta evidencia antes de desinstalar. La desinstalación no debe
usarse como mecanismo de limpieza de trabajos.

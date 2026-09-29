# Lomax SA: Etapa 2 con Floci y Docker

Entorno local para persistir el catalogo en RDS MySQL emulado por Floci y los atributos variables en DynamoDB. Floci se conecta al daemon Docker para iniciar un contenedor MySQL real para RDS; DynamoDB se atiende en el endpoint local de Floci.

## Requisitos

- Docker Desktop iniciado en modo de contenedores Linux.
- AWS CLI v2 instalado en Windows.
- Puertos `4567` y `7001-7099` disponibles. Se usa `4567` para no interferir con otras instalaciones locales de Floci en `4566`.
- Acceso a internet la primera vez para descargar las imagenes `floci/floci:2.1.0-compat` y `mysql:8.0`.

## Iniciar y probar

Desde PowerShell en la carpeta del proyecto:

```powershell
$env:LOMAX_DB_PASSWORD = "LomaxLocal2026!"
.\scripts\setup.ps1
```

La clave anterior es solo para el ejercicio local; puedes cambiarla antes de ejecutar el script. El script inicia Floci, crea o reutiliza la instancia RDS `lomax-mysql`, espera a MySQL, crea las tablas y carga las 20 filas proporcionadas. Luego crea la tabla DynamoDB y carga los atributos de ejemplo relacionándolos por el `producto_id` devuelto por RDS. Se puede ejecutar nuevamente para volver a aplicar la carga y las verificaciones.

El script valida una inserción válida, código duplicado, precio negativo y categoría inexistente. En cada caso inválido comprueba que no se haya creado una fila parcial. Por último lee DynamoDB y compara sus claves `producto_id` y `codigo` con los registros de RDS. Los cuatro resultados positivos se imprimen como `OK`.

## Modelo relacional (RDS MySQL)

```text
Categorias
  categoria_id  INT UNSIGNED   PK, autoincremental
  nombre        VARCHAR(100)   NOT NULL, UNIQUE

Productos
  producto_id   BIGINT UNSIGNED PK, autoincremental
  codigo        VARCHAR(40)    NOT NULL, UNIQUE
  nombre        VARCHAR(160)   NOT NULL
  descripcion   TEXT           NOT NULL
  precio        DECIMAL(10,2)  NOT NULL, CHECK >= 0
  categoria_id  INT UNSIGNED   NOT NULL, FK -> Categorias
  fecha_creacion TIMESTAMP     NOT NULL
  estado        ENUM           PENDIENTE | PUBLICADO
```

La FK, el índice único de código, el `CHECK` del precio y las columnas `NOT NULL` se validan en MySQL/InnoDB. Las tablas se crean en `database/schema.sql`; las cinco categorías y los 20 productos de ejemplo están en `database/seed.sql`.

## Esquema de DynamoDB

Tabla `LomaxAtributos`, modo `PAY_PER_REQUEST`:

| Atributo | Tipo DynamoDB | Uso |
| --- | --- | --- |
| `producto_id` | Number, clave de partición | Mismo identificador generado por RDS |
| `codigo` | String | Verificación de correspondencia con RDS |
| `atributos` | Map de String a String | Propiedades variables por tipo de producto |
| `imagen_estado` | String | `PENDIENTE` en esta etapa |
| `imagen_original_key` | String (opcional) | Se agrega en la etapa 3 |
| `miniatura_key` | String (opcional) | Se agrega en la etapa 3 |

La referencia cruzada entre servicios se comprueba en el script: no hay FK distribuida. Los ejemplos de atributos se encuentran en `dynamodb/atributos.json`.

## Comandos útiles

```powershell
docker compose ps
docker compose logs -f floci
aws dynamodb list-tables --endpoint-url http://localhost:4567 --region us-east-1
aws rds describe-db-instances --endpoint-url http://localhost:4567 --region us-east-1
```

Para detener Floci sin borrar el volumen persistente: `docker compose down`. Para continuar, vuelve a ejecutar `docker compose up -d floci` o el script de configuración. Eliminar volúmenes de Docker borra los datos locales.

## Etapa 3: S3 y Lambda (P4)

La función `lambda/handler.py` acepta eventos con `producto_id`, `bucket` y `clave_original`. Comprueba que el objeto esté en el bucket de originales, mida como máximo 5 MiB y sea JPEG o PNG válido; aplica la orientación EXIF, conserva la proporción y guarda un JPEG de hasta 300 x 300 píxeles. La clave usa `miniaturas/<producto_id>/<sha256(bucket/clave)>.jpg`, por lo que una repetición reemplaza el mismo objeto. DynamoDB recibe `imagen_estado=LISTA` y las claves solo después de guardar la miniatura. Ante un error de imagen, elimina la miniatura determinista, guarda `imagen_estado=ERROR` y mantiene el producto RDS en `PENDIENTE` para permitir el reintento.

El script de ejecución crea o reutiliza los buckets `lomax-originales` y `lomax-miniaturas`, prepara los productos de prueba sin publicarlos, empaqueta Pillow para `python3.12`, despliega/invoca Lambda síncronamente, valida el resultado funcional y verifica DynamoDB y S3. Genera archivos de evidencia y descargas bajo `evidence/stage3/`.

```powershell
$env:LOMAX_DB_PASSWORD = "LomaxLocal2026!"
.\scripts\stage3.ps1
```

La clave se comparte con la instancia local de RDS de la Etapa 2. La primera ejecución también puede tardar mientras Docker descarga Python, Pillow y el runtime de Lambda.

### Capturas para entregar

Guarda capturas legibles dentro de `evidence/stage3/` o insértalas en el informe P4. Estas cinco capturas cubren el entregable:

1. **Buckets y originales:** consola de Floci en `http://localhost:4567/_floci/ui` con `lomax-originales` y `lomax-miniaturas`, y el listado `originales/` con el JPEG de 1200 x 800. Como respaldo, usa `s3-listado-originales.txt`.
2. **Lambda invocada y resultado:** terminal mostrando `lambda-jpeg-primera-invoke-metadata.json` sin `FunctionError` y `lambda-jpeg-primera-response.json` con `estado: LISTA`, `dimensiones_original: 1200x800` y `dimensiones_miniatura: 300x200`.
3. **Original y miniatura descargados:** abre `original-descargado.jpg` y `miniaturas/miniatura-lomax.jpg` (en una captura conjunta o dos), y muestra `dimensiones.json` con `1200x800` y `300x200`. Adjunta ambos archivos al P4; no basta con una captura.
4. **Referencia y reintento:** muestra `dynamodb-get-item-miniatura.json`, donde `miniatura_key` coincide exactamente con la clave listada en `s3-list-objects-miniaturas.json`; incluye `lambda-jpeg-reintento-response.json` y evidencia que bajo `miniaturas/<producto_id>/` hay un único objeto.
5. **Imagen inválida y límite:** muestra `lambda-invalida-response.json` y `lambda-mayor-a-5MiB-response.json` con `estado: ERROR`, `dynamodb-get-item-invalida.json` con `imagen_estado: ERROR` y sin `miniatura_key`, `rds-estados-pendientes.txt` con los productos `PENDIENTE`, y `s3-list-objects-miniaturas.json` sin objetos para esos productos.

Las respuestas de AWS CLI prueban además que el transporte no reportó `FunctionError`; el campo `estado` y la verificación del objeto son la prueba funcional. El script termina con error si las dimensiones no son exactamente 1200 x 800 y 300 x 200, si la clave cambia al reintentar, si aparece más de una miniatura JPEG, si DynamoDB no coincide o si se publica un producto.

## Etapa 4: API Flask

Siete endpoints sobre RDS, DynamoDB, S3 y Lambda. Ver `backend/app.py`.

| Método | Ruta | Respuesta |
| --- | --- | --- |
| GET | `/categorias` | 200 con las categorías de RDS |
| POST | `/productos` | 201 con `producto_id` y estado `PENDIENTE`; 400 datos inválidos, 409 código duplicado, 400 categoría inexistente |
| POST | `/productos/{id}/imagen` | 200 con `PUBLICADO` si la Lambda genera la miniatura; 413 > 5 MiB, 415 formato no permitido, 404 producto inexistente |
| POST | `/productos/{id}/reprocesar` | 200; 409 si no hay original, 404 si el producto no existe |
| GET | `/productos` | 200 solo con productos `PUBLICADO` |
| GET | `/productos/{id}` | 200 con detalle; 404 si no existe |
| GET | `/productos/{id}/imagen` | 200 con los bytes de la miniatura; 404 si no hay |
| GET | `/health` | 200 |

### Contrato con la Lambda

La invocación es síncrona y el payload debe coincidir con lo que lee `lambda/handler.py`:

```json
{"producto_id": "42", "bucket": "lomax-originales", "clave_original": "originales/42/foto.jpg"}
```

El handler responde un objeto plano con `estado` (`LISTA` o `ERROR`) y, cuando corresponde, `miniatura_key`. El backend solo marca el producto como `PUBLICADO` en RDS si la respuesta trae `estado=LISTA` **y** una `miniatura_key`; en caso contrario deja el producto en `PENDIENTE` y borra la `miniatura_key` de DynamoDB para que no apunte a un objeto inexistente.

`GET /productos/{id}/imagen` no reconstruye la clave: la lee del item de DynamoDB, porque el hash de la clave lo calcula el handler y no es reproducible en el backend.

Los nombres de atributo que comparten RDS y DynamoDB son `producto_id`, `codigo`, `atributos`, `imagen_estado`, `imagen_original_key`, `miniatura_key` e `imagen_error`.

### Comprobación de contratos

Los nombres de evento, atributos y claves se pueden desincronizar sin que nada falle visiblemente hasta la primera carga de imagen. Para detectarlo:

```powershell
python scripts\verify_contracts.py
```

Parsea el AST de `lambda/handler.py` y de los módulos del backend y compara el evento enviado, los atributos de DynamoDB y la clave de la miniatura. No necesita Docker ni dependencias. Sale con código 1 si algo no coincide.

### Pruebas de integración

Con la pila levantada:

```powershell
docker compose up -d backend frontend
python backend\test_endpoints.py
```

Recorre el flujo completo: crea un producto, sube la imagen, verifica que la Lambda devuelve `LISTA`, que el producto queda `PUBLICADO`, que la miniatura se descarga y que el reproceso es idempotente. Sale con código 1 si alguna comprobación falla.

## Etapa 5: Frontend

`frontend/` es un dashboard estático servido por nginx en el puerto `80`. Habla con la API en `http://localhost:5000` mediante CORS. Muestra únicamente productos `PUBLICADO` y usa la miniatura que generó la Lambda en la tarjeta y en la ficha de detalle.

```powershell
docker compose up -d backend frontend
```

## Configuración

`backend/config.py` centraliza la configuración por variables de entorno; `backend/ENV_EJEMPLO` documenta todas. Los valores por defecto coinciden con los que crean `scripts/setup.ps1` y `scripts/stage3.ps1`, y `docker-compose.yml` los sobrescribe para el contenedor:

| Dato | Valor |
| --- | --- |
| Endpoint de Floci | `4567` desde el host, `4566` dentro de la red de compose |
| Instancia RDS | `lomax-mysql`, base `lomax_catalogo`, usuario `lomax` |
| Tabla DynamoDB | `LomaxAtributos` |
| Buckets S3 | `lomax-originales`, `lomax-miniaturas` |
| Función Lambda | `lomax-thumbnail` |
| Prefijo de originales | `originales/<producto_id>/<archivo>` |

La clave de la miniatura es determinista: `miniaturas/<producto_id>/<sha256(bucket/clave_original)>.jpg`, por lo que reprocesar la misma imagen reemplaza el mismo objeto en lugar de acumular duplicados.

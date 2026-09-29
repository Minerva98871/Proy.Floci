# Lomax SA

Catálogo de productos sobre servicios emulados de AWS con [Floci](https://floci.io). La aplicación es una API Flask que publica productos en RDS MySQL, guarda sus atributos variables en DynamoDB, sube las fotografías a S3, genera miniaturas con Lambda y las sirve detrás de un reverse proxy que es la única entrada de usuarios. Las imágenes se publican en un registro OCI (ECR) y la aplicación final se despliega en Kubernetes (EKS) con escalamiento y autorrecuperación.

## Documentos de la entrega

| Entregable | Documento |
| --- | --- |
| P1 — Síntesis conceptual | [`docs/p1-sintesis-conceptual.md`](docs/p1-sintesis-conceptual.md) |
| P2 — Arquitectura y diagrama | [`docs/p2-arquitectura.md`](docs/p2-arquitectura.md) |
| P7 — Publicación en ECR | [`docs/p7-ecr.md`](docs/p7-ecr.md) |
| Estado de avance y bugs corregidos | [`PROGRESO.md`](PROGRESO.md) |
| Manifiestos de Kubernetes | [`k8s/`](k8s/) |

## Requisitos

- Docker Desktop iniciado en modo de contenedores Linux.
- AWS CLI v2 en Windows (lo usan los scripts de cada etapa).
- `kubectl` para la Etapa 7. Docker Desktop ya lo incluye; si no, `kubectl version --client` lo confirma.
- Puertos `4567`, `7001-7099` y `8080` libres en el host. Se usa `4567` para no interferir con otras instalaciones locales de Floci en `4566`, y `8080` para el proxy porque el `80` está reservado en esta máquina. Ambos son configurables (`LOMAX_PROXY_PORT` en `.env`).
- Acceso a internet la primera vez para descargar las imágenes `floci/floci`, `mysql:8.0`, `python:3.12-slim` y `nginx:1.27-alpine`.

## Ejecución completa

Los scripts se ejecutan en orden. Cada uno es idempotente: se pueden volver a lanzar sin partir de cero.

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
$env:LOMAX_DB_PASSWORD = "LomaxLocal2026!"

.\scripts\setup.ps1        # Etapa 2  RDS + DynamoDB, 20 productos
.\scripts\stage3.ps1       # Etapa 3  S3 + Lambda, miniaturas
docker compose up -d --build   # Etapas 4-6  API, frontend y proxy
.\scripts\stage5_catalogo.ps1   # Etapa 5  una foto por producto vía la API
python backend\test_endpoints.py   # Etapa 4  suite TEST 1-8 contra el proxy
.\scripts\stage6_ecr.ps1   # Etapa 6  publica backend, frontend y proxy en ECR
.\scripts\stage7_eks.ps1   # Etapa 7  despliegue en EKS, escalamiento y autorrecuperación
```

Con la pila levantada, la aplicación se usa en **<http://localhost:8080>**. Ese es el único puerto publicado: ni el backend ni el frontend lo están, a propósito.

```powershell
curl http://localhost:8080/proxy-health   # {"status":"OK","service":"lomax-proxy"}
curl http://localhost:8080/api/health     # {"service":"lomax-backend","status":"OK"}
```

## Etapa 2: RDS y DynamoDB

Floci se conecta al daemon Docker para iniciar un contenedor MySQL real para RDS; DynamoDB se atiende en el endpoint local de Floci.

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
python scripts\verify_contracts.py     # que backend y Lambda no se desincronicen
python scripts\fix_powershell_encoding.py   # BOM UTF-8 en los .ps1
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

La suite recorre el flujo completo y **pega al reverse proxy**, no al backend directamente, que es como un usuario real llega a la aplicación. Cubre los ocho casos `TEST 1`–`TEST 8` y escribe un informe en `evidence/stage4/reporte-e4.md`.

```powershell
docker compose up -d --build
python backend\test_endpoints.py
```

Crea un producto, sube la imagen, verifica que la Lambda devuelve `LISTA`, que el producto queda `PUBLICADO`, que la miniatura se descarga y que el reproceso es idempotente. Comprueba además los códigos `400`, `409`, `413`, `415`, `502` y `503`, y que **cada error identifica el paso fallido** (`paso_fallido`). Sale con código 1 si alguna comprobación falla.

Para apuntar a otra dirección: `set LOMAX_TEST_BASE_URL=http://otro-host:8080/api`.

## Etapa 5: Frontend y reverse proxy

`frontend/` es un dashboard estático servido por nginx. Habla con la API por la misma entrada de usuario, así que no necesita CORS ni conocer la dirección del backend.

`proxy/` es el reverse proxy y es **la única vía de entrada**: el servicio `frontend` no publica ningún puerto y el `backend` solo es alcanzable desde la red de Compose. Todo pasa por nginx, que enruta `/api/` al backend y el resto al frontend.

```powershell
docker compose up -d --build
```

Abrir <http://localhost:8080>. El formulario muestra el estado de cada petición y, si el proxy o la API devuelven un error, muestra **qué paso falló** (`paso_fallido`) y ofrece un botón de reintento.

La configuración de nginx es una plantilla (`proxy/nginx.conf.template`) que el entrypoint de la imagen completa con `LOMAX_BACKEND` y `LOMAX_FRONTEND`. El filtro de `envsubst` solo sustituye esas dos variables, de modo que las propias de nginx (`$host`, `$scheme`...) no se vacían. Gracias a eso **la misma imagen** sirve en Docker Compose y en Kubernetes: solo cambian los nombres de los Services.

## Etapa 6: publicación en ECR

```powershell
.\scripts\stage6_ecr.ps1
```

Construye y publica tres imágenes —`lomax-backend`, `lomax-frontend` y `lomax-proxy`— en el registro OCI de Floci, etiquetadas con el hash del commit. El script usa el `repositoryUri` que devuelve la API en vez de construir el nombre a mano, muestra el digest de cada `docker push`, lista las imágenes con `ecr describe-images` y comprueba que una imagen descargada desde cero arranca y responde.

La etiqueta se usa después como `__IMAGE_TAG__` en los manifiestos de la Etapa 7, para que el clúster ejecute exactamente lo publicado y no reconstruya nada. Detalle en [`docs/p7-ecr.md`](docs/p7-ecr.md) y en [`evidence/stage6/ecr-publish.md`](evidence/stage6/ecr-publish.md).

> Con `FLOCI_SERVICES_ECR_URI_STYLE: "path"` el daemon de Docker en Windows no resuelve `*.localhost`, así que las imágenes se referencian como `localhost:4566/000000000000/us-east-1/<repositorio>:<etiqueta>`.

## Etapa 7: despliegue en EKS

```powershell
.\scripts\stage7_eks.ps1
```

Crea el cluster, aplica los manifiestos de [`k8s/`](k8s/) y demuestra las dos cosas que aporta un orquestador: **escalamiento horizontal** (1 → 3 réplicas del backend) y **autorrecuperación** (se borra un Pod a propósito y el Deployment crea otro con un UID que no existía antes).

Detalles que hacen que funcione en local y que conviene conocer:

- El webhook de autenticación de EKS **rechaza las claves `test/test`** a propósito, porque conceden cluster-admin. El script crea un usuario IAM (`lomax-dev`) con su access key y usa esas credenciales. Como IAM solo entrega el secret al crear la clave, la primera vez se guarda en `%TEMP%\lomax-eks-access-key.json` y las siguientes se recuperan de ahí.
- Floci levanta un contenedor k3s por cluster cuyo API server se enlaza en el host dentro del rango 6500-6599. **No hay que publicar ese rango** en `docker-compose.yml`: hacerlo lo ocupa entero y Floci responde `No free port available in range 6500-6599`.
- Desde un Pod, `host.docker.internal` no resuelve (el DNS del clúster no lo conoce), pero las IP de la red compartida de Docker sí. El script descubre en cada ejecución la IP de Floci y la del contenedor RDS y las inyecta en el ConfigMap. Docker las reasigna al reiniciar, por eso se descubren en vez de fijarse.
- El proxy se declara como `NodePort` para dejar el diseño completo, pero Floci solo publica el API server, así que el script usa `kubectl port-forward` para verificarlo. En AWS real lo haría un Service `LoadBalancer` con un ALB.

Evidencia completa en [`evidence/stage7/eks-despliegue.md`](evidence/stage7/eks-despliegue.md).

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

## Evidencia (P9)

Cada script deja en `evidence/` lo que comprobó, para que los resultados se puedan revisar sin volver a ejecutarlo.

| Ruta | Qué contiene |
| --- | --- |
| `evidence/stage3/` | Respuestas de invocación de Lambda, `get-item` de DynamoDB, listados de S3, dimensiones verificadas y los originales y miniaturas descargados |
| `evidence/stage4/` | Informe de la suite `TEST 1`–`TEST 8` con los códigos de cada caso |
| `evidence/stage5/` | Catálogo resultante y las fotografías de producto |
| `evidence/stage6/` | Digests de publicación, imágenes registradas y verificación de arranque |
| `evidence/stage7/` | Cluster, Pods, escalamiento y autorrecuperación con los UIDs antes y después |

Se versionan las respuestas, los informes y los archivos de imagen. Quedan fuera solo dos artefactos regenerables, para no subir 12 MB al repositorio: el paquete de Lambda (`lomax-thumbnail.zip`, que reconstruye `scripts/package_lambda.py`) y el JPEG de relleno de 5 MiB que sirve para probar el límite de tamaño. Los resultados que dependían de ellos sí están guardados.

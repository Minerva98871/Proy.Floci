# Etapa 1 — Arquitectura de la solución

Diagrama de arquitectura de Lomax SA con la entrada de usuarios, los
componentes de aplicación, los servicios de AWS emulados por FLOCI y su
ubicación en Kubernetes.

## Diagrama

```mermaid
flowchart TB
    subgraph usuario["USUARIOS"]
        N["1. Navegador<br/>escritorio o movil"]
    end

    subgraph entrada["ENTRADA DE USUARIOS (Docker Compose / EKS)"]
        P{{"REVERSE PROXY<br/>nginx 1.27-alpine<br/>:8080 → :80<br/><i>entrada única de usuarios</i>"}}
    end

    subgraph aplicacion["APLICACIÓN (contenedores en la red lomax-etapa2)"]
        FE["FRONTEND<br/>nginx sirviendo HTML/CSS/JS<br/>HTTP :80 interno"]
        API["API - Flask<br/>Python 3.12<br/>HTTP :5000 interno<br/>7 endpoints REST"]
    end

    subgraph aws["SERVICIOS AWS EMULADOS POR FLOCI (localhost:4567)"]
        RDS[("RDS · MySQL 8.0<br/>lomax_catalogo<br/>Categorias, Productos<br/>host.docker.internal:7001")]
        DDB[("DynamoDB<br/>tabla LomaxAtributos<br/>atributos variables +<br/>claves de imagen<br/>partition key: producto_id")]
        S3O[("S3 · lomax-originales<br/>originales/&lt;id&gt;/&lt;archivo&gt;")]
        S3M[("S3 · lomax-miniaturas<br/>miniaturas/&lt;id&gt;/&lt;sha256&gt;.jpg")]
        LAM["Lambda<br/>lomax-thumbnail<br/>Python 3.12 + Pillow<br/>invocación síncrona"]
    end

    subgraph k8s["UBICACIÓN EN KUBERNETES (Etapa 7 · EKS)"]
        direction LR
        subgraph nodos["Nodo de trabajo"]
            POD1["Pod backend<br/>replica 1<br/>imagen ECR"]
            POD2["Pod backend<br/>replica 2<br/>imagen ECR"]
            POD3["Pod backend<br/>replica 3<br/>imagen ECR"]
        end
        SVC["Service lomax-backend<br/>ClusterIP<br/>load balancing + readiness"]
        DEPLOY["Deployment lomax-backend<br/>spec.replicas: 3"]
        INGRESS["Ingress / Service proxy<br/>entrada de usuarios"]
        EPOD["Pod proxy<br/>imagen ECR"]
    end

    N -->|"HTTP :8080"| P
    P -->|"/ (estáticos)"| FE
    P -->|"/api/* (REST + /imagen)"| API

    API -->|"SQL 3306<br/>productos, categorías"| RDS
    API -->|"API DynamoDB<br/>atributos, estado imagen"| DDB
    API -->|"PutObject<br/>original"| S3O
    API -->|"InvokeFunction<br/>RequestResponse"| LAM
    LAM -->|"GetObject original"| S3O
    LAM -->|"thumbnail ≤300×300"| S3M
    LAM -->|"UpdateItem<br/>miniatura_key, imagen_estado"| DDB
    API -->|"miniatura bytes"| S3M
    FE -.->|"consume /api en el mismo origen"| P

    INGRESS --> EPOD --> SVC
    SVC --> POD1
    SVC --> POD2
    SVC --> POD3
    DEPLOY -.->|"gestiona"| POD1

    subgraph datos["PERSISTENCIA FUERA DE LOS PODS"]
        RDS
        DDB
    end
    S3O
    S3M

    classDef proxy fill:#1e3a5f,color:#fff,stroke:#0f2740,stroke-width:2px
    classDef app fill:#1f7a8c,color:#fff,stroke:#14545f,stroke-width:2px
    classDef data fill:#4a5568,color:#fff,stroke:#2d3748,stroke-width:2px
    classDef srv fill:#8b5a1f,color:#fff,stroke:#5f3d14,stroke-width:2px
    classDef k8s fill:#2d6a4f,color:#fff,stroke:#1b4732,stroke-width:2px

    class P proxy
    class FE,API app
    class RDS,DDB,S3O,S3M data
    class LAM srv
    class SVC,DEPLOY,INGRESS,POD1,POD2,POD3,EPOD k8s
```

## Componentes, protocolos y puertos

| Componente | Imagen | Puerto interno | Puerto publicado | Protocolo |
|---|---|---|---|---|
| Reverse proxy (entrada) | `proxy/Dockerfile` (nginx 1.27-alpine) | 80 | **8080** → 80 | HTTP |
| Frontend | `frontend/Dockerfile` (nginx) | 80 | ninguno | HTTP |
| API (backend) | `backend/Dockerfile` (python:3.12-slim) | 5000 | ninguno | HTTP REST |
| FLOCI (emulador AWS) | `floci/floci:2.1.0-compat` | 4566 | 4567, 7001-7099, 6500-6599, 5100 | HTTP |
| RDS MySQL | gestionado por FLOCI | 3306 | 7001 | MySQL |
| DynamoDB | gestionado por FLOCI | — | vía 4567 | HTTP API |
| S3 | gestionado por FLOCI | — | vía 4567 | HTTP API |
| Lambda | `lambda/handler.py` | — | vía 4567 | invocación HTTPS |
| ECR (registro OCI) | gestionado por FLOCI | 5100 | 5100 | Docker Registry v2 |
| EKS (k3s) | gestionado por FLOCI | 6500-6599 | 6500-6599 | Kubernetes API |

## Protocolos

- **HTTP** entre navegador → proxy → frontend y API.
- **MySQL** entre la API y RDS.
- **HTTPS (API de AWS)** entre la API y DynamoDB/S3/Lambda, apuntando a
  `http://localhost:4567` con las credenciales de demostración.
- **Docker Registry v2** entre `docker push`/`docker pull` y ECR.

## Almacenamiento

| Almacén | Contenido | Clave |
|---|---|---|
| RDS `lomax_catalogo` | `Categorias`, `Productos` | `producto_id` (auto_increment) |
| DynamoDB `LomaxAtributos` | Atributos variables, `imagen_original_key`, `miniatura_key`, `imagen_estado` | `producto_id` (numérica) |
| S3 `lomax-originales` | Fotografías originales | `originales/<id>/<archivo>` |
| S3 `lomax-miniaturas` | Miniaturas ≤300×300 | `miniaturas/<id>/<sha256>.jpg` |

## Redes

| Red | Tipo | Quiénes participan |
|---|---|---|
| `lomax-etapa2` | bridge, definida por Compose | proxy, frontend, backend, floci |
| `lomax-etapa2_default` | la que ve Floci | floci, mysql-rds (y los Pods en EKS) |

## Ubicación de los componentes en Kubernetes (Etapa 7)

| Componente | Namespace | Tipo | Notas |
|---|---|---|---|
| Reverse proxy | `lomax` | Pod | Entrada de usuarios, desde ECR |
| Frontend | `lomax` | Pod | Estáticos, desde ECR |
| Backend | `lomax` | Deployment (3 réplicas) + Service ClusterIP | Desde ECR |
| RDS | externo | servicio gestionado | Host del clúster, no Pod |
| DynamoDB | externo | servicio gestionado | sdk vía endpoint |
| S3 | externo | servicio gestionado | sdk vía endpoint |
| Lambda | externo | servicio gestionado | invocada por la API |

**Punto clave**: RDS, DynamoDB, S3 y Lambda quedan **fuera** de los Pods. Por
eso al borrar un Pod el catálogo sigue disponible: los datos no viajan con el
contenedor.

## Verificación E1

**Recorrido de una consulta del catálogo:**

1. El navegador pide `http://localhost:8080/`.
2. El reverse proxy enruta `/` al frontend y devuelve el HTML.
3. `app.js` llama a `GET /api/productos` en el **mismo origen**.
4. El proxy quita `/api` y reenvía a `backend:5000`.
5. La API consulta en **RDS** los productos `PUBLICADO` y en **DynamoDB** los
   atributos y la clave de miniatura de cada uno.
6. Devuelve la lista combinada con `miniatura_url` por producto.
7. El navegador pide cada `GET /api/productos/<id>/imagen`.
8. La API lee `miniatura_key` de **DynamoDB** y descarga los bytes de **S3**.

**Recorrido de un registro con publicación:**

1. `POST /api/productos` → **RDS** inserta `PENDIENTE`; **DynamoDB** guarda los
   atributos. Si DynamoDB falla, se revierte la fila de RDS.
2. `POST /api/productos/<id>/imagen` → la API sube el original a **S3** y marca
   `imagen_estado = PROCESANDO` en DynamoDB.
3. La API invoca **Lambda** de forma síncrona.
4. Lambda lee el original de S3, genera la miniatura ≤300×300 y la guarda.
5. Lambda escribe `miniatura_key` e `imagen_estado = LISTA` en DynamoDB.
6. La API confirma y cambia el producto a `PUBLICADO` en RDS.
7. Si Lambda devuelve `ERROR`, el producto **permanece** `PENDIENTE` y puede
   reintentarse con `POST /productos/<id>/reprocesar`.

**Contraste con lo desplegado**: cada nodo del diagrama corresponde a un
contenedor de `docker compose ps`, a un recurso de `aws` (RDS, DynamoDB, S3,
Lambda, ECR) o a un objeto de `kubectl get all` en la Etapa 7. La tabla de
puertos coincide con las secciones `ports:` de `docker-compose.yml`.

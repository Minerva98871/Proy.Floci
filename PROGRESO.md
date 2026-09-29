# Progreso de implementación

## Completado y verificado en ejecución

### Etapa 2 — RDS y DynamoDB (E2)
- 20 productos publicados en 4 categorías, con 2 conjuntos distintos de atributos.
- Las 4 restricciones probadas: inserción válida, código duplicado, precio
  negativo y categoría inexistente. Ninguna deja registros parciales.
- Carga inicial repetible sin duplicados (re-ejecutada dos veces con éxito).
- Acentos de `seed.sql` verificados intactos en RDS.

### Etapa 3 — S3 y Lambda (E3)
- 1200×800 produce 300×200; la proporción se conserva.
- 24 miniaturas, todas dentro de 300×300.
- Clave de salida determinista: repetir la invocación no crea objetos extra.
- Imagen inválida y archivo >5 MiB dejan estado `ERROR` sin miniatura, y el
  producto permanece `PENDIENTE` para reintentar.

### Etapa 4 — API (E4)
- **35/35 comprobaciones OK** en `backend/test_endpoints.py`.
- TEST 1 a TEST 8 del enunciado cubiertos, con reporte en
  `evidence/stage4/reporte-e4.md`.
- Cada error incluye `paso_fallido` (`validacion`, `rds`, `dynamodb`,
  `s3_original`, `s3_miniaturas`, `lambda`), como pide la Etapa 4.
- 409, 413 y 415 verificados.

### Etapa 5 — Catálogo y reverse proxy
- 21 productos publicados, cada uno con fotografía y miniatura.
- Originales con proporciones variadas (1200×800, 800×1200, 1000×1000,
  1600×900, 900×1600) para demostrar que el escalado es real.
- El proxy es la única entrada: `frontend` no publica puertos y `backend` solo
  es alcanzable desde la red de Compose.

### Etapa 6 — ECR (P7)
- Tres repositorios: `lomax-backend`, `lomax-frontend` y `lomax-proxy`.
- Build, `docker push` con digest y `ecr describe-images` verificados.
- Una imagen descargada desde cero arranca y responde `/health`.
- Evidencia en `evidence/stage6/ecr-publish.md` y detalle en `docs/p7-ecr.md`.

### Etapa 7 — EKS (P8)
- Cluster k3s real en `ACTIVE`, nodo `Ready`, API server en `localhost:6500`.
- 5 Pods `Running` en el namespace `lomax`: 3 del backend, 1 del frontend y
  1 del proxy, **todos con imágenes descargadas del registro ECR**.
- Escalamiento horizontal 1 → 3 réplicas verificado.
- Autorrecuperación verificada borrando un Pod: el reemplazo tiene un UID que
  no estaba en la lista previa, y el catálogo sigue completo tras recrearlo.
- Evidencia en `evidence/stage7/eks-despliegue.md`.

## Bugs reales encontrados y corregidos

| Bug | Síntoma | Causa |
|---|---|---|
| `conn.is_closed()` | 502 en toda escritura a RDS | Ese método es de MySQLdb, no de `mysql.connector` |
| Host de RDS fijo en compose | El backend no encontraba la BD | Floci genera el nombre del contenedor con un id aleatorio |
| Acentos corruptos en RDS | `Computación` | `Get-Content` sin `-Encoding UTF8` en PowerShell 5.1 |
| Acentos corruptos en `.ps1` | Comentarios en español ilegibles | PowerShell 5.1 lee sin BOM como ANSI; se añadió BOM UTF-8 a los scripts |
| `setup.ps1` no repetible | Fallaba al re-ejecutar tras la Etapa 3 | Exigía `PENDIENTE` cuando la Etapa 3 ya había procesado |
| Scripts PowerShell abortaban | Exit 1 en `docker compose` | stderr de comandos nativos con `ErrorActionPreference=Stop` |
| Sin reverse proxy | El frontend llamaba al backend por CORS | La arquitectura lo exige como entrada de usuarios |
| Sin opción de reintento | La E5 la pide en la interfaz | No existía en el frontend |
| `paso_fallido` ausente | La Etapa 4 exige identificar el paso | Los errores no lo traían |
| Rango 6500-6599 publicado | EKS fallaba con `No free port available` | El mapeo en compose ocupaba el rango que Floci necesita para k3s |
| `--version 1.31` en `create-cluster` | El clúster no se creaba, solo salía el banner del CLI | El AWS CLI intercepta `--version` antes de Reaching el subcomando |
| `--output json` sobreescrito | `ACTIVE` llegaba como `"ACTIVE"` y no comparaba | El script añadía su `--output` detrás del de la llamada |
| Multi-valor con `--output text` | `NoSuchEntity` al borrar claves de IAM | El CLI separa con tabulador en una sola línea, no con saltos de línea |
| Autorrecovery con UID equivocado | La E7 daba por buena una recuperación inexistente | Se comparaba contra un UID, no contra el conjunto de UIDs previos |
| `port-forward` sin credenciales | Todas las peticiones salían HTTP 0 | `Start-Process` no hereda las variables que solo existían durante la llamada |

## Pendiente

Nada de la asignación. Todo lo pedido en el enunciado está implementado y
verificado en ejecución; falta únicamente la entrega en el aula.


# Etapa 6 — Publicación de imágenes en ECR

Crea los repositorios ECR en FLOCI, construye las imágenes de frontend y
backend, las etiqueta con el commit de entrega y las publica.

**Script:** `scripts/stage6_ecr.ps1`
**Evidencia:** `evidence/stage6/ecr-publish.md`

## Uso

```powershell
# Publica ambas imágenes y ejecuta la verificación E6 completa
.\scripts\stage6_ecr.ps1

# Sin verificación final (más rápido)
.\scripts\stage6_ecr.ps1 -SinVerificar

# Etiquetado manual
.\scripts\stage6_ecr.ps1 -Tag "v1.0-entrega"
```

## Autenticación

FLOCI levanta un registro OCI real, no un mock, pero sin autenticación: el
cliente solo necesita credenciales de AWS válidas en formato.

```powershell
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = "us-east-1"
```

`docker login` es opcional porque el registro no pide usuario ni contraseña.

## Dirección del registro

El plano de datos de ECR lo sirve **el propio puerto 4566 de Floci**, que hace
de proxy hacia su contenedor interno `registry:2`. El puerto 5100 que aparece
en la configuración de Floci es *loopback-only* del backing container y **no
debe publicarse** en `docker-compose.yml`.

Por eso el compose publica `4566:4566` además de `4567:4566`.

### Esquema de URI: `path`, no `hostname`

Floci devuelve por defecto URIs con el esquema `hostname`:

```
000000000000.dkr.ecr.us-east-1.localhost:4566/lomax-backend
```

Ese esquema **no funciona en Docker Desktop para Windows**: el daemon corre
dentro de una VM Linux donde `*.localhost` no resuelve a loopback, y el push
falla con:

```
dial tcp: lookup 000000000000.dkr.ecr.us-east-1.localhost: no such host
```

La solución es el esquema `path`, que Floci documenta justo para este caso
("`*.localhost` does not resolve to loopback on this platform"):

```yaml
environment:
  FLOCI_SERVICES_ECR_URI_STYLE: "path"
```

Con él la API devuelve URIs que sí resuelven:

```
localhost:4566/000000000000/us-east-1/lomax-backend
```

`scripts/stage6_ecr.ps1` no construye la referencia a mano: la pide a
`ecr describe-repositories` y usa la `repositoryUri` que devuelve la API, de
modo que el script sigue funcionando si cambia el esquema o el puerto.

## Conectividad desde Docker y Kubernetes

| Origen | Cómo alcanza el registro | Verificación |
|---|---|---|
| Docker (host) | `localhost:4566/<cuenta>/<region>/<repo>` | `docker pull localhost:4566/000000000000/us-east-1/lomax-backend:<tag>` |
| Docker (contenedor) | `host.docker.internal:4566` | `docker run --rm curlimages/curl -s http://host.docker.internal:4566/v2/` responde `{}` |
| Kubernetes (Pods) | espejo configurado en el clúster EKS | `kubectl get pods` y el evento `Pulled` de la imagen |

El espejo del registro se habilita con
`FLOCI_SERVICES_EKS_ECR_REGISTRY_MIRROR=true` en `docker-compose.yml`, de modo
que los Pods resuelven la referencia ECR sin configuración adicional.

## Etiquetado ligado al commit

Por defecto el script usa el hash corto del commit actual:

```
000000000000.dkr.ecr.us-east-1.localhost:5100/lomax-backend:3ae406b
```

Así, ante cualquier duda sobre qué código corre en una imagen, basta con
comparar la etiqueta con `git log`.

## Verificación E6

El script ejecuta automáticamente los tres puntos que pide el enunciado:

1. **`ecr describe-images`** en ambos repositorios, registrando digest, tamaño y
   fecha de publicación.
2. **`docker pull` sin copia previa**: borra la imagen local (`docker rmi -f`)
   y la vuelve a descargar, para demostrar que viene del registro y no de la
   caché local.
3. **La imagen descargada contiene la aplicación**: arranca el contenedor del
   backend descargado, conectado a la red de Compose y apuntando a los
   servicios ya en marcha, y consulta `/health`. Si responde
   `{"status":"OK"}`, la imagen trae la aplicación entregada.

Salida real de la ejecución:

```
## Verificacion E6: ecr describe-images
- 3ae406b  digest=sha256:dfc2376b...  pushed=2026-09-29T08:57:37-04:00
- 3ae406b  digest=sha256:26fc452d...  pushed=2026-09-29T08:57:38-04:00

## Verificacion E6: docker pull sin copia previa
  Untagged: localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
  Status: Downloaded newer image for localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
  Untagged: localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b
  Status: Downloaded newer image for localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b

## Verificacion E6: la imagen descargada contiene la aplicacion
  /health -> {"service":"lomax-backend","status":"OK"}
  OK: la imagen publicada en ECR contiene la aplicacion entregada.
```

## Consumo en la Etapa 7

Los manifiestos de Kubernetes referencian la referencia remota directamente, sin
reconstruir dentro del clúster:

```yaml
image: localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
imagePullPolicy: IfNotPresent
```

Lo que se publica aquí es exactamente lo que se ejecuta en la Etapa 7.

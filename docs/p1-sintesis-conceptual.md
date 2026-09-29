# Síntesis conceptual — Unidad 1 y 2

Tecnologías Emergentes I · Lomax SA · Equipos 1 y 2

Este documento justifica las decisiones de arquitectura del proyecto. Cada
concepto se relaciona con una decisión concreta: no es teoría suelta, es el
argumento de por qué la solución es como es.

Las secciones que el enunciado dejó vacías (Service, escalamiento,
autorrecuperación, y los seis servicios de AWS) se desarrollan aquí y se
marcan con **[completo]** para que se distingan de lo que ya traía el
documento.

---

## 1. Cloud Computing

### Concepto

Entrega de recursos informáticos —servidores, almacenamiento, bases de datos y
aplicaciones— a través de Internet, con pago por consumo y sin que el usuario
gestione la infraestructura subyacente.

### Características aplicadas al proyecto

| Característica | Cómo aparece en Lomax SA |
|---|---|
| Acceso bajo demanda | El catálogo y la API se consultan por HTTP desde cualquier equipo. |
| Escalabilidad | RDS y S3 crecen sin migrar; en la Etapa 7 el backend escala de 1 a 3 réplicas en EKS. |
| Medición del consumo | Cada invocación de Lambda genera una miniatura; el coste escala con el uso, no con la infraestructura ociosa. |
| Acceso desde distintos dispositivos | El proxy sirve el frontend, así que el acceso no depende del cliente. |

### Escalabilidad vertical y horizontal

**Vertical**: más CPU, RAM o disco en una máquina. Se usó en la Etapa 2 para
que la instancia MySQL de RDS sostenga la carga de la validación de
restricciones, sin tocar el esquema.

**Horizontal**: añadir máquinas que reparten el trabajo. Es la vía que sigue el
proyecto en la Etapa 7: tres Pods del backend detrás de un Service responden
el mismo catálogo. La API no guarda estado en memoria, cada request abre y
cierra su conexión a RDS, y por eso puede atender cualquier Pod indistinto.

La diferencia clave para el proyecto: la escalabilidad **vertical** se decidió
en infraestructura gestionada, la **horizontal** en Kubernetes, porque es
donde la aplicación es stateless.

### Virtualización

Capa que abstrae el hardware físico para ejecutar varios entornos aislados. Es
lo que hace posible que una sola máquina aloje el emulador de AWS, el
MySQL de RDS, la Lambda y los contenedores de la aplicación, cada uno con su
propio sistema de archivos y su reparto de recursos.

### IaaS, PaaS y SaaS

| Modelo | Qué se gestiona | En el proyecto |
|---|---|---|
| **IaaS** | VMs, redes, discos. El usuario elige el SO y el parcheo. | RDS (MySQL), EKS (nodos del clúster). |
| **PaaS** | El proveedor administra todo; el usuario solo sube código. | Lambda: solo se entrega `handler.py` y AWS resuelve capacidad, concurrencia y facturación. |
| **SaaS** | Aplicación terminada, se consume. | No se usa en el alcance. |

Lomax SA no necesita un SaaS de catálogo porque el requisito de conservar
atributos variables por producto (un teclado necesita conexión y distribución;
una pantalla, pulgadas y resolución) no se resuelve con un modelo fijo de
campos sin modificarlo para cada categoría.

### Tipos de nube

**Pública** (AWS), **privada** (infraestructura interna) e **híbrida**. El
proyecto usa pública emulada localmente, que es lo que permite a un equipo
estudentil practicar la API de AWS sin cuenta ni facturación. La alternativa
privada se descartó por coste; la híbrida no aporta nada aquí porque no hay
sistema legado que integrar.

### Ventajas y limitaciones

**Ventajas**: no hay inversión inicial en hardware; la escalabilidad es
horizontal y el coste sigue al uso; el acceso es remoto; la disponibilidad la
gestiona el proveedor.

**Limitaciones**: dependencia del proveedor y de la red; coste variable que
puede sorprender sin control; la verificación es más difícil porque el
hardware es del proveedor; versiones antiguas de las librerías cliente
rompen compatibilidad. Esta última es concreta: el código usa `boto3` con
`endpoint_url` para apuntar al emulador, y una API de AWS que difiera de la
emulada rompería el flujo.

---

## 2. Contenedores

### Concepto

Proceso aislado que empaqueta una aplicación con todas sus dependencias para
ejecutarla igual en cualquier máquina. Comparte el kernel del anfitrión, a
diferencia de una máquina virtual, que incluye su propio kernel.

### Imagen y contenedor

**Imagen**: conjunto de archivos inmutable de capas. Si contiene el código, las
dependencias y el comando de arranque, describes el entorno completo.

**Contenedor**: una instancia en ejecución de esa imagen. El proyecto tiene
`backend/Dockerfile` y `frontend/Dockerfile`; `docker compose up` crea un
contenedor por servicio.

### Dockerfile

Instrucciones que describen cómo construir la imagen:

```dockerfile
FROM python:3.12-slim          # imagen base
WORKDIR /app                   # directorio de trabajo
COPY . .                       # copia el código
RUN pip install -r requirements.txt   # dependencias
EXPOSE 5000                    # puerto que espera el contenedor
CMD ["python", "app.py"]       # proceso principal
```

`EXPOSE` documenta el puerto; no lo publica. La publicación real la hace
Docker Compose con `ports:`. En el diseño final el frontend **no** publica
puertos porque el proxy es la entrada de usuarios.

### Redes y volúmenes

**Redes**: comunicación por nombre de servicio entre contenedores. `backend` y
`floci` se hablan por DNS interno, sin IP fijas. Por eso el compose declara
la red `lomax-etapa2` y el proxy alcanza `backend:5000`.

*El enunciado describe aquí los volúmenes; es una errata. La definición
correcta de redes es la anterior y la de volúmenes va en el punto siguiente.*

**Volúmenes**: almacenamiento persistente que sobrevive a la eliminación del
contenedor. Son los que hacen posible la E2: reiniciar los componentes de
persistencia sin borrar volúmenes conserva los datos. Sin volumen, cada
`docker compose down` destruiría la base y el enunciado no podría pedir
comparar valores antes y después del reinicio.

### Docker Compose

Define y ejecuta aplicaciones de varios contenedores desde un YAML: imágenes,
variables, puertos, redes, volúmenes y dependencias. El proyecto lo usa para
levantar emulador, backend, frontend y proxy con un solo comando.

### Ventajas y limitaciones

**Ventajas**: aislamiento del sistema, instalación y distribución idénticas en
cualquier equipo, menos consumo que una máquina virtual, y Portabilidad, porque
separar aplicación de infraestructura.

**Limitaciones**: comparten el kernel del anfitrión (aislamiento más débil que
una VM); requieren conocimiento de Docker y administración de sistemas; con
muchos contenedores la orquestación se vuelve compleja, y por eso existe
Kubernetes; y una mala configuración expone puertos o secretos.

---

## 3. Kubernetes

### Concepto **[completo]**

Orquestador que declarativo: se describe el estado deseado y Kubernetes
reconduce el real. Programa aplicaciones en contenedores, gestiona su
disponibilidad y las vuelve a crear si fallan.

### Arquitectura básica

Control plane (API Server, Scheduler, Controller Manager) más nodos de trabajo
que ejecutan las aplicaciones en Pods. El Control plane decide *qué* y *dónde*;
los nodos ejecutan.

### Cluster, Pod y Deployment **[completo]**

**Cluster**: conjunto de nodos que trabajan coordinados. En la Etapa 7 es un
clúster EKS creado sobre FLOCI.

**Pod**: la unidad más pequeña que Kubernetes gestiona. Contiene uno o varios
contenedores que comparten red y almacenamiento. Es la unidad de escalamiento y
de reprogramación: si un nodo falla, sus Pods se recrean en otro.

**Deployment**: recurso que mantiene un número dado de Pods idénticos a partir
de una imagen, y permite actualizar, escalar y hacer rollback declarando el
estado deseado. Es lo que produce las 3 réplicas del backend exigidas en la
Etapa 7.

### Service **[completo]**

Un Service expone un conjunto de Pods tras una dirección y puerto estables. Los
Pods son efímeros: sus IP cambian cuando se recrean. El Service es lo que
permite que el proxy o el frontend hablen con «el backend» sin saber cuántos
Pods hay ni cuáles son.

En el proyecto el Service cumple la misma función que el `upstream` de nginx
en local: reparte tráfico entre las réplicas y gestiona el caso de que un Pod
no esté listo. Se configura `readinessProbe` contra `/health` para que un Pod
que aún no conecta con RDS no reciba tráfico y aparezca `Ready` solo cuando la
API puede atender de verdad.

### Escalamiento **[completo]**

Aumentar o reducir Pods para ajustar el recursos a la demanda. Horizontal
(cambia el número de Pods) y vertical (cambia los recursos de un Pod). En el
proyecto el escalamiento es horizontal y se controla de dos formas:

- ** declarativo**: editando `spec.replicas` del Deployment y aplicando el manifiesto.
- **automático**: con HPA, definiendo umbrales de CPU para que el clúster añada
  o retire Pods sin intervención.

Se eligió escalamiento horizontal porque la API es stateless: cada request
abre su propia conexión a RDS y a DynamoDB, así que añadir Pods no exige
sincronizar nada.

### Autorrecuperación **[completo]**

La capacidad de reponer automáticamente un Pod que muere, sin intervención
humana. El bucle es: el nodo detecta que el contenedor terminó, el Deployment
observa que hay menos Pods de los deseados y crea uno nuevo; si el problema
persiste, `CrashLoopBackOff` lo refleja. El proceso no se pierde porque el
estado vive en RDS y DynamoDB, fuera de los Pods.

Se demuestra en la E7 eliminando un Pod a propósito: el reemplazo aparece con
un UID nuevo y el número de réplicas vuelve al valor deseado.

**Por qué el estado debe estar fuera del clúster**: si los datos vivieran en el
sistema de archivos de un Pod, al recrearlo se perderían. Por eso el proyecto
usa RDS y DynamoDB, y el enunciado lo exige expresamente.

---

## 4. AWS

### Concepto

Plataforma de servicios en la nube. Para el proyecto se usa **FLOCI**, un
emulador local compatible con la API de AWS: los mismos comandos de `aws`
mismo SDK apuntan a `http://localhost:4567` sin cuenta ni facturación. Esa
compatibilidad es lo que permite practicar la arquitectura real antes de
la entrega de verdad.

### RDS **[completo]**

Servicio gestionado de bases de datos relacionales. En el proyecto:
`lomax-catalogo` en MySQL, con las tablas `Categorias` y `Productos`.

Se eligió RDS frente a DynamoDB para el catálogo porque las restricciones del
enunciado son relacionales: `codigo` único, precio no negativo y categoría
existente. La integridad se delega a la base con `UNIQUE`, `CHECK` y clave
foránea, en vez de validarla solo en Python, de modo que ningún cliente pueda
saltársela.

Consecuencia de diseño que se ve en la API: los errores 1062 (duplicado) y
1452 (clave foránea) se traducen a 409 y 400, en vez de propagarse como 500.

### DynamoDB **[completo]**

Base de datos de clave-valor y documentos, sin esquema fijo, con latencia de
milisegundos. En el proyecto guarda los atributos variables por
`producto_id`, junto con `imagen_original_key`, `miniatura_key` y el estado del
procesamiento.

Se eligió DynamoDB y no una segunda tabla en MySQL porque los atributos cambian
según la categoría: un teclado tiene `conexion` y `distribucion`, una pantalla
tiene `pulgadas` y `resolucion`. En SQL eso exigiría columnas fijas, una tabla
por categoría o storing JSON sin consultas útiles; en DynamoDB cada item
guarda su propio conjunto de atributos.

La relación entre ambas bases se verifica desde la API, no con una clave
foránea: los servicios no la pueden validar entre sí, así que `POST /productos`
escribe en las dos y, si falla DynamoDB, revierte la fila de RDS para no dejar
un producto huérfano.

### S3 **[completo]**

Almacenamiento de objetos, durability con acceso por clave, sin esquema y con
coste por uso. En el proyecto hay dos buckets: `lomax-originales` para las
fotografías y `lomax-miniaturas` para las generadas por Lambda.

Se separaron en dos buckets y no en prefijos del mismo porque tienen ciclos de
vida y permisos distintos: los originales no se tocan tras la carga, mientras
que las miniaturas se regeneran al reintentar. La clave del original incluye el
nombre del archivo, la de la miniatura un hash del original, lo que hace la
salida determinista: repetir la petición sobrescribe la misma clave en vez de
acumular objetos.

### Lambda **[completo]**

Ejecución de funciones por evento, sin servidor que gestionar. El proveedor
asigna capacidad, escala según las llamadas y cobra por ejecución y duración.

En el proyecto `handler.py` recibe `producto_id`, `bucket` y
`clave_original`, valida la imagen, genera una miniatura de hasta 300×300
conservando la proporción y escribe `miniatura_key` y `imagen_estado` en
DynamoDB.

La API la invoca de forma **síncrona** (`RequestResponse`) porque necesita
saber si la miniatura se generó antes de marcar el producto como `PUBLICADO`.
El coste de la espera se compensa con la garantía: no se publica un producto
con la imagen pendiente, que es el error que el enunciado quiere evitar. Con
invocación asíncrona el producto quedaría `PENDIENTE` sin que nadie sepa si
terminará.

### ECR **[completo]**

Registro de imágenes de contenedor. Se construye, etiqueta y publica la
imagen Docker de cada componente, con una etiqueta ligada al commit de entrega
para poder rastrear qué código hay dentro de cada imagen.

En el proyecto se crearían `lomax-backend` y `lomax-frontend` en FLOCI, y se
publicarían con `docker push` a la dirección que entrega el registro
(`localhost:5100`). La Etapa 7 los consume desde EKS: el clúster tiene el
espejo del registro configurado, así que los Pods descargan las imágenes igual
que lo haría un clúster real de AWS.

La ventaja frente a construirse dentro del clúster es que la imagen se compila
una vez y todos los nodos usan el mismo artefacto, lo que hace el despliegue
reproducible.

### EKS **[completo]**

Servicio gestionado de Kubernetes. En el proyecto sustituye a Docker Compose
para el despliegue, manteniendo proxy como entrada de usuarios y conservando
RDS, DynamoDB, S3 y Lambda fuera del clúster.

Permite demostrar lo que un orquestador aporta y Compose no: escalamiento
horizontal declarativo, balanceo entre Pods, autorrecuperación ante la muerte
de un Pod y capacidad de comprobar que los datos sobreviven a la
reprogramación. Se elige frente aECS por ser el estándar y el que pide el
enunciado.

---

## 5. Cómo se relacionan los conceptos con la solución

| Concepto | Decisión de arquitectura que justifica |
|---|---|
| Baas de datos relacional vs. esquema variable | RDS para datos con restricciones (código único, precio, FK), DynamoDB para atributos que cambian por categoría |
| IaaS frente a PaaS | RDS y EKS gestionados; Lambda como PaaS donde solo se entrega el código |
| Escalabilidad horizontal | API stateless: cada request abre y cierra su conexión, así que los Pods son intercambiables |
| Estado fuera del clúster | RDS y DynamoDB persistentes, para que recrear Pods no pierda datos |
| Contenedores frente a VM | Imágenes de frontend y backend idénticas en desarrollo y en EKS |
| Aprovisionamiento declarativo | Manifiestos de Kubernetes describen el estado deseado; el proxy enruta `/` al frontend y `/api` al backend |
| Servicios gestionados | Ninguna base de datos ni función se despliega dentro del clúster |

## Referencias de implementación

- Símbolos oficiales: [AWS Architecture Icons](https://aws.amazon.com/architecture/icons/)
- Emulador local: `floci/floci` (`docker-compose.yml`)
- Persistencia: `database/schema.sql`, `database/seed.sql`, `dynamodb/atributos.json`
- Procesamiento: `lambda/handler.py`
- API: `backend/app.py`

# E7 - Despliegue en EKS, escalamiento y autorrecuperacion

- Fecha: 2026-09-29 09:27:40
- Cluster: lomax
- Replicas objetivo: 3

## Imagen
- Etiqueta: 3ae406b
- Origen: registro ECR de la Etapa 6 (el clúster no reconstruye nada)

## Credenciales de IAM para el webhook de EKS
- El rol ya existia: arn:aws:iam::000000000000:role/lomax-eks-cluster
- Usuario IAM: { "User": { "Path": "/", "UserName": "lomax-dev", "UserId": "AIDADRC4F7IR9EVJO4P7", "Arn": "arn:aws:iam::000000000000:user/lomax-dev", "CreateDate": "2026-09-29T13:23:48.372919+00:00" } }
- Se reutiliza el access key guardado en C:\Users\ALUMNO\AppData\Local\Temp\lomax-eks-access-key.json: AKIA77XCTPMTSI5VSHDR
- Las claves de demostracion test/test estan rechazadas por el webhook.
- Desde aqui el script se identifica como el usuario lomax-dev.

## Cluster EKS
- El cluster ya existia y estaba ACTIVE.
- Esperando a que el cluster quede ACTIVE...
- Estado: ACTIVE
- Endpoint: https://localhost:6500
- Version de Kubernetes: 1.29  (eks.1)
- OIDC: https://oidc.eks.us-east-1.amazonaws.com/id/9B3D9DF7535B469D935A2D6B3AA5F7C2

## Conexion con kubectl
### kubectl get nodes
```text
  NAME           STATUS   ROLES           AGE   VERSION        INTERNAL-IP   EXTERNAL-IP   OS-IMAGE           KERNEL-VERSION                      CONTAINER-RUNTIME
  0548cca56159   Ready    control-plane   20m   v1.34.1+k3s1   172.17.0.3    <none>        K3s v1.34.1+k3s1   6.18.33.2-microsoft-standard-WSL2   containerd://2.1.4-k3s2
```

- Nodo: 0548cca56159
- providerID: k3s://0548cca56159

## Direcciones de los servicios gestionados (fuera del cluster)
- Contenedor RDS: floci-rds-db-BE54F56ECC0141DC9E487EF4-d7e4da -> 172.19.0.6:3306
- Contenedor Floci: lomax-floci -> http://172.19.0.2:4566
- Las IPs se descubren en cada ejecucion porque Docker las reasigna.

## Aplicacion de los manifiestos
- Manifiestos renderizados en C:\Users\ALUMNO\AppData\Local\Temp\lomax-k8s-lomax
- Sustituidos: __IMAGE_TAG__, __AWS_ENDPOINT__, __RDS_HOST__, __RDS_PORT__

### kubectl apply
```text
  namespace/lomax unchanged
  configmap/lomax-config unchanged
  secret/lomax-secrets configured
  deployment.apps/lomax-backend unchanged
  service/lomax-backend unchanged
  deployment.apps/lomax-frontend unchanged
  service/lomax-frontend unchanged
  deployment.apps/lomax-proxy unchanged
  service/lomax-proxy unchanged
```

## Espera a que los Pods esten Ready
### kubectl wait --for=condition=Ready
```text
  NAME                              READY   STATUS    RESTARTS   AGE     IP           NODE           NOMINATED NODE   READINESS GATES
  lomax-backend-7d9c499499-8n5m5    1/1     Running   0          2m44s   10.42.0.9    0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-dtj8k    1/1     Running   0          2m44s   10.42.0.7    0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-s2b58    1/1     Running   0          60s     10.42.0.12   0548cca56159   <none>           <none>
  lomax-frontend-54b46ff667-htzpb   1/1     Running   0          2m44s   10.42.0.10   0548cca56159   <none>           <none>
  lomax-proxy-597bf6cd46-b9frs      1/1     Running   0          2m44s   10.42.0.11   0548cca56159   <none>           <none>
```

### kubectl get all -n lomax
```text
  NAME                                  READY   STATUS    RESTARTS   AGE
  pod/lomax-backend-7d9c499499-8n5m5    1/1     Running   0          2m46s
  pod/lomax-backend-7d9c499499-dtj8k    1/1     Running   0          2m46s
  pod/lomax-backend-7d9c499499-s2b58    1/1     Running   0          62s
  pod/lomax-frontend-54b46ff667-htzpb   1/1     Running   0          2m46s
  pod/lomax-proxy-597bf6cd46-b9frs      1/1     Running   0          2m46s
  
  NAME                     TYPE        CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
  service/lomax-backend    ClusterIP   10.43.79.202   <none>        5000/TCP       2m46s
  service/lomax-frontend   ClusterIP   10.43.95.229   <none>        80/TCP         2m46s
  service/lomax-proxy      NodePort    10.43.232.51   <none>        80:30080/TCP   2m46s
  
  NAME                             READY   UP-TO-DATE   AVAILABLE   AGE
  deployment.apps/lomax-backend    3/3     3            3           2m46s
  deployment.apps/lomax-frontend   1/1     1            1           2m46s
  deployment.apps/lomax-proxy      1/1     1            1           2m46s
  
  NAME                                        DESIRED   CURRENT   READY   AGE
  replicaset.apps/lomax-backend-7d9c499499    3         3         3       2m46s
  replicaset.apps/lomax-frontend-54b46ff667   1         1         1       2m46s
  replicaset.apps/lomax-proxy-597bf6cd46      1         1         1       2m46s
```

## Verificacion E7 a: el proxy es la entrada unica
- Tunel abierto: localhost:8081 -> service/lomax-proxy:80 en el namespace lomax
- El contenedor k3s de Floci solo publica su API server en el host, por eso el
  proxy del cluster se expone con port-forward y no con un NodePort alcanzable
  desde fuera. En AWS real lo haria un Service type LoadBalancer con ALB.

``` GET /proxy-health``` -> HTTP 200  {"status":"OK","service":"lomax-proxy"}
``` GET /api/health``` -> HTTP 200  {"service":"lomax-backend","status":"OK"}

``` GET /``` -> HTTP 200, 5287 bytes de HTML
``` GET /api/productos``` -> HTTP 200, 21 productos publicados
``` GET /api/productos/1/imagen``` -> HTTP 200, 3364 bytes

- OK: el catalogo completo se sirve desde Kubernetes a traves del proxy.
- OK: los datos vienen de RDS/DynamoDB/S3, que estan FUERA del cluster.

## Verificacion E7 b: escalamiento horizontal
Escalando lomax-backend de 1 a 3 replicas...
### kubectl get deployment lomax-backend
```text
  NAME            READY   UP-TO-DATE   AVAILABLE   AGE
  lomax-backend   3/3     3            3           2m54s
```

### kubectl get pods -l app=lomax-backend
```text
  NAME                             READY   STATUS    RESTARTS   AGE     IP           NODE           NOMINATED NODE   READINESS GATES
  lomax-backend-7d9c499499-8n5m5   1/1     Running   0          2m55s   10.42.0.9    0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-dtj8k   1/1     Running   0          2m55s   10.42.0.7    0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-s2b58   1/1     Running   0          71s     10.42.0.12   0548cca56159   <none>           <none>
```

### Pods del backend tras el escalamiento
```text
  lomax-backend-7d9c499499-8n5m5   4ec7f13c-5448-4ac3-86d8-803852eeedbf   10.42.0.9    0548cca56159   localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
  lomax-backend-7d9c499499-dtj8k   60e0f008-bf70-4caf-affe-563863661c3a   10.42.0.7    0548cca56159   localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
  lomax-backend-7d9c499499-s2b58   da1dabcd-d3f4-44a0-9ea5-5f05c1a3096d   10.42.0.12   0548cca56159   localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b
```

- OK: el Deployment mantiene 3 replicas del backend.

## Verificacion E7 c: autorrecuperacion
- Pod eliminado a proposito: lomax-backend-7d9c499499-8n5m5
- UID antes de eliminarlo:  4ec7f13c-5448-4ac3-86d8-803852eeedbf
- UIDs vivos antes de eliminar: 4ec7f13c-5448-4ac3-86d8-803852eeedbf, 60e0f008-bf70-4caf-affe-563863661c3a, da1dabcd-d3f4-44a0-9ea5-5f05c1a3096d

- Se ejecuto: kubectl delete pod lomax-backend-7d9c499499-8n5m5 --force --grace-period=0
### Pods tras la eliminacion
```text
  NAME                             READY   STATUS    RESTARTS   AGE    IP           NODE           NOMINATED NODE   READINESS GATES
  lomax-backend-7d9c499499-dtj8k   1/1     Running   0          3m8s   10.42.0.7    0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-lsjh8   1/1     Running   0          11s    10.42.0.13   0548cca56159   <none>           <none>
  lomax-backend-7d9c499499-s2b58   1/1     Running   0          84s    10.42.0.12   0548cca56159   <none>           <none>
```

- Pod de reemplazo: lomax-backend-7d9c499499-lsjh8
- UID del Pod de reemplazo: 9735e429-1bf4-4dc7-a814-b92db0a74adf
- OK: el Pod eliminado fue sustituido por uno INEXISTENTE antes, con otro UID,
  lo que demuestra que lo creo el Deployment y no era un Pod que ya estuviera.
- OK: el numero de replicas volvio a 3.
### Pods finales
```text
  lomax-backend-7d9c499499-dtj8k   60e0f008-bf70-4caf-affe-563863661c3a   true
  lomax-backend-7d9c499499-lsjh8   9735e429-1bf4-4dc7-a814-b92db0a74adf   true
  lomax-backend-7d9c499499-s2b58   da1dabcd-d3f4-44a0-9ea5-5f05c1a3096d   true
```

## Verificacion E7 d: los datos sobreviven a la recreacion de los Pods
``` GET /api/productos``` despues de recrear un Pod -> HTTP 200, 21 productos
- OK: el catalogo sigue completo. RDS y DynamoDB estan fuera del cluster, por eso
  recrear un Pod no pierde datos. Un volumen efimero tambien lo habria permitido,
  pero aqui el estado se comprobaria que vive en los servicios gestionados.

## Verificacion E7 e: las imagenes vienen de ECR
### Imagenes de los Pods
```text
  POD                               IMAGE                                                          IMAGE_ID
  lomax-backend-7d9c499499-dtj8k    localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b    localhost:4566/000000000000/us-east-1/lomax-backend@sha256:dfc2376b0b51985a30f16d8bef8afde9c1dd7d66bcf1a1132a0dd7e8e012ac8c
  lomax-backend-7d9c499499-lsjh8    localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b    localhost:4566/000000000000/us-east-1/lomax-backend@sha256:dfc2376b0b51985a30f16d8bef8afde9c1dd7d66bcf1a1132a0dd7e8e012ac8c
  lomax-backend-7d9c499499-s2b58    localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b    localhost:4566/000000000000/us-east-1/lomax-backend@sha256:dfc2376b0b51985a30f16d8bef8afde9c1dd7d66bcf1a1132a0dd7e8e012ac8c
  lomax-frontend-54b46ff667-htzpb   localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b   localhost:4566/000000000000/us-east-1/lomax-frontend@sha256:9830dd9fb2576f7d6f2b84484d4508a60dfb233b7b97c1fc860084c47abb369b
  lomax-proxy-597bf6cd46-b9frs      localhost:4566/000000000000/us-east-1/lomax-proxy:3ae406b      localhost:4566/000000000000/us-east-1/lomax-proxy@sha256:eeae775437a7fc7db018440152cec30b6849b4ddea76550cb8ea6defa6c4e499
```

- OK: todos los Pods ejecutan imagenes descargadas del registro ECR.
- OK: el clúster no reconstruyo ninguna imagen.


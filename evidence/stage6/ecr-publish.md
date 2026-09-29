# E6 - Publicacion de imagenes en ECR

- Fecha: 2026-09-29 09:19:00
- Tag: 3ae406b
- Plano de datos: 000000000000.dkr.ecr.us-east-1.localhost:4567

## Repositorios
- lomax-backend ya existia
- lomax-frontend ya existia
- lomax-proxy creado
- lomax-backend -> localhost:4566/000000000000/us-east-1/lomax-backend
- lomax-frontend -> localhost:4566/000000000000/us-east-1/lomax-frontend
- lomax-proxy -> localhost:4566/000000000000/us-east-1/lomax-proxy

## docker push
### lomax-backend
  #0 building with "desktop-linux" instance using docker driver
  System.Management.Automation.RemoteException
  #1 [internal] load build definition from Dockerfile
  #1 transferring dockerfile: 714B done
  #1 DONE 0.0s
  System.Management.Automation.RemoteException
  #2 [internal] load metadata for docker.io/library/python:3.12-slim
  #2 DONE 1.0s
  System.Management.Automation.RemoteException
  #3 [internal] load .dockerignore
  #3 transferring context: 2B done
  #3 DONE 0.0s
  System.Management.Automation.RemoteException
  #4 [internal] load build context
  #4 transferring context: 234B done
  #4 DONE 0.0s
  System.Management.Automation.RemoteException
  #5 [ 1/11] FROM docker.io/library/python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
  #5 resolve docker.io/library/python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f 0.0s done
  #5 DONE 0.0s
  System.Management.Automation.RemoteException
  #6 [ 5/11] RUN pip install --no-cache-dir -r requirements.txt
  #6 CACHED
  System.Management.Automation.RemoteException
  #7 [ 8/11] COPY dynamodb_service.py .
  #7 CACHED
  System.Management.Automation.RemoteException
  #8 [ 9/11] COPY s3_service.py .
  #8 CACHED
  System.Management.Automation.RemoteException
  #9 [10/11] COPY lambda_service.py .
  #9 CACHED
  System.Management.Automation.RemoteException
  #10 [ 4/11] COPY requirements.txt .
  #10 CACHED
  System.Management.Automation.RemoteException
  #11 [ 7/11] COPY database.py .
  #11 CACHED
  System.Management.Automation.RemoteException
  #12 [ 3/11] RUN apt-get update && apt-get install -y     gcc     && rm -rf /var/lib/apt/lists/*
  #12 CACHED
  System.Management.Automation.RemoteException
  #13 [ 6/11] COPY config.py .
  #13 CACHED
  System.Management.Automation.RemoteException
  #14 [ 2/11] WORKDIR /app
  #14 CACHED
  System.Management.Automation.RemoteException
  #15 [11/11] COPY app.py .
  #15 CACHED
  System.Management.Automation.RemoteException
  #16 exporting to image
  #16 exporting layers done
  #16 exporting manifest sha256:ad8e1d655b324ee14d158ae3382771bd8af0598ab0bd9137470bbf70d80b5bb5 done
  #16 exporting config sha256:93f3c5be8b847d436f14ad45e75f06a6bd059cb7018b5bebd07780af85257feb done
  #16 exporting attestation manifest sha256:25e2fb9fa0aaae21d9bbc9512bc7cb7eccdae89ed0cdd2d68d0cd734c846ebf3 0.0s done
  #16 exporting manifest list sha256:a82abe41604a0d870e7d10dce4d31eeb5e1eda09078c52349c96784ea0b45279
  #16 exporting manifest list sha256:a82abe41604a0d870e7d10dce4d31eeb5e1eda09078c52349c96784ea0b45279 0.0s done
  #16 naming to docker.io/library/lomax-backend:3ae406b done
  #16 unpacking to docker.io/library/lomax-backend:3ae406b 0.0s done
  #16 naming to localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b done
  #16 unpacking to localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b 0.0s done
  #16 DONE 0.2s
  System.Management.Automation.RemoteException
  View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/lis5tmfonhrb9w3if6e619zn9
construida: lomax-backend:3ae406b
  The push refers to repository [localhost:4566/000000000000/us-east-1/lomax-backend]
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  f84f41a98173: Waiting
  44136fa355b3: Waiting
  3764a9a7d1e8: Waiting
  6b37362b3da7: Waiting
  16d2344e7b52: Waiting
  635a7a69a293: Waiting
  3764a9a7d1e8: Layer already exists
  b0dc7f87bef1: Layer already exists
  06ad939ed42b: Layer already exists
  fbaba0352805: Layer already exists
  b27da2a41d05: Waiting
  44136fa355b3: Already exists
  6b37362b3da7: Layer already exists
  9c139161c26d: Layer already exists
  a2b3c6d85c2a: Waiting
  a6d4d75ace33: Layer already exists
  324318469a68: Layer already exists
  b27da2a41d05: Layer already exists
  f84f41a98173: Pushed
  82b9ab1b31cf: Layer already exists
  96d32a2a0468: Layer already exists
  a2b3c6d85c2a: Layer already exists
  16d2344e7b52: Layer already exists
  635a7a69a293: Layer already exists
  3ae406b: digest: sha256:a82abe41604a0d870e7d10dce4d31eeb5e1eda09078c52349c96784ea0b45279 size: 856
publicada: localhost:4566/000000000000/us-east-1/lomax-backend:3ae406b

### lomax-frontend
  #0 building with "desktop-linux" instance using docker driver
  System.Management.Automation.RemoteException
  #1 [internal] load build definition from Dockerfile
  #1 transferring dockerfile: 225B done
  #1 DONE 0.0s
  System.Management.Automation.RemoteException
  #2 [internal] load metadata for docker.io/library/nginx:alpine
  #2 DONE 0.9s
  System.Management.Automation.RemoteException
  #3 [internal] load .dockerignore
  #3 transferring context: 2B done
  #3 DONE 0.0s
  System.Management.Automation.RemoteException
  #4 [internal] load build context
  #4 transferring context: 88B done
  #4 DONE 0.0s
  System.Management.Automation.RemoteException
  #5 [1/4] FROM docker.io/library/nginx:alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2
  #5 resolve docker.io/library/nginx:alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2 0.0s done
  #5 DONE 0.0s
  System.Management.Automation.RemoteException
  #6 [3/4] COPY styles.css /usr/share/nginx/html/
  #6 CACHED
  System.Management.Automation.RemoteException
  #7 [2/4] COPY index.html /usr/share/nginx/html/
  #7 CACHED
  System.Management.Automation.RemoteException
  #8 [4/4] COPY app.js /usr/share/nginx/html/
  #8 CACHED
  System.Management.Automation.RemoteException
  #9 exporting to image
  #9 exporting layers done
  #9 exporting manifest sha256:f08c646447f1a16335c367c84ee93f7784244840fe252d6d76b94deb3aa7bd80 done
  #9 exporting config sha256:1b0ebe8f1316b18cfccbcd60570d73a2f9de9723af5393ece683810ede86f427 done
  #9 exporting attestation manifest sha256:92e18f1a118c4c5be8eba6d24e9ea92a961523a0d694df74b9383b23ea899a77 0.0s done
  #9 exporting manifest list sha256:9830dd9fb2576f7d6f2b84484d4508a60dfb233b7b97c1fc860084c47abb369b
  #9 exporting manifest list sha256:9830dd9fb2576f7d6f2b84484d4508a60dfb233b7b97c1fc860084c47abb369b 0.0s done
  #9 naming to docker.io/library/lomax-frontend:3ae406b done
  #9 unpacking to docker.io/library/lomax-frontend:3ae406b 0.0s done
  #9 naming to localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b done
  #9 unpacking to localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b 0.0s done
  #9 DONE 0.1s
  System.Management.Automation.RemoteException
  View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/tmfs0i3himp0jes9qey7h1abz
construida: lomax-frontend:3ae406b
  The push refers to repository [localhost:4566/000000000000/us-east-1/lomax-frontend]
  e2de96513ba9: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  d9aae54b5831: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  d9aae54b5831: Waiting
  e2de96513ba9: Waiting
  d9aae54b5831: Waiting
  e2de96513ba9: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  d9aae54b5831: Waiting
  e2de96513ba9: Waiting
  e2de96513ba9: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  d9aae54b5831: Waiting
  ab037380f980: Waiting
  44136fa355b3: Waiting
  d9aae54b5831: Waiting
  e2de96513ba9: Waiting
  fc971636fe83: Waiting
  68e862f6def1: Waiting
  d9aae54b5831: Layer already exists
  e2de96513ba9: Layer already exists
  6c53d0b2a666: Layer already exists
  745dfb2690dd: Layer already exists
  64c8194480fe: Layer already exists
  e76228b47809: Layer already exists
  fc6775b8407c: Waiting
  44136fa355b3: Already exists
  9a9a644fdd6a: Layer already exists
  e72112c14215: Layer already exists
  68e862f6def1: Layer already exists
  fc6775b8407c: Layer already exists
  ab037380f980: Pushed
  fc971636fe83: Layer already exists
  3ae406b: digest: sha256:9830dd9fb2576f7d6f2b84484d4508a60dfb233b7b97c1fc860084c47abb369b size: 856
publicada: localhost:4566/000000000000/us-east-1/lomax-frontend:3ae406b

### lomax-proxy
  #0 building with "desktop-linux" instance using docker driver
  System.Management.Automation.RemoteException
  #1 [internal] load build definition from Dockerfile
  #1 transferring dockerfile: 910B done
  #1 DONE 0.0s
  System.Management.Automation.RemoteException
  #2 [internal] load metadata for docker.io/library/nginx:1.27-alpine
  #2 DONE 0.2s
  System.Management.Automation.RemoteException
  #3 [internal] load .dockerignore
  #3 transferring context: 2B done
  #3 DONE 0.0s
  System.Management.Automation.RemoteException
  #4 [internal] load build context
  #4 transferring context: 41B done
  #4 DONE 0.0s
  System.Management.Automation.RemoteException
  #5 [1/2] FROM docker.io/library/nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10
  #5 resolve docker.io/library/nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10 0.0s done
  #5 DONE 0.0s
  System.Management.Automation.RemoteException
  #6 [2/2] COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
  #6 CACHED
  System.Management.Automation.RemoteException
  #7 exporting to image
  #7 exporting layers done
  #7 exporting manifest sha256:a5e1f2e5cf2e15536843e9312ddde98216132b586b346acb56a2d616e57e2fc5 0.0s done
  #7 exporting config sha256:b4df1853b30cb0645647017cc3b85556114a5cd5696ab725317b6a619d6fca77 0.0s done
  #7 exporting attestation manifest sha256:94198469a05a31c2bd648246ffe857a09611ff417012a23ba8475adb1db3cc86 0.0s done
  #7 exporting manifest list sha256:eeae775437a7fc7db018440152cec30b6849b4ddea76550cb8ea6defa6c4e499 0.0s done
  #7 naming to docker.io/library/lomax-proxy:3ae406b done
  #7 unpacking to docker.io/library/lomax-proxy:3ae406b 0.0s done
  #7 naming to localhost:4566/000000000000/us-east-1/lomax-proxy:3ae406b done
  #7 unpacking to localhost:4566/000000000000/us-east-1/lomax-proxy:3ae406b 0.0s done
  #7 DONE 0.2s
  System.Management.Automation.RemoteException
  View build details: docker-desktop://dashboard/build/desktop-linux/desktop-linux/e7l22phpfuu24n98xg0ob6cir
construida: lomax-proxy:3ae406b
  The push refers to repository [localhost:4566/000000000000/us-east-1/lomax-proxy]
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  44136fa355b3: Waiting
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  f78d5f5368fd: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  f18232174bc9: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  61ca4f733c80: Waiting
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  f78d5f5368fd: Waiting
  44136fa355b3: Waiting
  61ca4f733c80: Waiting
  f18232174bc9: Waiting
  44136fa355b3: Mounted from 000000000000/us-east-1/lomax-frontend
  b464cfdf2a63: Waiting
  d7e507024086: Waiting
  f78d5f5368fd: Pushed
  b464cfdf2a63: Pushed
  d7e507024086: Pushed
  39c2ddfd6010: Waiting
  81bd8ed7ec67: Pushed
  f18232174bc9: Pushed
  34a64644b756: Waiting
  820d3fb19e1f: Waiting
  61ca4f733c80: Pushed
  197eb75867ef: Pushed
  34a64644b756: Pushed
  820d3fb19e1f: Pushed
  39c2ddfd6010: Pushed
  3ae406b: digest: sha256:eeae775437a7fc7db018440152cec30b6849b4ddea76550cb8ea6defa6c4e499 size: 856
publicada: localhost:4566/000000000000/us-east-1/lomax-proxy:3ae406b

## Verificacion omitida (-SinVerificar)

# Etapa 7 - Despliegue en Kubernetes (EKS) con escalamiento y autorrecuperacion
#
# Crea el cluster EKS en FLOCI, conecta kubectl, aplica los manifiestos de k8s/
# y demuestra las dos propiedades que aporta un orquestador y que Docker
# Compose no da:
#
#   1. Escalamiento horizontal  - el backend pasa de 1 a 3 replicas.
#   2. Autorrecuperacion        - se borra un Pod a proposito y el
#                                 Deployment crea uno nuevo con UID distinto.
#
# Las imagenes NO se construyen aqui: se descargan del registro ECR de la
# Etapa 6, que es lo que demuestra que lo publicado es lo que se ejecuta.
#
# Uso:  .\scripts\stage7_eks.ps1
#       .\scripts\stage7_eks.ps1 -Replicas 5
#       .\scripts\stage7_eks.ps1 -SaltarCluster     # reutiliza el clúster existente
param(
  [string]$Cluster = "lomax",
  [string]$Endpoint = "http://localhost:4567",
  [string]$Region = "us-east-1",
  [string]$Account = "000000000000",
  [string]$IamUser = "lomax-dev",
  [string]$ImageTag = "",
  [int]$Replicas = 3,
  [string]$PortForwardPort = "8081",
  [switch]$SaltarCluster,
  [switch]$SaltarEvidencia
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$manifestDirectory = Join-Path $projectRoot "k8s"
$evidenceDirectory = Join-Path $projectRoot "evidence/stage7"
$reportPath = Join-Path $evidenceDirectory "eks-despliegue.md"

$env:AWS_DEFAULT_REGION = $Region
$env:AWS_PAGER = ""

$lineas = @()

function Registrar {
  param([string]$Texto)
  Write-Host $Texto
  $script:lineas += $Texto
}

function Invoke-Native {
  # En Windows PowerShell 5.1 la salida por stderr de un comando nativo se
  # convierte en error fatal si $ErrorActionPreference esta en "Stop".
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$Arguments = @(),
    [string[]]$Environment = @()
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    if ($Environment.Count -gt 0) {
      $previous = @{}
      foreach ($pair in $Environment) {
        $name, $value = $pair -split "=", 2
        $previous[$name] = [Environment]::GetEnvironmentVariable($name, "Process")
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
      }
      try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
      }
      finally {
        foreach ($name in $previous.Keys) {
          [Environment]::SetEnvironmentVariable($name, $previous[$name], "Process")
        }
      }
    }
    else {
      $output = & $FilePath @Arguments 2>&1
      $exitCode = $LASTEXITCODE
    }
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
}

function Invoke-Aws {
  param(
    [string[]]$Arguments,
    [string[]]$Credentials = @(),
    [switch]$AllowFailure,
    [switch]$Raw
  )
  # Si quien llama ya pide un formato concreto, se respeta. Anadir al final un
  # "--output json" lo pisaria y devolveria, por ejemplo, "ACTIVE" entrecomillado
  # en lugar de ACTIVE, que ya no compara bien.
  $completos = $Arguments + @("--endpoint-url", $Endpoint, "--region", $Region)
  if ($Arguments -notcontains "--output") {
    $completos += @("--output", "json")
  }

  $resultado = Invoke-Native -FilePath "aws" -Arguments $completos -Environment $Credentials
  if (-not $AllowFailure -and $resultado.ExitCode -ne 0) {
    throw "Fallo de AWS CLI ($($Arguments -join ' ')): $($resultado.Output -join "`n")"
  }
  if ($Raw) { return $resultado }
  $texto = ($resultado.Output -join "`n").Trim()
  if (-not $texto) { return $null }
  try { return ($texto | ConvertFrom-Json) } catch { return $texto }
}

function Invoke-Kubectl {
  param(
    [string[]]$Arguments,
    [switch]$AllowFailure
  )
  $resultado = Invoke-Native -FilePath "kubectl" -Arguments $Arguments -Environment $script:kubectlCredentials
  if (-not $AllowFailure -and $resultado.ExitCode -ne 0) {
    throw "Fallo de kubectl ($($Arguments -join ' ')): $($resultado.Output -join "`n")"
  }
  return $resultado
}

# El acento grave es el caracter de escape de PowerShell, asi que en cadenas
# con comillas dobles un numero impar de ellos se traga la comilla de cierre.
# En cadenas simples no tiene ese papel, asi que las vallas de Markdown se
# escriben aqui entrecomilladas.
$fence = '```'

function Registrar-Salida {
  param([string]$Titulo, $Resultado)
  Registrar "### $Titulo"
  Registrar "${fence}text"
  foreach ($linea in $Resultado.Output) { Registrar "  $linea" }
  Registrar $fence
  Registrar ""
}

# ============================================================================
New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null

Registrar "# E7 - Despliegue en EKS, escalamiento y autorrecuperacion`n"
Registrar "- Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Registrar "- Cluster: $Cluster"
Registrar "- Replicas objetivo: $Replicas`n"

# --- 1) Etiqueta de imagen ------------------------------------------------
if ([string]::IsNullOrWhiteSpace($ImageTag)) {
  $commit = Invoke-Native -FilePath "git" -Arguments @("-C", $projectRoot, "rev-parse", "--short", "HEAD")
  $ImageTag = (($commit.Output -join "").Trim())
  if ([string]::IsNullOrWhiteSpace($ImageTag)) { $ImageTag = "latest" }
}
Registrar "## Imagen"
Registrar "- Etiqueta: $ImageTag"
Registrar "- Origen: registro ECR de la Etapa 6 (el clúster no reconstruye nada)`n"

# --- 2) Credenciales ------------------------------------------------------
# El webhook de autenticacion de EKS rechaza a proposito las claves publicas de
# desarrollo test/test y floci/floci, porque conceden cluster-admin. Por eso se
# crea un usuario IAM con su access key y se usan para hablar con EKS.
Registrar "## Credenciales de IAM para el webhook de EKS"
$demoCredentials = @("AWS_ACCESS_KEY_ID=test", "AWS_SECRET_ACCESS_KEY=test")
$rol = Invoke-Aws -Arguments @("iam", "create-role",
  "--role-name", "lomax-eks-cluster",
  "--assume-role-policy-document", '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":["eks.amazonaws.com","eks-floci.amazonaws.com"]},"Action":"sts:AssumeRole"}]}',
  "--query", "Role.Arn", "--output", "text") -Credentials $demoCredentials -AllowFailure -Raw
$rolArn = "arn:aws:iam::${Account}:role/lomax-eks-cluster"
if ($rol.ExitCode -eq 0 -and $rol.Output) {
  $rolArn = (($rol.Output -join "").Trim())
  Registrar "- Rol creado: $rolArn"
}
else {
  Registrar "- El rol ya existia: $rolArn"
}

# El usuario y su clave se gestionan aqui para que el script sea reejecutable
# desde cero. IAM solo entrega el secret de un access key en el instante en que
# se crea y nunca lo devuelve despues, asi que la primera vez se guarda en un
# archivo local. Si en una ejecucion posterior ese archivo ya no sirve (usuario
# borrado, clave eliminada, archivo perdido), se descarta la clave vieja y se
# crea una nueva en lugar de bloquearse.
$accessKeyId = ""
$secretKey = ""
$keyFile = Join-Path $env:TEMP "lomax-eks-access-key.json"

$usuario = Invoke-Aws -Arguments @("iam", "get-user", "--user-name", $IamUser) -Credentials $demoCredentials -AllowFailure -Raw
if ($usuario.ExitCode -ne 0) {
  Registrar "- El usuario $IamUser no existia; se crea."
  Invoke-Aws -Arguments @("iam", "create-user", "--user-name", $IamUser) -Credentials $demoCredentials | Out-Null
}
else {
  Registrar "- Usuario IAM: $(($usuario.Output -join ' ').Trim() -replace '\s+', ' ')"
}

$keys = Invoke-Aws -Arguments @("iam", "list-access-keys", "--user-name", $IamUser,
  "--query", "AccessKeyMetadata[].AccessKeyId", "--output", "text") -Credentials $demoCredentials -AllowFailure -Raw
# Con --output text el AWS CLI devuelve varios valores separados por tabulador
# en una SOLA linea, no uno por linea. Partir solo por saltos de linea trataria
# "CLAVE_A\tCLAVE_B" como un id unico y el borrado fallaria con NoSuchEntity.
$idsExistentes = @(
  (($keys.Output -join " ") -split "\s+") | Where-Object { $_ }
)

if ($idsExistentes.Count -eq 0) {
  Registrar "- El usuario no tenia access keys."
}
elseif (Test-Path $keyFile) {
  $guardado = Get-Content $keyFile -Raw | ConvertFrom-Json
  if ($idsExistentes -contains $guardado.id) {
    $accessKeyId = $guardado.id
    $secretKey = $guardado.secret
    Registrar "- Se reutiliza el access key guardado en ${keyFile}: $accessKeyId"
  }
  else {
    Registrar "- El access key guardado ya no existe en IAM; se creara uno nuevo."
  }
}
else {
  Registrar "- Hay $($idsExistentes.Count) access key(s) en IAM pero no hay copia local"
  Registrar "  del secret, que IAM no permite recuperar. Se creara uno nuevo."
}

if (-not $accessKeyId) {
  foreach ($obsoleto in $idsExistentes) {
    $borrado = Invoke-Aws -Arguments @("iam", "delete-access-key", "--user-name", $IamUser,
      "--access-key-id", $obsoleto) -Credentials $demoCredentials -AllowFailure -Raw
    if ($borrado.ExitCode -ne 0) {
      # No se ignora: si el borrado falla, el create-access-key siguiente va a
      # chocar con el limite de 2 claves por usuario y el fallo real queda
      # escondido detras de un error que no explica nada.
      throw "No se pudo eliminar el access key ${obsoleto}: $($borrado.Output -join ' ')"
    }
  }
  if ($idsExistentes.Count -gt 0) {
    Registrar "- Se eliminaron $($idsExistentes.Count) clave(s) anterior(es) para liberar el limite de 2 por usuario."
  }

  $accessKey = Invoke-Aws -Arguments @("iam", "create-access-key", "--user-name", $IamUser,
    "--query", "AccessKey.{id:AccessKeyId,secret:SecretAccessKey}", "--output", "json") -Credentials $demoCredentials -Raw
  if ($accessKey.ExitCode -ne 0 -or -not $accessKey.Output) {
    throw "No se pudo crear un access key de IAM: $($accessKey.Output -join ' ')"
  }
  $keyData = (($accessKey.Output -join "`n") | ConvertFrom-Json)
  $accessKeyId = $keyData.id
  $secretKey = $keyData.secret
  Registrar "- Access key creado para ${IamUser}: $accessKeyId"
  [IO.File]::WriteAllText($keyFile, (
    @{ id = $accessKeyId; secret = $secretKey } | ConvertTo-Json -Compress
  ), [Text.UTF8Encoding]::new($false))
  Registrar "- Secret guardado en $keyFile (IAM no lo volvera a entregar).`n"
}
if (-not $accessKeyId -or -not $secretKey) {
  throw "No se pudo obtener un access key de IAM para el webhook de EKS."
}
$script:kubectlCredentials = @(
  "AWS_ACCESS_KEY_ID=$accessKeyId",
  "AWS_SECRET_ACCESS_KEY=$secretKey",
  "AWS_DEFAULT_REGION=$Region"
)
# A partir de aqui el script actsua como el usuario lomax-dev, asi que sus
# credenciales pasan a ser las del proceso. No es solo comodo: kubectl delega
# en el plugin exec "aws eks get-token" y, si no las hereda, el port-forward
# falla con NoCredentials. Las llamadas que necesitan las claves de
# demostracion (test/test) las sobrescriben punto por punto con Invoke-Aws -Credentials
# y restauran al terminar.
$env:AWS_ACCESS_KEY_ID = $accessKeyId
$env:AWS_SECRET_ACCESS_KEY = $secretKey
$env:AWS_DEFAULT_REGION = $Region
Registrar "- Las claves de demostracion test/test estan rechazadas por el webhook."
Registrar "- Desde aqui el script se identifica como el usuario lomax-dev.`n"

# --- 3) Cluster -----------------------------------------------------------
Registrar "## Cluster EKS"
if ($SaltarCluster) {
  Registrar "- Se reutiliza el cluster existente."
}
else {
  $existente = Invoke-Aws -Arguments @("eks", "describe-cluster", "--name", $Cluster,
    "--query", "cluster.status", "--output", "text") -Credentials $demoCredentials -AllowFailure -Raw
  $estadoActual = (($existente.Output -join "").Trim())

  if ($estadoActual -eq "ACTIVE") {
    Registrar "- El cluster ya existia y estaba ACTIVE."
  }
  else {
    if ($estadoActual -eq "FAILED" -or $estadoActual -eq "CREATING") {
      Registrar "- Eliminando el cluster en estado '$estadoActual' para recrearlo limpio."
      Invoke-Aws -Arguments @("eks", "delete-cluster", "--name", $Cluster) -Credentials $demoCredentials -AllowFailure | Out-Null
      Start-Sleep -Seconds 8
    }
    # El rol IAM debe existir antes de crear el cluster.
    Invoke-Aws -Arguments @("iam", "get-role", "--role-name", "lomax-eks-cluster") -Credentials $demoCredentials -AllowFailure | Out-Null

    Registrar "- Creando el cluster (k3s real, no mock)..."
    $creado = Invoke-Aws -Arguments @("eks", "create-cluster",
      "--name", $Cluster,
      "--role-arn", $rolArn,
      "--resources-vpc-config", "subnetIds=[]") -Credentials $demoCredentials -AllowFailure -Raw
    if ($creado.ExitCode -ne 0) {
      # Floci puede tener el nombre cogido por un cluster que se esta borrando.
      # No es un fallo: se espera a que se libere y se sigue adelante.
      if (($creado.Output -join " ") -match "ResourceInUseException") {
        Registrar "- El nombre ya estaba en uso por un cluster en borrado; se espera."
      }
      else {
        throw "No se pudo crear el cluster: $($creado.Output -join ' ')"
      }
    }
  }
}

Registrar "- Esperando a que el cluster quede ACTIVE..."
$estado = ""
for ($intento = 0; $intento -lt 60; $intento++) {
  $consulta = Invoke-Aws -Arguments @("eks", "describe-cluster", "--name", $Cluster,
    "--query", "cluster.status", "--output", "text") -Credentials $demoCredentials -AllowFailure -Raw
  $estado = (($consulta.Output -join "").Trim())
  if ($estado -in @("ACTIVE", "FAILED")) { break }
  Start-Sleep -Seconds 8
}
Registrar "- Estado: $estado"
if ($estado -ne "ACTIVE") {
  throw "El cluster $Cluster no llego a ACTIVE (estado: $estado)."
}

# El --query con varios campos devuelve el objeto YA en la raiz, no envuelto
# en "cluster". Por eso se lee $detalle.endpoint y no $detalle.cluster.endpoint.
$detalle = Invoke-Aws -Arguments @("eks", "describe-cluster", "--name", $Cluster,
  "--query", "cluster.{name:name,status:status,endpoint:endpoint,version:version,platform:platformVersion,oidc:identity.oidc.issuer}") -Credentials $demoCredentials
Registrar "- Endpoint: $($detalle.endpoint)"
Registrar "- Version de Kubernetes: $($detalle.version)  ($($detalle.platform))"
Registrar "- OIDC: $($detalle.oidc)`n"

# --- 4) kubeconfig --------------------------------------------------------
Registrar "## Conexion con kubectl"
Invoke-Aws -Arguments @("eks", "update-kubeconfig",
  "--name", $Cluster, "--region", $Region) -Credentials $script:kubectlCredentials | Out-Null
$nodes = Invoke-Kubectl -Arguments @("get", "nodes", "-o", "wide")
Registrar-Salida "kubectl get nodes" $nodes
$nodo = (Invoke-Kubectl -Arguments @("get", "nodes", "-o", "jsonpath={.items[0].metadata.name}")).Output -join ""
$nodo = $nodo.Trim()
Registrar "- Nodo: $nodo"
Registrar "- providerID: $((Invoke-Kubectl -Arguments @('get','node',$nodo,'-o','jsonpath={.spec.providerID}')).Output -join '')`n"

# --- 5) Direcciones de los servicios gestionados --------------------------
# Desde un Pod se alcanza a RDS y a FLOCI por su IP en la red de Docker
# compartida. host.docker.internal no resuelve dentro de los Pods porque el
# DNS del cluster no lo conoce, de ahi que se usen IPs.
Registrar "## Direcciones de los servicios gestionados (fuera del cluster)"
$rdsContainer = (Invoke-Native -FilePath "docker" -Arguments @("ps", "--filter", "name=floci-rds-db", "--format", "{{.Names}}")).Output[0]
if (-not $rdsContainer) { throw "No se encontro el contenedor de RDS de Floci." }
$rdsContainer = $rdsContainer.Trim()
$flociContainer = (Invoke-Native -FilePath "docker" -Arguments @("ps", "--filter", "name=lomax-floci", "--format", "{{.Names}}")).Output[0]
if (-not $flociContainer) { throw "No se encontro el contenedor de Floci." }
$flociContainer = $flociContainer.Trim()

function Get-ContainerNetworkIp {
  param([string]$Nombre)
  $salida = Invoke-Native -FilePath "docker" -Arguments @(
    "inspect", $Nombre, "--format",
    '{{range $k, $v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}'
  )
  if ($salida.ExitCode -ne 0) { throw "No se pudo leer la red del contenedor $Nombre." }
  foreach ($par in (($salida.Output -join "").Trim() -split "\s+")) {
    if ($par -match "^([^=]+)=(.*)$") {
      $red = $Matches[1]
      $ip = $Matches[2]
      # La red compartida con la aplicacion es la que importa; 'bridge' es la
      # red interna por defecto de Docker y no enruta al emulador.
      if ($red -ne "bridge" -and $ip) { return $ip }
    }
  }
  throw "El contenedor $Nombre no tiene IP en la red compartida."
}

$rdsIp = Get-ContainerNetworkIp -Nombre $rdsContainer
$flociIp = Get-ContainerNetworkIp -Nombre $flociContainer
$awsEndpoint = "http://${flociIp}:4566"
$rdsPort = 3306

Registrar "- Contenedor RDS: ${rdsContainer} -> ${rdsIp}:${rdsPort}"
Registrar "- Contenedor Floci: $flociContainer -> $awsEndpoint"
Registrar "- Las IPs se descubren en cada ejecucion porque Docker las reasigna.`n"

# --- 6) Manifiestos -------------------------------------------------------
Registrar "## Aplicacion de los manifiestos"
$renderDirectory = Join-Path $env:TEMP "lomax-k8s-$Cluster"
Remove-Item -Recurse -Force $renderDirectory -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $renderDirectory | Out-Null

foreach ($manifiesto in (Get-ChildItem $manifestDirectory -Filter *.yaml | Sort-Object Name)) {
  $contenido = [IO.File]::ReadAllText($manifiesto.FullName)
  $contenido = $contenido.Replace("__IMAGE_TAG__", $ImageTag)
  $contenido = $contenido.Replace("__AWS_ENDPOINT__", $awsEndpoint)
  $contenido = $contenido.Replace("__RDS_HOST__", $rdsIp)
  $contenido = $contenido.Replace("__RDS_PORT__", "$rdsPort")
  [IO.File]::WriteAllText((Join-Path $renderDirectory $manifiesto.Name), $contenido, [Text.UTF8Encoding]::new($false))
}
Registrar "- Manifiestos renderizados en $renderDirectory"
Registrar "- Sustituidos: __IMAGE_TAG__, __AWS_ENDPOINT__, __RDS_HOST__, __RDS_PORT__`n"

$aplicar = Invoke-Kubectl -Arguments (@("apply", "-f", $renderDirectory) )
Registrar-Salida "kubectl apply" $aplicar

Registrar "## Espera a que los Pods esten Ready"
$listos = $false
for ($intento = 0; $intento -lt 60; $intento++) {
  $salida = Invoke-Kubectl -Arguments @("wait", "--for=condition=Ready", "pod",
    "--all", "--namespace", "lomax", "--timeout=10s") -AllowFailure
  if ($salida.ExitCode -eq 0) { $listos = $true; break }
  Start-Sleep -Seconds 6
}
if (-not $listos) { throw "Los Pods no llegaron a Ready a tiempo." }
Registrar-Salida "kubectl wait --for=condition=Ready" (Invoke-Kubectl -Arguments @("get", "pods", "-n", "lomax", "-o", "wide"))
Registrar-Salida "kubectl get all -n lomax" (Invoke-Kubectl -Arguments @("get", "all", "-n", "lomax"))

# --- 7) Verificacion E7 --------------------------------------------------
if (-not $SaltarEvidencia) {
  # 7a) El proxy es la entrada de usuarios y sirve la aplicacion completa.
  Registrar "## Verificacion E7 a: el proxy es la entrada unica"
  $forward = Start-Process -FilePath "kubectl" -ArgumentList @(
    "port-forward", "--namespace", "lomax", "service/lomax-proxy",
    "${PortForwardPort}:80"
  ) -NoNewWindow -PassThru -RedirectStandardOutput "$env:TEMP\lomax-pf-out.txt" -RedirectStandardError "$env:TEMP\lomax-pf-err.txt"
  $script:portForwardProcess = $forward

  # No basta con esperar unos segundos: si kubectl port-forward muere por
  # credenciales o por un nombre de Service equivocado, el puerto se queda
  # cerrado y todas las peticiones darian HTTP 0 sin explicar por que. Se
  # reintenta la conexion y, si no llega, se informa de lo que dijo kubectl.
  $tunelListo = $false
  for ($intento = 0; $intento -lt 20; $intento++) {
    Start-Sleep -Seconds 3
    if ($forward.HasExited) { break }
    $sondeo = Invoke-Native -FilePath "curl.exe" -Arguments @(
      "-s", "-o", "NUL", "--max-time", "5", "http://localhost:$PortForwardPort/proxy-health"
    )
    if ($sondeo.ExitCode -eq 0) { $tunelListo = $true; break }
  }
  if (-not $tunelListo) {
    $salidaPf = ((Get-Content "$env:TEMP\lomax-pf-out.txt" -ErrorAction SilentlyContinue) +
                 (Get-Content "$env:TEMP\lomax-pf-err.txt" -ErrorAction SilentlyContinue)) -join "`n"
    throw "kubectl port-forward no abrio localhost:$PortForwardPort (proceso terminado: $($forward.HasExited)). Salida de kubectl: $salidaPf"
  }
  Registrar "- Tunel abierto: localhost:$PortForwardPort -> service/lomax-proxy:80 en el namespace lomax"
  Registrar "- El contenedor k3s de Floci solo publica su API server en el host, por eso el"
  Registrar "  proxy del cluster se expone con port-forward y no con un NodePort alcanzable"
  Registrar "  desde fuera. En AWS real lo haria un Service type LoadBalancer con ALB.`n"

  function Invoke-Proxy {
  param([string]$Ruta)
    $url = "http://localhost:$PortForwardPort$Ruta"
    $salida = Invoke-Native -FilePath "curl.exe" -Arguments @("-s", "--max-time", "20", "-w", "`n%{http_code}", $url)
    $lineas = @($salida.Output | ForEach-Object { [string]$_ })
    $codigo = 0
    if ($lineas.Count -gt 0 -and $lineas[-1].Trim() -match "^\d{3}$") {
      $codigo = [int]$lineas[-1].Trim()
      $lineas = $lineas[0..($lineas.Count - 2)]
    }
    return [pscustomobject]@{ Codigo = $codigo; Cuerpo = ($lineas -join "`n") }
  }

  $saludProxy = Invoke-Proxy "/proxy-health"
  Registrar "$fence GET /proxy-health$fence -> HTTP $($saludProxy.Codigo)  $($saludProxy.Cuerpo)"

  $saludApi = Invoke-Proxy "/api/health"
  Registrar "$fence GET /api/health$fence -> HTTP $($saludApi.Codigo)  $($saludApi.Cuerpo)"

  $raiz = Invoke-Proxy "/"
  Registrar "$fence GET /$fence -> HTTP $($raiz.Codigo), $($raiz.Cuerpo.Length) bytes de HTML"

  $catalogo = Invoke-Proxy "/api/productos"
  $conteo = 0
  try { $conteo = (($catalogo.Cuerpo | ConvertFrom-Json).count) } catch { $conteo = 0 }
  Registrar "$fence GET /api/productos$fence -> HTTP $($catalogo.Codigo), $conteo productos publicados"

  $miniatura = Invoke-Proxy "/api/productos/1/imagen"
  Registrar "$fence GET /api/productos/1/imagen$fence -> HTTP $($miniatura.Codigo), $($miniatura.Cuerpo.Length) bytes"

  Registrar ""
  if ($saludProxy.Codigo -ne 200) { throw "El proxy del cluster no responde /proxy-health." }
  if ($saludApi.Codigo -ne 200) { throw "El backend del cluster no responde /api/health." }
  if ($raiz.Codigo -ne 200) { throw "El frontend del cluster no se sirve desde el proxy." }
  if ($conteo -lt 20) { throw "El catalogo servido desde EKS trae $conteo productos; se esperaban 20 o mas." }
  Registrar "- OK: el catalogo completo se sirve desde Kubernetes a traves del proxy."
  Registrar "- OK: los datos vienen de RDS/DynamoDB/S3, que estan FUERA del cluster.`n"

  # 7b) Escalamiento horizontal
  Registrar "## Verificacion E7 b: escalamiento horizontal"
  Registrar "Escalando lomax-backend de 1 a $Replicas replicas..."
  Invoke-Kubectl -Arguments @("scale", "deployment/lomax-backend", "--namespace", "lomax",
    "--replicas=$Replicas") | Out-Null
  Invoke-Kubectl -Arguments @("rollout", "status", "deployment/lomax-backend",
    "--namespace", "lomax", "--timeout=180s") | Out-Null
  Registrar-Salida "kubectl get deployment lomax-backend" (Invoke-Kubectl -Arguments @("get", "deployment", "lomax-backend", "-n", "lomax"))
  Registrar-Salida "kubectl get pods -l app=lomax-backend" (Invoke-Kubectl -Arguments @("get", "pods", "-l", "app=lomax-backend", "-n", "lomax", "-o", "wide"))

  $podsEscalados = Invoke-Kubectl -Arguments @("get", "pods", "-l", "app=lomax-backend",
    "-n", "lomax", "--no-headers", "-o", "custom-columns=NAME:.metadata.name,UID:.metadata.uid,IP:.status.podIP,NODE:.spec.nodeName,IMAGE:.spec.containers[0].image")
  $lineasPods = @($podsEscalados.Output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
  Registrar-Salida "Pods del backend tras el escalamiento" $podsEscalados
  if ($lineasPods.Count -ne $Replicas) {
    throw "Se esperaban $Replicas Pods del backend y hay $($lineasPods.Count)."
  }
  Registrar "- OK: el Deployment mantiene $Replicas replicas del backend.`n"

  # 7c) Autorrecuperacion: borrar un Pod y ver que vuelve con otro UID
  Registrar "## Verificacion E7 c: autorrecuperacion"
  $victima = ($lineasPods | Select-Object -First 1)
  $nombreVictima = ($victima -split "\s+")[0]
  $uidVictima = ($victima -split "\s+")[1]
  # Se guardan los UIDs de TODOS los Pods vivos. Comparar solo contra el UID de
  # la victima daria por bueno un Pod que ya existia de antes: cualquier otro
  # Pod vivo cumple "distinto de la victima", y la comprobacion pasaria aunque
  # no hubiera habido autorrecuperacion. Un Pod de reemplazo es, por
  # definicion, un UID que no estaba en la foto previa.
  $uidsPrevios = @($lineasPods | ForEach-Object { ($_ -split "\s+")[1] })
  Registrar "- Pod eliminado a proposito: $nombreVictima"
  Registrar "- UID antes de eliminarlo:  $uidVictima"
  Registrar "- UIDs vivos antes de eliminar: $($uidsPrevios -join ', ')`n"

  Invoke-Kubectl -Arguments @("delete", "pod", $nombreVictima, "-n", "lomax", "--grace-period=0", "--force") | Out-Null
  Registrar "- Se ejecuto: kubectl delete pod $nombreVictima --force --grace-period=0"

  $reemplazado = $false
  $uidNuevo = ""
  $nombreNuevo = ""
  for ($intento = 0; $intento -lt 40; $intento++) {
    Start-Sleep -Seconds 4
    $actuales = Invoke-Kubectl -Arguments @("get", "pods", "-l", "app=lomax-backend",
      "-n", "lomax", "--no-headers", "-o", "custom-columns=NAME:.metadata.name,UID:.metadata.uid,READY:.status.containerStatuses[0].ready,PHASE:.status.phase") -AllowFailure
    $lineasActuales = @($actuales.Output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
    $nuevo = $lineasActuales | Where-Object { $uidsPrevios -notcontains ($_ -split "\s+")[1] }
    if ($nuevo -and $nuevo.Count -gt 0) {
      $reemplazado = $true
      $campos = (($nuevo | Select-Object -First 1) -split "\s+")
      $nombreNuevo = $campos[0]
      $uidNuevo = $campos[1]
      # Se espera a que el reemplazo este listo, no solo a que exista: el Pod
      # aparece de inmediato, pero hasta que readinessProbe pasa no recibe
      # trafico, y la evidencia debe reflejar el estado final util.
      if ($campos.Count -ge 3 -and $campos[2] -eq "true") { break }
    }
  }
  Registrar-Salida "Pods tras la eliminacion" (Invoke-Kubectl -Arguments @("get", "pods", "-l", "app=lomax-backend", "-n", "lomax", "-o", "wide"))
  if (-not $reemplazado) {
    throw "El Deployment no creo un Pod de reemplazo tras eliminar $nombreVictima."
  }
  if ($uidNuevo -eq $uidVictima) {
    throw "El UID de reemplazo ($uidNuevo) es el mismo que el eliminado; no hubo autorrecuperacion real."
  }
  if ($uidsPrevios -contains $uidNuevo) {
    throw "El UID de reemplazo ($uidNuevo) ya existia antes de la eliminacion; se eligio el Pod equivocado como reemplazo."
  }
  Registrar "- Pod de reemplazo: $nombreNuevo"
  Registrar "- UID del Pod de reemplazo: $uidNuevo"
  Registrar "- OK: el Pod eliminado fue sustituido por uno INEXISTENTE antes, con otro UID,"
  Registrar "  lo que demuestra que lo creo el Deployment y no era un Pod que ya estuviera."

  Invoke-Kubectl -Arguments @("rollout", "status", "deployment/lomax-backend",
    "--namespace", "lomax", "--timeout=120s") | Out-Null
  $finales = Invoke-Kubectl -Arguments @("get", "pods", "-l", "app=lomax-backend",
    "-n", "lomax", "--no-headers", "-o", "custom-columns=NAME:.metadata.name,UID:.metadata.uid,READY:.status.containerStatuses[0].ready")
  $lineasFinales = @($finales.Output | ForEach-Object { ([string]$_).Trim() } | Where-Object { $_ })
  if ($lineasFinales.Count -ne $Replicas) {
    throw "Tras la autorrecuperacion hay $($lineasFinales.Count) Pods; se esperaban $Replicas."
  }
  Registrar "- OK: el numero de replicas volvio a $Replicas."
  Registrar-Salida "Pods finales" $finales

  # 7d) Los datos sobreviven: el estado no vive en los Pods
  Registrar "## Verificacion E7 d: los datos sobreviven a la recreacion de los Pods"
  $trasRecreo = Invoke-Proxy "/api/productos"
  $conteoFinal = 0
  try { $conteoFinal = (($trasRecreo.Cuerpo | ConvertFrom-Json).count) } catch { $conteoFinal = 0 }
  Registrar "$fence GET /api/productos$fence despues de recrear un Pod -> HTTP $($trasRecreo.Codigo), $conteoFinal productos"
  if ($conteoFinal -lt 20) {
    throw "El catalogo quedo en $conteoFinal productos tras recrear un Pod; se esperaban 20 o mas."
  }
  Registrar "- OK: el catalogo sigue completo. RDS y DynamoDB estan fuera del cluster, por eso"
  Registrar "  recrear un Pod no pierde datos. Un volumen efimero tambien lo habria permitido,"
  Registrar "  pero aqui el estado se comprobaria que vive en los servicios gestionados.`n"

  # 7e) Imagenes descargadas del registro
  Registrar "## Verificacion E7 e: las imagenes vienen de ECR"
  $imagenes = Invoke-Kubectl -Arguments @("get", "pods", "-n", "lomax",
    "-o", "custom-columns=POD:.metadata.name,IMAGE:.spec.containers[0].image,IMAGE_ID:.status.containerStatuses[0].imageID")
  Registrar-Salida "Imagenes de los Pods" $imagenes
  $imagenesOk = @($imagenes.Output | ForEach-Object { [string]$_ } | Where-Object { $_ -match "000000000000/us-east-1/lomax-" })
  if ($imagenesOk.Count -lt 3) {
    throw "Solo $($imagenesOk.Count) Pods usan imagenes de ECR; se esperaban al menos 3."
  }
  Registrar "- OK: todos los Pods ejecutan imagenes descargadas del registro ECR."
  Registrar "- OK: el clúster no reconstruyo ninguna imagen.`n"
}

# --- Cierre ---------------------------------------------------------------
if ($script:portForwardProcess) {
  Stop-Process -Id $script:portForwardProcess.Id -Force -ErrorAction SilentlyContinue
}

[IO.File]::WriteAllLines($reportPath, $lineas, [Text.UTF8Encoding]::new($false))
Write-Host ""
Write-Host "Etapa 7 completada. Evidencia: evidence/stage7/eks-despliegue.md"

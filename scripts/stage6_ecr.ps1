# Etapa 6 - Publicacion de imagenes en ECR
#
# Crea los repositorios ECR en FLOCI, construye las imagenes de frontend y
# backend, las etiqueta con el commit de entrega y las publica. Al final
# verifica que se pueden descargar con docker pull desde un entorno sin copia
# previa y que la imagen descargada contiene la aplicacion.
#
# Uso:  .\scripts\stage6_ecr.ps1
#       .\scripts\stage6_ecr.ps1 -SinVerificar
#       .\scripts\stage6_ecr.ps1 -Tag "v1.0-entrega"
param(
  # El plano de datos de ECR lo sirve el propio puerto 4566 de Floci, que
  # hace de proxy hacia su contenedor registry:2 interno. El 5100 es
  # loopback-only y no debe publicarse.
  [string]$RegistryPort = "4567",
  [string]$Account = "000000000000",
  [string]$Region = "us-east-1",
  [string]$Endpoint = "http://localhost:4567",
  [string]$Tag = "",
  [string]$BackendRepository = "lomax-backend",
  [string]$FrontendRepository = "lomax-frontend",
  [string]$ProxyRepository = "lomax-proxy",
  [string]$Network = "",
  [switch]$SinVerificar
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $projectRoot "evidence/stage6"
$reportPath = Join-Path $evidenceDirectory "ecr-publish.md"

$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = $Region
$env:AWS_PAGER = ""

# Tag por defecto: hash corto del commit actual, para saber que codigo lleva
# cada imagen publicada.
if ([string]::IsNullOrWhiteSpace($Tag)) {
  $commit = & git -C $projectRoot rev-parse --short HEAD 2>$null
  if ($LASTEXITCODE -eq 0 -and $commit) { $Tag = $commit.Trim() }
  else { $Tag = "sin-commit" }
}

# Nombre de host de las referencias ECR. El puerto es el que publica
# docker-compose para el listener de Floci (4567 en el host -> 4566 dentro).
$registryHost = "$Account.dkr.ecr.$Region.localhost:$RegistryPort"

function Invoke-Native {
  # En Windows PowerShell 5.1 la salida por stderr de un comando nativo se
  # convierte en error fatal si $ErrorActionPreference esta en "Stop", asi que
  # se captura sin dejar que el script se detenga.
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$Arguments = @()
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  return [pscustomobject]@{ ExitCode = $exitCode; Output = @($output) }
}

function Invoke-Ecr {
  param([string[]]$Arguments)
  $resultado = Invoke-Native -FilePath "aws" -Arguments (
    @("ecr") + $Arguments + @("--endpoint-url", $Endpoint, "--region", $Region, "--output", "json")
  )
  if ($resultado.ExitCode -ne 0) {
    throw "Fallo de ECR ($($Arguments -join ' ')): $($resultado.Output -join "`n")"
  }
  $texto = ($resultado.Output -join "`n").Trim()
  if (-not $texto) { return $null }
  return ($texto | ConvertFrom-Json)
}

New-Item -ItemType Directory -Force -Path $evidenceDirectory | Out-Null
$lineas = @()

function Registrar {
  param([string]$Texto)
  Write-Host $Texto
  $script:lineas += $Texto
}

Registrar "# E6 - Publicacion de imagenes en ECR`n"
Registrar "- Fecha: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
Registrar "- Tag: $Tag"
Registrar "- Plano de datos: $registryHost`n"

# 1) Los repositorios
Registrar "## Repositorios"
$repositorios = @()
foreach ($repositorio in @($BackendRepository, $FrontendRepository, $ProxyRepository)) {
  $existente = Invoke-Native -FilePath "aws" -Arguments @(
    "ecr", "describe-repositories", "--repository-names", $repositorio,
    "--endpoint-url", $Endpoint, "--region", $Region
  )
  if ($existente.ExitCode -eq 0) {
    Registrar "- $repositorio ya existia"
  }
  else {
    $creado = Invoke-Native -FilePath "aws" -Arguments @(
      "ecr", "create-repository", "--repository-name", $repositorio,
      "--endpoint-url", $Endpoint, "--region", $Region
    )
    if ($creado.ExitCode -ne 0) {
      throw "No se pudo crear el repositorio $repositorio : $($creado.Output -join "`n")"
    }
    Registrar "- $repositorio creado"
  }
  $repositorios += $repositorio
}

# La URI que devuelve la API es la fuente de verdad del registro. Se usa en
# lugar de construirla a mano, para que el script siga funcionando si Floci
# cambia el esquema (hostname o path) o el puerto.
$uris = @{}
foreach ($repositorio in $repositorios) {
  $detalle = Invoke-Ecr -Arguments @("describe-repositories", "--repository-names", $repositorio)
  $uris[$repositorio] = $detalle.repositories[0].repositoryUri
  Registrar "- $repositorio -> $($uris[$repositorio])"
}
$registryHost = ($uris[$repositorios[0]] -split "/")[0]
Registrar ""

# 2) Construir y publicar
Registrar "## docker push"
$imagenes = @(
  @{ Nombre = $BackendRepository; Contexto = "backend" },
  @{ Nombre = $FrontendRepository; Contexto = "frontend" },
  @{ Nombre = $ProxyRepository; Contexto = "proxy" }
)

foreach ($imagen in $imagenes) {
  $tagLocal = "$($imagen.Nombre):$Tag"
  $tagRemoto = "$($uris[$imagen.Nombre]):$Tag"

  Registrar "### $($imagen.Nombre)"

  $build = Invoke-Native -FilePath "docker" -Arguments @(
    "build", "-t", $tagLocal, "-t", $tagRemoto, $imagen.Contexto
  )
  $build.Output | ForEach-Object { Registrar "  $_" }
  if ($build.ExitCode -ne 0) {
    throw "Fallo al construir $($imagen.Nombre)."
  }
  Registrar "construida: $tagLocal"

  $push = Invoke-Native -FilePath "docker" -Arguments @("push", $tagRemoto)
  $push.Output | ForEach-Object { Registrar "  $_" }
  if ($push.ExitCode -ne 0) {
    throw "Fallo al publicar $($imagen.Nombre) en $registryHost."
  }
  Registrar "publicada: $tagRemoto`n"
}

# 3) Verificacion E6
if ($SinVerificar) {
  Registrar "## Verificacion omitida (-SinVerificar)"
}
else {
  Registrar "## Verificacion E6: ecr describe-images"
  foreach ($repositorio in $repositorios) {
    $descripcion = Invoke-Ecr -Arguments @("describe-images", "--repository-name", $repositorio)
    if (-not $descripcion.imageDetails -or $descripcion.imageDetails.Count -eq 0) {
      throw "$repositorio no tiene imagenes publicadas."
    }
    foreach ($detalle in $descripcion.imageDetails) {
      $etiquetas = @($detalle.imageTags) -join ","
      Registrar ("- {0}  digest={1}  {2} bytes  pushed={3}" -f $etiquetas, $detalle.imageDigest, $detalle.imageSizeInBytes, $detalle.imagePushedAt)
    }
  }
  Registrar ""

  Registrar "## Verificacion E6: docker pull sin copia previa"
  foreach ($imagen in $imagenes) {
    $tagRemoto = "$($uris[$imagen.Nombre]):$Tag"
    $borrar = Invoke-Native -FilePath "docker" -Arguments @("rmi", "-f", $tagRemoto)
    Registrar "  $($borrar.Output -join ' ')"

    $pull = Invoke-Native -FilePath "docker" -Arguments @("pull", $tagRemoto)
    $pull.Output | ForEach-Object { Registrar "  $_" }
    if ($pull.ExitCode -ne 0) {
      throw "docker pull fallo para $tagRemoto."
    }
  }
  Registrar ""

  Registrar "## Verificacion E6: la imagen descargada contiene la aplicacion"
  # Se levanta el backend descargado del registro contra los servicios que ya
  # estan en marcha y se consulta /health. Si responde OK, la imagen trae la
  # aplicacion entregada y no solo un contenedor vacio.
  $contenedor = "lomax-ecr-check"
  Invoke-Native -FilePath "docker" -Arguments @("rm", "-f", $contenedor) | Out-Null

  # Docker Compose antepone el nombre del proyecto a la red, asi que se
  # descubre en vez de fijarlo: si el proyecto se renombra, el script sigue
  # funcionando.
  $redCompose = $Network
  if (-not $redCompose) {
    $redes = Invoke-Native -FilePath "docker" -Arguments @("network", "ls", "--format", "{{.Name}}")
    $redCompose = @($redes.Output | ForEach-Object { ([string]$_).Trim() } |
      Where-Object { $_ -like "lomax*_default" -or $_ -eq "lomax-etapa2" } |
      Select-Object -First 1)
    if (-not $redCompose) {
      throw "No se encontro la red de Compose de Lomax. Levantalo con docker compose up -d."
    }
  }
  Registrar "Red de Compose detectada: $redCompose"

  $rdsHost = ""
  $envFile = Join-Path $projectRoot ".env"
  if (Test-Path $envFile) {
    $linea = Get-Content $envFile | Where-Object { $_ -match "^LOMAX_RDS_HOST=" } | Select-Object -First 1
    if ($linea) { $rdsHost = ($linea -split "=", 2)[1] }
  }
  $dbPassword = $env:LOMAX_DB_PASSWORD
  if ([string]::IsNullOrWhiteSpace($dbPassword)) { $dbPassword = "LomaxLocal2026!" }

  $arranque = Invoke-Native -FilePath "docker" -Arguments @(
    "run", "--rm", "-d", "--name", $contenedor,
    "--network", $redCompose,
    "-p", "5001:5000",
    "-e", "RDS_HOST=$rdsHost",
    "-e", "RDS_PASSWORD=$dbPassword",
    "-e", "AWS_ENDPOINT_URL=http://floci:4566",
    "$($uris[$BackendRepository]):$Tag"
  )
  if ($arranque.ExitCode -ne 0) {
    throw "No se pudo arrancar la imagen descargada: $($arranque.Output -join "`n")"
  }

  $salud = $null
  for ($intento = 0; $intento -lt 30; $intento++) {
    Start-Sleep -Seconds 2
    $probe = Invoke-Native -FilePath "docker" -Arguments @(
      "exec", $contenedor, "python", "-c",
      "import urllib.request;print(urllib.request.urlopen('http://127.0.0.1:5000/health',timeout=5).read().decode())"
    )
    if ($probe.ExitCode -eq 0 -and ($probe.Output -join "").Trim()) {
      $salud = ($probe.Output -join " ").Trim()
      break
    }
  }
  Invoke-Native -FilePath "docker" -Arguments @("rm", "-f", $contenedor) | Out-Null

  if (-not $salud) {
    throw "La imagen descargada no respondio en /health."
  }
  Registrar "  /health -> $salud"
  Registrar "  OK: la imagen publicada en ECR contiene la aplicacion entregada."
}

[System.IO.File]::WriteAllLines($reportPath, $lineas, [System.Text.UTF8Encoding]::new($false))
Write-Host ""
Write-Host "Etapa 6 completada. Imagenes publicadas con el tag '$Tag'."
Write-Host "Evidencia: evidence/stage6/ecr-publish.md"
Write-Host "Siguiente paso: .\scripts\stage7_eks.ps1"

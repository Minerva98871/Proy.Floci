# Etapa 5 del catalogo: una fotografia por producto.
#
# El enunciado pide 20 productos publicados en 3 o mas categorias, con dos
# conjuntos distintos de atributos y una fotografia cada uno. Este script
# completa la parte que falta: genera una imagen por producto, la sube a
# traves de la API (de modo que pase por S3, Lambda y DynamoDB igual que una
# foto real) y verifica que el producto queda PUBLICADO.
#
# Uso:  .\scripts\stage5_catalogo.ps1
# Deuda:  .\scripts\stage5_catalogo.ps1 -SoloGenerar
param(
  [string]$BaseUrl = "http://localhost:8080/api",
  [string]$DbPassword = $env:LOMAX_DB_PASSWORD,
  [switch]$SoloGenerar
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$evidenceDirectory = Join-Path $projectRoot "evidence/stage5"
$imageDirectory = Join-Path $evidenceDirectory "originales"
$catalogoJson = Join-Path $evidenceDirectory "catalogo.json"

if ([string]::IsNullOrWhiteSpace($DbPassword)) {
  $DbPassword = "LomaxLocal2026!"
  Write-Warning "Usando clave de demostracion local. Define LOMAX_DB_PASSWORD para cambiarla."
}

function Invoke-Native {
  # Igual que en setup.ps1: en Windows PowerShell 5.1 la salida por stderr de
  # un comando nativo se convierte en error fatal si $ErrorActionPreference
  # esta en "Stop".
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$Arguments = @()
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $previousOutputEncoding = $OutputEncoding
  $OutputEncoding = [System.Text.UTF8Encoding]::new($false)
  $ErrorActionPreference = "Continue"
  try {
    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $OutputEncoding = $previousOutputEncoding
    $ErrorActionPreference = $previousErrorActionPreference
  }

  return [pscustomobject]@{
    ExitCode = $exitCode
    Output   = @($output)
  }
}

# El cliente MySQL corre en un contenedor, igual que en la Etapa 2.
function Get-CatalogoProductos {
  $port = 7001
  $envFile = Join-Path $projectRoot ".env"
  if (Test-Path $envFile) {
    $linea = Get-Content $envFile | Where-Object { $_ -match "^LOMAX_RDS_PORT=" } | Select-Object -First 1
    if ($linea) { $port = ($linea -split "=")[1] }
  }

  $argumentos = @(
    "run", "--rm",
    "--mount", "type=bind,source=$(Join-Path $projectRoot 'scripts'),target=/scripts,readonly",
    "--env", "MYSQL_PWD=$DbPassword",
    "--interactive", "mysql:8.0",
    "mysql",
    "--host=host.docker.internal",
    "--port=$port",
    "--user=lomax",
    "--database=lomax_catalogo",
    "--batch", "--skip-column-names",
    "--default-character-set=utf8mb4",
    "--execute=SELECT p.producto_id, p.codigo, p.nombre, c.nombre FROM Productos p JOIN Categorias c ON c.categoria_id = p.categoria_id WHERE p.estado = 'PUBLICADO' ORDER BY p.producto_id;"
  )

  $resultado = Invoke-Native -FilePath "docker" -Arguments $argumentos
  if ($resultado.ExitCode -ne 0) {
    throw "No se pudo leer el catalogo de RDS: $($resultado.Output -join "`n")"
  }

  $productos = @()
  foreach ($linea in $resultado.Output) {
    $texto = ([string]$linea).Trim()
    if (-not $texto) { continue }
    $columnas = $texto -split "`t"
    if ($columnas.Count -lt 4) { continue }
    $productos += [pscustomobject]@{
      producto_id = [int]$columnas[0]
      codigo      = $columnas[1]
      nombre      = $columnas[2]
      categoria   = $columnas[3]
    }
  }
  return $productos
}

# Python para hablar JSON con la API y montar el archivo de catalogo.
$python = "python"
if (-not (Get-Command $python -ErrorAction SilentlyContinue)) { $python = "py" }

function Invoke-Api {
  param(
    [Parameter(Mandatory = $true)][string]$Method,
    [Parameter(Mandatory = $true)][string]$Path,
    $JsonBody,
    $FilePath
  )

  $url = "$BaseUrl$Path"
  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    # -w %{http_code} deja el codigo HTTP en la ultima linea para poder
    # distinguir un 200 con cuerpo de error de un 4xx real. Con -s -X GET y
    # sin cuerpo no se pasa -d, porque curl descartaria la URL.
    if ($FilePath) {
      $argumentos = @("-s", "-w", "`n%{http_code}", "-X", $Method, "-F", "file=@$FilePath", $url)
    }
    elseif ($PSBoundParameters.ContainsKey("JsonBody") -and $JsonBody) {
      $argumentos = @("-s", "-w", "`n%{http_code}", "-X", $Method,
                      "-H", "Content-Type: application/json", "-d", $JsonBody, $url)
    }
    else {
      $argumentos = @("-s", "-w", "`n%{http_code}", "-X", $Method, $url)
    }

    $respuesta = & curl.exe @argumentos 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }

  $lineas = @($respuesta | ForEach-Object { [string]$_ })
  $codigo = 0
  if ($lineas.Count -gt 0) {
    $ultima = $lineas[-1].Trim()
    if ($ultima -match "^\d{3}$") {
      $codigo = [int]$ultima
      $lineas = $lineas[0..($lineas.Count - 2)]
    }
  }

  $texto = ($lineas -join "`n").Trim()
  if ($exitCode -ne 0) {
    return [pscustomobject]@{ Codigo = 0; Datos = @{ error = "curl fallo: $texto" } }
  }
  if (-not $texto) {
    return [pscustomobject]@{ Codigo = $codigo; Datos = @{} }
  }

  $datos = $null
  try { $datos = $texto | ConvertFrom-Json } catch { $datos = @{ _cuerpo = $texto } }
  return [pscustomobject]@{ Codigo = $codigo; Datos = $datos }
}

New-Item -ItemType Directory -Force -Path $imageDirectory | Out-Null

# 1) Leer el catalogo de RDS
Write-Host "Leyendo productos publicados de RDS..."
$productos = Get-CatalogoProductos
if ($productos.Count -lt 20) {
  Write-Warning "Solo hay $($productos.Count) productos publicados en RDS; el enunciado pide al menos 20."
}
$categoriasUsadas = @($productos | ForEach-Object { $_.categoria } | Sort-Object -Unique)
Write-Host "OK: $($productos.Count) productos publicados en $($categoriasUsadas.Count) categorias: $($categoriasUsadas -join ', ')"

# 2) Generar una imagen por producto dentro de la imagen de herramientas
$catalogoParaPython = @()
foreach ($producto in $productos) {
  $catalogoParaPython += @{
    codigo    = $producto.codigo
    nombre    = $producto.nombre
    categoria = $producto.categoria
  }
}
[System.IO.File]::WriteAllText(
  $catalogoJson,
  ($catalogoParaPython | ConvertTo-Json -Depth 4),
  [System.Text.UTF8Encoding]::new($false)
)

$imagenHerramientas = Invoke-Native -FilePath "docker" -Arguments @(
  "build", "--file", "scripts/Dockerfile.image-tools", "--tag", "lomax-image-tools", "."
)
if ($imagenHerramientas.ExitCode -ne 0) {
  throw "No se pudo construir lomax-image-tools: $($imagenHerramientas.Output -join "`n")"
}

$generar = Invoke-Native -FilePath "docker" -Arguments @(
  "run", "--rm",
  "--mount", "type=bind,source=$evidenceDirectory,target=/catalogo",
  "lomax-image-tools",
  "python", "/tools/generate_product_images.py", "/catalogo/catalogo.json", "/catalogo/originales"
)
$generar.Output | ForEach-Object { Write-Host "  $_" }
if ($generar.ExitCode -ne 0) {
  throw "No se pudieron generar las imagenes del catalogo."
}
$generadas = @(Get-ChildItem $imageDirectory -Filter *.jpg)
Write-Host "OK: $($generadas.Count) imagenes generadas en evidence/stage5/originales."

if ($SoloGenerar) {
  Write-Host "SoloGenerar: no se suben las imagenes. Fin."
  return
}

# 3) Subir cada imagen por la API para que recorra S3 -> Lambda -> DynamoDB
$publicados = 0
$errores = @()

Write-Host "Subiendo imagenes por la API (S3 -> Lambda -> DynamoDB)..."
foreach ($producto in $productos) {
  $imagen = Join-Path $imageDirectory "$($producto.codigo).jpg"
  if (-not (Test-Path $imagen)) {
    $errores += "$($producto.codigo): no se genero la imagen"
    continue
  }

  $resultado = Invoke-Api -Method "POST" -Path "/productos/$($producto.producto_id)/imagen" -FilePath $imagen

  if ($resultado.Codigo -ne 200) {
    $detalle = $resultado.Datos.error
    if ($resultado.Datos.paso_fallido) { $detalle = "$detalle (paso: $($resultado.Datos.paso_fallido))" }
    $errores += "$($producto.codigo): HTTP $($resultado.Codigo) $detalle"
    Write-Host "  XX  $($producto.codigo)  HTTP $($resultado.Codigo)  $detalle"
    continue
  }

  if ($resultado.Datos.estado_procesamiento -eq "LISTA" -and $resultado.Datos.estado -eq "PUBLICADO") {
    $publicados++
    Write-Host "  OK  $($producto.codigo)  producto_id=$($producto.producto_id)  PUBLICADO"
  }
  else {
    $detalle = $resultado.Datos.error
    if ($resultado.Datos.paso_fallido) { $detalle = "$detalle (paso: $($resultado.Datos.paso_fallido))" }
    $errores += "$($producto.codigo): la Lambda no completo (estado_procesamiento=$($resultado.Datos.estado_procesamiento)) $detalle"
    Write-Host "  XX  $($producto.codigo)  $($resultado.Datos.estado_procesamiento)  $detalle"
  }
}

# 4) Verificar por la API que el catalogo quedo completo
$listado = Invoke-Api -Method "GET" -Path "/productos"
$enCatalogo = @($listado.Datos.data).Count
$conMiniatura = @($listado.Datos.data | Where-Object { $_.miniatura_disponible }).Count

Write-Host ""
Write-Host "Resumen:"
Write-Host "  productos subidos en esta ejecucion : $publicados"
Write-Host "  en el catalogo (GET /productos)     : $enCatalogo"
Write-Host "  con miniatura disponible            : $conMiniatura"
Write-Host "  categorias                          : $($categoriasUsadas.Count)"

if ($errores.Count -gt 0) {
  Write-Host ""
  Write-Host "Errores ($($errores.Count)):" -ForegroundColor Red
  $errores | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
}

if ($enCatalogo -lt 20) {
  throw "El catalogo expone $enCatalogo productos; el enunciado pide al menos 20 publicados con fotografia."
}
if ($conMiniatura -ne $enCatalogo) {
  throw "Solo $conCatalogo de $enCatalogo productos tienen miniatura; todos deberian tener fotografia."
}
if ($errores.Count -gt 0) {
  throw "Hubo $($errores.Count) errores al subir imagenes."
}

Write-Host ""
Write-Host "Etapa 5 completada: $enCatalogo productos publicados, cada uno con su fotografia y miniatura."

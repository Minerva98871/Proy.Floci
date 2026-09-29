param(
  [string]$DbPassword = $env:LOMAX_DB_PASSWORD,
  [string]$Region = "us-east-1",
  [string]$OriginalsBucket = "lomax-originales",
  [string]$ThumbnailsBucket = "lomax-miniaturas",
  [string]$TableName = "LomaxAtributos",
  [string]$FunctionName = "lomax-thumbnail"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$endpoint = "http://localhost:4567"
$dbUser = "lomax"
$maxImageBytes = 5 * 1024 * 1024

if ([string]::IsNullOrWhiteSpace($DbPassword)) {
  $DbPassword = "LomaxLocal2026!"
}
$env:AWS_ACCESS_KEY_ID = "test"
$env:AWS_SECRET_ACCESS_KEY = "test"
$env:AWS_DEFAULT_REGION = $Region
$env:AWS_PAGER = ""

function Invoke-Native {
  # Ejecuta un comando nativo devolviendo salida y codigo de retorno sin
  # lanzar excepcion. En Windows PowerShell 5.1, con $ErrorActionPreference
  # en "Stop", la salida por stderr de docker se convierte en un error fatal
  # y aborta el script. $PSNativeCommandUseErrorActionPreference solo existe
  # en PowerShell 7.3 o superior, asi que esta funcion cubre ambas versiones.
  param(
    [Parameter(Mandatory = $true)][string]$FilePath,
    [string[]]$Arguments = @(),
    [string]$WorkingDirectory
  )

  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  $previousLocation = Get-Location
  try {
    if ($WorkingDirectory) { Set-Location -LiteralPath $WorkingDirectory }
    $output = & $FilePath @Arguments 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    if ($WorkingDirectory) { Set-Location -LiteralPath $previousLocation }
    $ErrorActionPreference = $previousPreference
  }

  return [pscustomobject]@{
    ExitCode = $exitCode
    Output   = @($output)
  }
}

function Invoke-AwsJson {
  param([string[]]$Arguments)

  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & aws @Arguments --endpoint-url $endpoint --region $Region --output json 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($exitCode -ne 0) {
    throw "Fallo AWS CLI ($($Arguments -join ' ')): $($output -join "`n")"
  }
  if (-not $output) { return $null }
  return (($output -join "`n") | ConvertFrom-Json)
}

function Invoke-AwsCommand {
  param([string[]]$Arguments)

  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = & aws @Arguments --endpoint-url $endpoint --region $Region 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($exitCode -ne 0) {
    throw "Fallo AWS CLI ($($Arguments -join ' ')): $($output -join "`n")"
  }
  return $output
}

function Write-Utf8Json {
  param([string]$Path, [object]$Value)
  $json = $Value | ConvertTo-Json -Depth 20
  [System.IO.File]::WriteAllText($Path, $json, [System.Text.UTF8Encoding]::new($false))
}

function Invoke-MySql {
  param([string]$Sql, [int]$Port)

  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = $Sql | & docker run --rm --interactive --env "MYSQL_PWD=$DbPassword" mysql:8.0 mysql --host=host.docker.internal --port=$Port --user=$dbUser --database=lomax_catalogo --batch --skip-column-names 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($exitCode -ne 0) {
    throw "Fallo MySQL: $($output -join "`n")"
  }
  return $output
}

function Put-DynamoItem {
  param([string]$ProductId, [string]$Code)

  $itemPath = Join-Path ([System.IO.Path]::GetTempPath()) "lomax-stage3-item-$PID.json"
  $item = @{
    producto_id = @{ N = $ProductId }
    codigo = @{ S = $Code }
    atributos = @{ M = @{} }
    imagen_estado = @{ S = "PENDIENTE" }
  }
  Write-Utf8Json -Path $itemPath -Value $item
  try {
    Invoke-AwsJson -Arguments @("dynamodb", "put-item", "--table-name", $TableName, "--item", "file://$itemPath") | Out-Null
  }
  finally {
    Remove-Item $itemPath -ErrorAction SilentlyContinue
  }
}

function Get-DynamoItem {
  param([string]$ProductId)

  $keyPath = Join-Path ([System.IO.Path]::GetTempPath()) "lomax-stage3-key-$PID.json"
  Write-Utf8Json -Path $keyPath -Value @{ producto_id = @{ N = $ProductId } }
  try {
    return (Invoke-AwsJson -Arguments @("dynamodb", "get-item", "--table-name", $TableName, "--key", "file://$keyPath", "--consistent-read")).Item
  }
  finally {
    Remove-Item $keyPath -ErrorAction SilentlyContinue
  }
}

function Get-S3ObjectCount {
  param([object]$Listing)
  if ($null -eq $Listing.Contents) { return 0 }
  return @($Listing.Contents).Count
}

function Invoke-Thumbnail {
  param(
    [string]$ProductId,
    [string]$SourceKey,
    [string]$Name,
    [string]$ExpectedStatus
  )

  $eventPath = Join-Path $stageDirectory "$Name-event.json"
  $responsePath = Join-Path $stageDirectory "$Name-response.json"
  $metadataPath = Join-Path $stageDirectory "$Name-invoke-metadata.json"
  Write-Utf8Json -Path $eventPath -Value @{
    producto_id = $ProductId
    bucket = $OriginalsBucket
    clave_original = $SourceKey
  }

  $previousPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $metadataOutput = & aws lambda invoke --function-name $FunctionName --invocation-type RequestResponse --cli-binary-format raw-in-base64-out --payload "fileb://$eventPath" $responsePath --cli-connect-timeout 30 --cli-read-timeout 300 --endpoint-url $endpoint --region $Region --output json 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousPreference
  }
  if ($exitCode -ne 0) {
    throw "lambda invoke ($Name) fallo: $($metadataOutput -join "`n")"
  }
  [System.IO.File]::WriteAllText($metadataPath, ($metadataOutput -join "`n"), [System.Text.UTF8Encoding]::new($false))
  $metadata = ($metadataOutput -join "`n") | ConvertFrom-Json
  if ($metadata.FunctionError) {
    throw "Lambda reporto FunctionError=$($metadata.FunctionError) en $Name. Revisa $responsePath"
  }
  $result = Get-Content $responsePath -Raw | ConvertFrom-Json
  if ($result.estado -ne $ExpectedStatus) {
    throw "Lambda devolvio estado '$($result.estado)' para $Name; se esperaba '$ExpectedStatus'. Revisa $responsePath"
  }
  return $result
}

function Upload-Image {
  param([string]$Path, [string]$Key, [switch]$AllowOversizeTestFixture)

  $length = (Get-Item $Path).Length
  if ($length -gt $maxImageBytes -and -not $AllowOversizeTestFixture) {
    throw "El archivo $Path supera el limite de 5 MiB."
  }
  $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
  if ($extension -notin @(".jpg", ".jpeg", ".png")) {
    throw "Solo se admiten extensiones .jpg, .jpeg o .png."
  }
  Invoke-AwsCommand -Arguments @("s3", "cp", $Path, "s3://$OriginalsBucket/$Key") | Out-Null
}

Push-Location $projectRoot
try {
  foreach ($command in @("docker", "aws")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
      throw "No se encontro '$command'. Instala Docker Desktop y AWS CLI v2."
    }
  }

  $stageDirectory = Join-Path $projectRoot "evidence/stage3"
  $originalDirectory = Join-Path $stageDirectory "originales"
  $thumbnailDirectory = Join-Path $stageDirectory "miniaturas"
  New-Item -ItemType Directory -Force -Path $originalDirectory, $thumbnailDirectory | Out-Null

  $floci = Invoke-Native -FilePath "docker" -Arguments @("compose", "up", "-d", "floci")
  if ($floci.ExitCode -ne 0) {
    throw "No se pudo iniciar Floci con Docker Compose: $($floci.Output -join "`n")"
  }

  $emulatorReady = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
      $tableNames = @( (Invoke-AwsJson -Arguments @("dynamodb", "list-tables")).TableNames )
      if ($tableNames -contains $TableName) {
        $emulatorReady = $true
        break
      }
    }
    catch {
      Start-Sleep -Seconds 2
    }
    Start-Sleep -Seconds 2
  }
  if (-not $emulatorReady) {
    throw "No existe la tabla DynamoDB '$TableName'. Ejecuta primero .\\scripts\\setup.ps1."
  }
  $instanceDescriptions = @( (Invoke-AwsJson -Arguments @("rds", "describe-db-instances")).DBInstances )
  if (-not ($instanceDescriptions | Where-Object { $_.DBInstanceIdentifier -eq "lomax-mysql" -and $_.DBInstanceStatus -eq "available" })) {
    throw "No existe una instancia RDS lomax-mysql disponible. Ejecuta primero .\\scripts\\setup.ps1."
  }

  foreach ($bucket in @($OriginalsBucket, $ThumbnailsBucket)) {
    $probe = Invoke-Native -FilePath "aws" -Arguments @(
      "s3api", "head-bucket", "--bucket", $bucket,
      "--endpoint-url", $endpoint, "--region", $Region
    )
    $bucketExists = $probe.ExitCode -eq 0
    if (-not $bucketExists) {
      Invoke-AwsCommand -Arguments @("s3", "mb", "s3://$bucket") | Out-Null
    }
  }

  $imageCodes = @("P4-LAMBDA-JPG", "P4-LAMBDA-PNG", "P4-LAMBDA-INVALID", "P4-LAMBDA-OVERSIZE")
  $sql = @"
INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES
  ('P4-LAMBDA-JPG', 'Prueba Lambda JPEG', 'Imagen JPEG 1200x800 para P4.', 10.00, 1, 'PENDIENTE'),
  ('P4-LAMBDA-PNG', 'Prueba Lambda PNG', 'Imagen PNG de control para P4.', 11.00, 1, 'PENDIENTE'),
  ('P4-LAMBDA-INVALID', 'Prueba Lambda invalida', 'Archivo que no es una imagen.', 12.00, 1, 'PENDIENTE'),
  ('P4-LAMBDA-OVERSIZE', 'Prueba Lambda grande', 'Archivo mayor a 5 MiB.', 13.00, 1, 'PENDIENTE')
ON DUPLICATE KEY UPDATE
  nombre = VALUES(nombre), descripcion = VALUES(descripcion), precio = VALUES(precio),
  categoria_id = VALUES(categoria_id), estado = 'PENDIENTE';
SELECT producto_id, codigo FROM Productos WHERE codigo IN ('P4-LAMBDA-JPG', 'P4-LAMBDA-PNG', 'P4-LAMBDA-INVALID', 'P4-LAMBDA-OVERSIZE') ORDER BY codigo;
"@
  $rdsEndpoint = (Invoke-AwsJson -Arguments @("rds", "describe-db-instances", "--db-instance-identifier", "lomax-mysql")).DBInstances[0].Endpoint
  $productRows = @(Invoke-MySql -Sql $sql -Port ([int]$rdsEndpoint.Port))
  $productIds = @{}
  foreach ($row in $productRows) {
    $columns = ([string]$row) -split "`t"
    if ($columns.Count -ge 2 -and $imageCodes -contains $columns[1]) {
      $productIds[$columns[1]] = $columns[0]
    }
  }
  foreach ($code in $imageCodes) {
    if (-not $productIds.ContainsKey($code)) { throw "No se encontro en RDS el producto $code." }
    Put-DynamoItem -ProductId $productIds[$code] -Code $code
  }

  $originalJpeg = Join-Path $originalDirectory "lomax-1200x800.jpg"
  $originalPng = Join-Path $originalDirectory "lomax-1200x800.png"
  function Invoke-ImageTools {
    param([string[]]$Arguments, [string]$FailureMessage)

    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
      $output = & docker @Arguments 2>&1
      $exitCode = $LASTEXITCODE
    }
    finally {
      $ErrorActionPreference = $previousPreference
    }
    if ($output) { $output | ForEach-Object { Write-Host $_ } }
    if ($exitCode -ne 0) { throw "$FailureMessage`n$($output -join "`n")" }
  }

  $mount = "type=bind,source=$stageDirectory,target=/evidence"
  Invoke-ImageTools -Arguments @("build", "--file", "scripts/Dockerfile.image-tools", "--tag", "lomax-image-tools", ".") `
    -FailureMessage "No se pudo construir la imagen Docker de herramientas de imagen."
  Invoke-ImageTools -Arguments @("run", "--rm", "--mount", $mount, "lomax-image-tools", "python", "/tools/create_test_image.py", "/evidence/originales/lomax-1200x800.jpg") `
    -FailureMessage "No se pudo crear el JPEG de prueba."
  Invoke-ImageTools -Arguments @("run", "--rm", "--mount", $mount, "lomax-image-tools", "python", "/tools/create_test_image.py", "/evidence/originales/lomax-1200x800.png") `
    -FailureMessage "No se pudo crear el PNG de prueba."

  $invalidPath = Join-Path $originalDirectory "archivo-invalido.jpg"
  [System.IO.File]::WriteAllText($invalidPath, "Esto no es una imagen JPEG ni PNG.", [System.Text.UTF8Encoding]::new($false))
  $oversizePath = Join-Path $originalDirectory "imagen-mayor-a-5MiB.jpg"
  [System.IO.File]::WriteAllBytes($oversizePath, [byte[]]::new($maxImageBytes + 1))

  $testImages = @(
    @{ Code = "P4-LAMBDA-JPG"; Path = $originalJpeg; Key = "originales/$($productIds['P4-LAMBDA-JPG'])/lomax-1200x800.jpg" },
    @{ Code = "P4-LAMBDA-PNG"; Path = $originalPng; Key = "originales/$($productIds['P4-LAMBDA-PNG'])/lomax-1200x800.png" },
    @{ Code = "P4-LAMBDA-INVALID"; Path = $invalidPath; Key = "originales/$($productIds['P4-LAMBDA-INVALID'])/archivo-invalido.jpg" },
    @{ Code = "P4-LAMBDA-OVERSIZE"; Path = $oversizePath; Key = "originales/$($productIds['P4-LAMBDA-OVERSIZE'])/imagen-mayor-a-5MiB.jpg" }
  )
  foreach ($image in $testImages) {
    if ($image.Code -eq "P4-LAMBDA-OVERSIZE") {
      Upload-Image -Path $image.Path -Key $image.Key -AllowOversizeTestFixture
    }
    else {
      Upload-Image -Path $image.Path -Key $image.Key
    }
  }

  $runtimeEnvironmentPath = Join-Path $stageDirectory "lambda-environment.json"
  Write-Utf8Json -Path $runtimeEnvironmentPath -Value @{
    Variables = @{
      AWS_ENDPOINT_URL = "http://floci:4566"
      ORIGINALS_BUCKET = $OriginalsBucket
      THUMBNAILS_BUCKET = $ThumbnailsBucket
      DYNAMODB_TABLE = $TableName
    }
  }
  $packagePath = Join-Path $stageDirectory "lomax-thumbnail.zip"
  Invoke-ImageTools -Arguments @("run", "--rm", "--mount", $mount, "lomax-image-tools", "python", "/tools/package_lambda.py", "/evidence") `
    -FailureMessage "No se pudo empaquetar la funcion Lambda."
  if (-not (Test-Path $packagePath)) { throw "No se genero el paquete $packagePath." }

  $functionNames = @((Invoke-AwsJson -Arguments @("lambda", "list-functions")).Functions | ForEach-Object { $_.FunctionName })
  if ($functionNames -contains $FunctionName) {
    Invoke-AwsJson -Arguments @("lambda", "update-function-code", "--function-name", $FunctionName, "--zip-file", "fileb://$packagePath") | Out-Null
    Invoke-AwsJson -Arguments @("lambda", "update-function-configuration", "--function-name", $FunctionName, "--runtime", "python3.12", "--handler", "handler.handler", "--timeout", "60", "--memory-size", "512", "--environment", "file://$runtimeEnvironmentPath") | Out-Null
  }
  else {
    Invoke-AwsJson -Arguments @(
      "lambda", "create-function",
      "--function-name", $FunctionName,
      "--runtime", "python3.12",
      "--role", "arn:aws:iam::000000000000:role/lomax-thumbnail-role",
      "--handler", "handler.handler",
      "--timeout", "60",
      "--memory-size", "512",
      "--zip-file", "fileb://$packagePath",
      "--environment", "file://$runtimeEnvironmentPath"
    ) | Out-Null
  }

  $active = $false
  for ($attempt = 0; $attempt -lt 90; $attempt++) {
    $configuration = Invoke-AwsJson -Arguments @("lambda", "get-function-configuration", "--function-name", $FunctionName)
    if ($configuration.State -eq "Active" -and $configuration.LastUpdateStatus -ne "InProgress") {
      $active = $true
      break
    }
    Start-Sleep -Seconds 2
  }
  if (-not $active) { throw "La funcion $FunctionName no llego a estado Active." }

  $jpegId = $productIds["P4-LAMBDA-JPG"]
  $jpegKey = $testImages[0].Key
  $jpegFirst = Invoke-Thumbnail -ProductId $jpegId -SourceKey $jpegKey -Name "lambda-jpeg-primera" -ExpectedStatus "LISTA"
  $jpegRetry = Invoke-Thumbnail -ProductId $jpegId -SourceKey $jpegKey -Name "lambda-jpeg-reintento" -ExpectedStatus "LISTA"
  if ($jpegFirst.miniatura_key -ne $jpegRetry.miniatura_key) {
    throw "El reintento JPEG cambio la clave determinista de salida."
  }

  $pngResult = Invoke-Thumbnail -ProductId $productIds["P4-LAMBDA-PNG"] -SourceKey $testImages[1].Key -Name "lambda-png" -ExpectedStatus "LISTA"
  $invalidResult = Invoke-Thumbnail -ProductId $productIds["P4-LAMBDA-INVALID"] -SourceKey $testImages[2].Key -Name "lambda-invalida" -ExpectedStatus "ERROR"
  $oversizeResult = Invoke-Thumbnail -ProductId $productIds["P4-LAMBDA-OVERSIZE"] -SourceKey $testImages[3].Key -Name "lambda-mayor-a-5MiB" -ExpectedStatus "ERROR"

  foreach ($product in @(
    @{ Code = "P4-LAMBDA-JPG"; Expected = "LISTA" },
    @{ Code = "P4-LAMBDA-PNG"; Expected = "LISTA" },
    @{ Code = "P4-LAMBDA-INVALID"; Expected = "ERROR" },
    @{ Code = "P4-LAMBDA-OVERSIZE"; Expected = "ERROR" }
  )) {
    $item = Get-DynamoItem -ProductId $productIds[$product.Code]
    if (-not $item -or $item.imagen_estado.S -ne $product.Expected) {
      throw "DynamoDB imagen_estado incorrecto para $($product.Code)."
    }
    $rdsState = [string](Invoke-MySql -Sql "SELECT estado FROM Productos WHERE producto_id = $($productIds[$product.Code]);" -Port ([int]$rdsEndpoint.Port))
    if ($rdsState -ne "PENDIENTE") {
      throw "El producto $($product.Code) quedo $rdsState en RDS; no debe publicarse en esta etapa."
    }
    if ($product.Expected -eq "LISTA" -and -not $item.miniatura_key.S) {
      throw "DynamoDB no contiene la miniatura de $($product.Code)."
    }
    if ($product.Expected -eq "ERROR" -and $item.miniatura_key) {
      throw "DynamoDB conserva una miniatura para el caso fallido $($product.Code)."
    }
    $ddbEvidencePath = Join-Path $stageDirectory "dynamodb-$($product.Code).json"
    Write-Utf8Json -Path $ddbEvidencePath -Value @{ Item = $item }
  }

  $validItem = Get-DynamoItem -ProductId $jpegId
  if ($validItem.miniatura_key.S -ne $jpegFirst.miniatura_key) {
    throw "La clave de DynamoDB no coincide con la miniatura informada por Lambda."
  }
  $invalidItem = Get-DynamoItem -ProductId $productIds["P4-LAMBDA-INVALID"]
  if ($invalidItem.imagen_estado.S -ne "ERROR" -or $invalidItem.miniatura_key) {
    throw "El estado de la imagen invalida en DynamoDB no cumple la expectativa."
  }

  $originalListing = Invoke-AwsCommand -Arguments @("s3", "ls", "s3://$OriginalsBucket/originales/", "--recursive")
  [System.IO.File]::WriteAllLines((Join-Path $stageDirectory "s3-listado-originales.txt"), [string[]]$originalListing, [System.Text.UTF8Encoding]::new($false))
  $thumbnailListing = Invoke-AwsCommand -Arguments @("s3", "ls", "s3://$ThumbnailsBucket/miniaturas/", "--recursive")
  [System.IO.File]::WriteAllLines((Join-Path $stageDirectory "s3-listado-miniaturas.txt"), [string[]]$thumbnailListing, [System.Text.UTF8Encoding]::new($false))
  Write-Utf8Json -Path (Join-Path $stageDirectory "s3-list-objects-originales.json") -Value (Invoke-AwsJson -Arguments @("s3api", "list-objects-v2", "--bucket", $OriginalsBucket, "--prefix", "originales/"))
  Write-Utf8Json -Path (Join-Path $stageDirectory "s3-list-objects-miniaturas.json") -Value (Invoke-AwsJson -Arguments @("s3api", "list-objects-v2", "--bucket", $ThumbnailsBucket, "--prefix", "miniaturas/"))

  $jpegPrefix = "miniaturas/$jpegId/"
  $jpegObjects = Invoke-AwsJson -Arguments @("s3api", "list-objects-v2", "--bucket", $ThumbnailsBucket, "--prefix", $jpegPrefix)
  if ((Get-S3ObjectCount $jpegObjects) -ne 1 -or $jpegObjects.Contents[0].Key -ne $validItem.miniatura_key.S) {
    throw "Tras el reintento debe existir un unico objeto miniatura con la clave guardada en DynamoDB."
  }
  foreach ($code in @("P4-LAMBDA-INVALID", "P4-LAMBDA-OVERSIZE")) {
    $failedObjects = Invoke-AwsJson -Arguments @("s3api", "list-objects-v2", "--bucket", $ThumbnailsBucket, "--prefix", "miniaturas/$($productIds[$code])/" )
    if ((Get-S3ObjectCount $failedObjects) -ne 0) { throw "Se creo una miniatura para $code pese al error." }
  }

  $jpegDownloaded = Join-Path $thumbnailDirectory "miniatura-lomax.jpg"
  $getMetadata = Invoke-AwsJson -Arguments @("s3api", "get-object", "--bucket", $ThumbnailsBucket, "--key", $validItem.miniatura_key.S, $jpegDownloaded)
  Write-Utf8Json -Path (Join-Path $stageDirectory "s3-get-object-miniatura.json") -Value $getMetadata
  $originalDownloaded = Join-Path $stageDirectory "original-descargado.jpg"
  $originalMetadata = Invoke-AwsJson -Arguments @("s3api", "get-object", "--bucket", $OriginalsBucket, "--key", $jpegKey, $originalDownloaded)
  Write-Utf8Json -Path (Join-Path $stageDirectory "s3-get-object-original.json") -Value $originalMetadata
  Write-Utf8Json -Path (Join-Path $stageDirectory "dynamodb-get-item-miniatura.json") -Value @{ Item = $validItem }
  Write-Utf8Json -Path (Join-Path $stageDirectory "dynamodb-get-item-invalida.json") -Value @{ Item = $invalidItem }

  $dimensionOutput = & docker run --rm --mount "type=bind,source=$stageDirectory,target=/evidence" lomax-image-tools python /tools/inspect_images.py /evidence/original-descargado.jpg /evidence/miniaturas/miniatura-lomax.jpg 2>&1
  if ($LASTEXITCODE -ne 0) { throw "No se pudieron inspeccionar las dimensiones descargadas." }
  [System.IO.File]::WriteAllLines((Join-Path $stageDirectory "dimensiones.json"), [string[]]$dimensionOutput, [System.Text.UTF8Encoding]::new($false))
  $dimensions = ($dimensionOutput -join "`n") | ConvertFrom-Json
  if ($dimensions.'original-descargado.jpg'.ancho -ne 1200 -or $dimensions.'original-descargado.jpg'.alto -ne 800) {
    throw "La imagen descargada no mide 1200x800."
  }
  if ($dimensions.'miniatura-lomax.jpg'.ancho -ne 300 -or $dimensions.'miniatura-lomax.jpg'.alto -ne 200) {
    throw "La miniatura descargada no mide 300x200."
  }

  $rdsStates = Invoke-MySql -Sql "SELECT codigo, producto_id, estado FROM Productos WHERE codigo LIKE 'P4-LAMBDA-%' ORDER BY codigo;" -Port ([int]$rdsEndpoint.Port)
  [System.IO.File]::WriteAllLines((Join-Path $stageDirectory "rds-estados-pendientes.txt"), [string[]]$rdsStates, [System.Text.UTF8Encoding]::new($false))
  Write-Host "OK: JPEG y PNG validos procesados; original de 1200x800 -> miniatura de 300x200."
  Write-Host "OK: clave determinista estable tras repetir la invocacion; un solo objeto para el JPEG."
  Write-Host "OK: JPEG invalido y archivo >5 MiB terminan en ERROR, sin miniatura; RDS conserva PENDIENTE."
  Write-Host "Evidencias y archivos descargados: $stageDirectory"
}
finally {
  Pop-Location
}
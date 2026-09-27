param(
  [string]$DbPassword = $env:LOMAX_DB_PASSWORD,
  [string]$Region = "us-east-1",
  [string]$InstanceId = "lomax-mysql",
  [string]$TableName = "LomaxAtributos"
)

$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $false
$projectRoot = Split-Path -Parent $PSScriptRoot
$endpoint = "http://localhost:4567"
$dbUser = "lomax"

if ([string]::IsNullOrWhiteSpace($DbPassword)) {
  $DbPassword = "LomaxLocal2026!"
  Write-Warning "Usando clave de demostracion local. Define LOMAX_DB_PASSWORD para cambiarla; no uses esta clave fuera de local."
}

function Invoke-Aws {
  param([string[]]$Arguments)

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
  $result = & aws @Arguments --endpoint-url $endpoint --region $Region --output json 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if ($exitCode -ne 0) {
    throw "Fallo AWS CLI ($($Arguments -join ' ')): $($result -join "`n")"
  }
  if ($result) {
    return (($result -join "`n") | ConvertFrom-Json)
  }
}

function Invoke-MySql {
  param(
    [string]$Sql,
    [switch]$AllowFailure,
    [switch]$NoDatabase
  )

  $mysqlArguments = @(
    "mysql",
    "--host=host.docker.internal",
    "--port=$script:dbPort",
    "--user=$dbUser",
    "--batch",
    "--skip-column-names"
  )
  if (-not $NoDatabase) { $mysqlArguments += "--database=lomax_catalogo" }

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $output = $Sql | & docker run --rm --mount $script:databaseMount --env "MYSQL_PWD=$DbPassword" --interactive mysql:8.0 @mysqlArguments 2>&1
    $exitCode = $LASTEXITCODE
  }
  finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
  if (-not $AllowFailure -and $exitCode -ne 0) {
    throw "Fallo MySQL: $($output -join "`n")"
  }
  if ($AllowFailure) {
    return [pscustomobject]@{ ExitCode = $exitCode; Output = ($output -join "`n") }
  }
  return $output
}

function Get-MySqlScalar {
  param([string]$Sql)
  $result = @(Invoke-MySql -Sql $Sql)
  if ($result.Count -eq 0) { return "" }
  return [string]$result[0]
}

function Assert-NoProduct {
  param([string]$Code)
  $count = Get-MySqlScalar "SELECT COUNT(*) FROM Productos WHERE codigo = '$Code';"
  if ($count -ne "0") {
    throw "La operacion invalida dejo $count registro(s) con codigo $Code."
  }
}

Push-Location $projectRoot
try {
  foreach ($command in @("docker", "aws")) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) {
      throw "No se encontro '$command'. Instala Docker Desktop y AWS CLI v2."
    }
  }

  $env:AWS_ACCESS_KEY_ID = "test"
  $env:AWS_SECRET_ACCESS_KEY = "test"
  $env:AWS_DEFAULT_REGION = $Region
  $env:AWS_PAGER = ""

  & docker compose up -d floci
  if ($LASTEXITCODE -ne 0) { throw "No se pudo iniciar Floci con Docker Compose." }

  $ready = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
      Invoke-Aws -Arguments @("dynamodb", "list-tables") | Out-Null
      $ready = $true
      break
    } catch {
      Start-Sleep -Seconds 2
    }
  }
  if (-not $ready) { throw "Floci no respondio en $endpoint. Revisa 'docker compose logs floci'." }

  $instances = @( (Invoke-Aws -Arguments @("rds", "describe-db-instances")).DBInstances )
  $instance = $instances | Where-Object { $_.DBInstanceIdentifier -eq $InstanceId } | Select-Object -First 1
  if (-not $instance) {
    Write-Host "Creando instancia RDS MySQL '$InstanceId'..."
    Invoke-Aws -Arguments @(
      "rds", "create-db-instance",
      "--db-instance-identifier", $InstanceId,
      "--db-instance-class", "db.t3.micro",
      "--engine", "mysql",
      "--master-username", $dbUser,
      "--master-user-password", $DbPassword,
      "--allocated-storage", "20"
    ) | Out-Null
  }

  $instance = $null
  for ($attempt = 0; $attempt -lt 90; $attempt++) {
    $instances = @( (Invoke-Aws -Arguments @("rds", "describe-db-instances")).DBInstances )
    $instance = $instances | Where-Object { $_.DBInstanceIdentifier -eq $InstanceId } | Select-Object -First 1
    if ($instance -and $instance.DBInstanceStatus -eq "available") { break }
    if ($instance -and $instance.DBInstanceStatus -eq "failed") {
      throw "La instancia RDS quedo en estado failed. Revisa los logs de Floci."
    }
    Start-Sleep -Seconds 2
  }
  if (-not $instance -or $instance.DBInstanceStatus -ne "available") {
    throw "La instancia RDS no alcanzo el estado available."
  }

  $script:dbPort = [int]$instance.Endpoint.Port
  $script:databaseMount = "type=bind,source=$(Join-Path $projectRoot 'database'),target=/scripts,readonly"
  $mysqlReady = $false
  for ($attempt = 0; $attempt -lt 90; $attempt++) {
    $probe = Invoke-MySql -Sql "SELECT 1;" -AllowFailure -NoDatabase
    if ($probe.ExitCode -eq 0) {
      $mysqlReady = $true
      break
    }
    Start-Sleep -Seconds 2
  }
  if (-not $mysqlReady) { throw "MySQL RDS no acepta conexiones en host.docker.internal:$script:dbPort." }

  $schema = Get-Content (Join-Path $projectRoot "database/schema.sql") -Raw
  $seed = Get-Content (Join-Path $projectRoot "database/seed.sql") -Raw
  $schemaLoaded = $false
  for ($attempt = 0; $attempt -lt 60; $attempt++) {
    $schemaResult = Invoke-MySql -Sql $schema -AllowFailure -NoDatabase
    if ($schemaResult.ExitCode -eq 0) {
      $seedResult = Invoke-MySql -Sql $seed -AllowFailure -NoDatabase
      if ($seedResult.ExitCode -eq 0) {
        $schemaLoaded = $true
        break
      }
    }
    Start-Sleep -Seconds 2
  }
  if (-not $schemaLoaded) {
    throw "No se pudieron aplicar el esquema y las semillas SQL. Ultimo error: $($seedResult.Output)"
  }
  Write-Host "Esquema y 20 productos de ejemplo cargados en RDS/MySQL."

  $tables = @( (Invoke-Aws -Arguments @("dynamodb", "list-tables")).TableNames )
  if ($tables -notcontains $TableName) {
    Invoke-Aws -Arguments @(
      "dynamodb", "create-table",
      "--table-name", $TableName,
      "--attribute-definitions", "AttributeName=producto_id,AttributeType=N",
      "--key-schema", "AttributeName=producto_id,KeyType=HASH",
      "--billing-mode", "PAY_PER_REQUEST"
    ) | Out-Null
  }

  $rdsProducts = @{}
  foreach ($line in @(Invoke-MySql -Sql "SELECT producto_id, codigo FROM Productos ORDER BY producto_id;")) {
    $columns = ([string]$line) -split "`t"
    if ($columns.Count -ge 2) { $rdsProducts[$columns[1]] = $columns[0] }
  }

  $attributeRows = Get-Content (Join-Path $projectRoot "dynamodb/atributos.json") -Raw | ConvertFrom-Json
  foreach ($row in $attributeRows) {
    if (-not $rdsProducts.ContainsKey($row.codigo)) {
      throw "El codigo $($row.codigo) no existe en RDS; no se puede crear su item DynamoDB."
    }
    $attributeMap = @{}
    foreach ($property in $row.atributos.PSObject.Properties) {
      $attributeMap[$property.Name] = @{ S = [string]$property.Value }
    }
    $item = @{
      producto_id = @{ N = [string]$rdsProducts[$row.codigo] }
      codigo = @{ S = [string]$row.codigo }
      atributos = @{ M = $attributeMap }
      imagen_estado = @{ S = "PENDIENTE" }
    } | ConvertTo-Json -Depth 12 -Compress
    $itemFile = Join-Path ([System.IO.Path]::GetTempPath()) "lomax-dynamodb-item-$PID.json"
    [System.IO.File]::WriteAllText($itemFile, $item, [System.Text.UTF8Encoding]::new($false))
    try {
      Invoke-Aws -Arguments @("dynamodb", "put-item", "--table-name", $TableName, "--item", "file://$itemFile") | Out-Null
    }
    finally {
      Remove-Item $itemFile -ErrorAction SilentlyContinue
    }
  }
  Write-Host "Atributos variables cargados en DynamoDB con las claves producto_id de RDS."

  $testCode = "TEST-ETAPA2-VALIDO"
  Invoke-MySql -Sql "DELETE FROM Productos WHERE codigo = '$testCode';" | Out-Null
  try {
    $valid = Invoke-MySql -Sql "INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES ('$testCode', 'Producto de prueba', 'Registro de validacion de Etapa 2.', 10.50, 1, 'PENDIENTE');"
    $validCount = Get-MySqlScalar "SELECT COUNT(*) FROM Productos WHERE codigo = '$testCode';"
    if ($validCount -ne "1") { throw "La insercion valida no creo exactamente un registro." }
    Write-Host "OK: insercion valida aceptada."

    $duplicate = Invoke-MySql -Sql "INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES ('$testCode', 'Duplicado', 'Debe rechazarse.', 11.00, 1, 'PENDIENTE');" -AllowFailure
    if ($duplicate.ExitCode -eq 0) { throw "Se acepto un codigo duplicado." }
    $validCount = Get-MySqlScalar "SELECT COUNT(*) FROM Productos WHERE codigo = '$testCode';"
    if ($validCount -ne "1") { throw "El intento de codigo duplicado altero el registro existente." }
    Write-Host "OK: codigo duplicado rechazado sin registro adicional."

    $negativeCode = "TEST-ETAPA2-NEGATIVO"
    $negative = Invoke-MySql -Sql "INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES ('$negativeCode', 'Precio invalido', 'Debe rechazarse.', -1.00, 1, 'PENDIENTE');" -AllowFailure
    if ($negative.ExitCode -eq 0) { throw "Se acepto un precio negativo." }
    Assert-NoProduct $negativeCode
    Write-Host "OK: precio negativo rechazado sin registro parcial."

    $categoryCode = "TEST-ETAPA2-CATEGORIA"
    $missingCategory = Invoke-MySql -Sql "INSERT INTO Productos (codigo, nombre, descripcion, precio, categoria_id, estado) VALUES ('$categoryCode', 'Categoria invalida', 'Debe rechazarse.', 1.00, 4294967295, 'PENDIENTE');" -AllowFailure
    if ($missingCategory.ExitCode -eq 0) { throw "Se acepto una categoria inexistente." }
    Assert-NoProduct $categoryCode
    Write-Host "OK: categoria inexistente rechazada sin registro parcial."
  }
  finally {
    Invoke-MySql -Sql "DELETE FROM Productos WHERE codigo = '$testCode';" | Out-Null
    Invoke-MySql -Sql "DELETE FROM Productos WHERE codigo IN ('TEST-ETAPA2-NEGATIVO', 'TEST-ETAPA2-CATEGORIA');" | Out-Null
  }

  $scan = Invoke-Aws -Arguments @("dynamodb", "scan", "--table-name", $TableName, "--consistent-read")
  $checkedItems = 0
  $distinctAttributeSets = @{}
  foreach ($item in $scan.Items) {
    $productCode = [string]$item.codigo.S
    $productId = [string]$item.producto_id.N
    if (-not $rdsProducts.ContainsKey($productCode) -or $rdsProducts[$productCode] -ne $productId) {
      throw "DynamoDB producto_id=$productId/codigo=$productCode no corresponde a RDS."
    }
    if ($item.imagen_estado.S -ne "PENDIENTE") {
      throw "Se esperaba imagen_estado=PENDIENTE para $productCode en esta etapa."
    }
    $keys = @($item.atributos.M.PSObject.Properties.Name | Sort-Object) -join ","
    $distinctAttributeSets[$keys] = $true
    $checkedItems++
  }
  if ($checkedItems -ne $attributeRows.Count) {
    throw "DynamoDB devolvio $checkedItems items; se esperaban $($attributeRows.Count)."
  }
  if ($distinctAttributeSets.Count -lt 2) {
    throw "Los items DynamoDB no muestran esquemas de atributos diferentes."
  }

  Write-Host "OK: recuperados $checkedItems items DynamoDB; todos coinciden con su producto RDS y hay atributos variables."
  Write-Host "Etapa 2 completada. RDS MySQL: localhost:$script:dbPort / lomax_catalogo. DynamoDB: $TableName en $endpoint."
}
finally {
  Pop-Location
}
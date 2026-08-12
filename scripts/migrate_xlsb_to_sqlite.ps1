param(
    [Parameter(Mandatory = $true)]
    [string]$WorkbookPath,

    [Parameter(Mandatory = $true)]
    [string]$DatabasePath,

    [Parameter(Mandatory = $true)]
    [string]$SqliteExe
)

$ErrorActionPreference = "Stop"

$tableNames = @(
    "RQ_PKG_PLAN",
    "RQ_YLD",
    "RQ_CHIP_QTY",
    "RQ_CHIP_EQ",
    "RQ_DISPLAY_ORDER",
    "RQ_EQP_OWN",
    "RQ_EQP_LENT",
    "RQ_EQP_AVBL",
    "RQ_UPEH",
    "RQ_RUN_RATE",
    "RQ_VITAL",
    "RQ_MODULE",
    "RQ_RUN_DAY",
    "RQ_LOT_RATIO",
    "RQ_WF_RATIO",
    "RQ_REQB"
)

function Quote-Identifier([string]$Value) {
    return '"' + $Value.Replace('"', '""') + '"'
}

function Quote-SqlText([string]$Value) {
    return "'" + $Value.Replace("'", "''") + "'"
}

function Get-SqliteType([object[]]$Values) {
    $notNull = @($Values | Where-Object { $null -ne $_ -and $_ -ne "" })
    if ($notNull.Count -eq 0) {
        return "TEXT"
    }
    $numeric = @($notNull | Where-Object {
        $_ -is [byte] -or $_ -is [int16] -or $_ -is [int32] -or
        $_ -is [int64] -or $_ -is [single] -or $_ -is [double] -or
        $_ -is [decimal]
    })
    if ($numeric.Count -ne $notNull.Count) {
        return "TEXT"
    }
    $wholeNumbers = @($numeric | Where-Object {
        [double]$_ -eq [math]::Truncate([double]$_)
    })
    if ($wholeNumbers.Count -eq $numeric.Count) {
        return "INTEGER"
    }
    return "REAL"
}

function Read-ExcelTable($Workbook, [string]$TableName) {
    foreach ($sheet in $Workbook.Worksheets) {
        foreach ($table in $sheet.ListObjects) {
            if ($table.Name -ne $TableName) {
                continue
            }
            $values = $table.Range.Value2
            $rowCount = $values.GetLength(0)
            $columnCount = $values.GetLength(1)
            $headers = @()
            for ($column = 1; $column -le $columnCount; $column++) {
                $header = [string]$values[1, $column]
                if ([string]::IsNullOrWhiteSpace($header)) {
                    throw "빈 헤더가 존재합니다: $TableName"
                }
                $headers += $header.Trim()
            }
            if (@($headers | Select-Object -Unique).Count -ne $headers.Count) {
                throw "중복 헤더가 존재합니다: $TableName"
            }
            $rows = @()
            for ($row = 2; $row -le $rowCount; $row++) {
                $item = [ordered]@{}
                for ($column = 1; $column -le $columnCount; $column++) {
                    $item[$headers[$column - 1]] = $values[$row, $column]
                }
                $rows += [pscustomobject]$item
            }
            return [pscustomobject]@{
                Name = $TableName
                Headers = $headers
                Rows = $rows
            }
        }
    }
    throw "Excel Table을 찾을 수 없습니다: $TableName"
}

$resolvedWorkbook = [System.IO.Path]::GetFullPath($WorkbookPath)
$resolvedDatabase = [System.IO.Path]::GetFullPath($DatabasePath)
$resolvedSqlite = [System.IO.Path]::GetFullPath($SqliteExe)

if (-not (Test-Path -LiteralPath $resolvedWorkbook -PathType Leaf)) {
    throw "Workbook을 찾을 수 없습니다: $resolvedWorkbook"
}
if (-not (Test-Path -LiteralPath $resolvedSqlite -PathType Leaf)) {
    throw "sqlite3 실행 파일을 찾을 수 없습니다: $resolvedSqlite"
}

$databaseDirectory = Split-Path -Parent $resolvedDatabase
New-Item -ItemType Directory -Path $databaseDirectory -Force | Out-Null
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("capa_sqlite_" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $temporaryRoot -Force | Out-Null
$temporaryDatabase = Join-Path $temporaryRoot "capa_simulation.db"
$sqlPath = Join-Path $temporaryRoot "import.sql"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$excel = $null
$workbook = $null

try {
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $workbook = $excel.Workbooks.Open($resolvedWorkbook, 0, $true)

    $tables = @()
    foreach ($tableName in $tableNames) {
        $tables += Read-ExcelTable $workbook $tableName
    }

    $sql = New-Object System.Collections.Generic.List[string]
    $sql.Add(".bail on")
    $sql.Add("PRAGMA journal_mode=DELETE;")
    $sql.Add("PRAGMA synchronous=FULL;")
    $sql.Add("BEGIN IMMEDIATE;")

    $tableMetadata = @()
    foreach ($table in $tables) {
        $csvPath = Join-Path $temporaryRoot ($table.Name + ".csv")
        $csvLines = @($table.Rows | ConvertTo-Csv -NoTypeInformation)
        [System.IO.File]::WriteAllLines($csvPath, $csvLines, $utf8NoBom)

        $columnDefinitions = @()
        for ($column = 0; $column -lt $table.Headers.Count; $column++) {
            $header = $table.Headers[$column]
            $columnValues = @($table.Rows | ForEach-Object { $_.$header })
            $columnType = Get-SqliteType $columnValues
            $columnDefinitions += (Quote-Identifier $header) + " " + $columnType
        }
        $quotedTable = Quote-Identifier $table.Name
        $sql.Add("CREATE TABLE $quotedTable (" + ($columnDefinitions -join ", ") + ");")
        $sql.Add(".mode csv")
        $sql.Add('.import --skip 1 "' + $csvPath.Replace("\", "/") + '" "' + $table.Name + '"')

        $tableMetadata += [pscustomobject]@{
            TableName = $table.Name
            RowCount = $table.Rows.Count
            ColumnCount = $table.Headers.Count
            CsvSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $csvPath).Hash
        }
    }

    $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedWorkbook).Hash
    $importedAt = (Get-Date).ToString("yyyy-MM-ddTHH:mm:ssK")
    $sql.Add(@"
CREATE TABLE "_import_history" (
    "table_name" TEXT NOT NULL,
    "row_count" INTEGER NOT NULL,
    "column_count" INTEGER NOT NULL,
    "csv_sha256" TEXT NOT NULL,
    "source_file" TEXT NOT NULL,
    "source_sha256" TEXT NOT NULL,
    "imported_at" TEXT NOT NULL
);
"@)
    foreach ($metadata in $tableMetadata) {
        $sql.Add(
            'INSERT INTO "_import_history" VALUES (' +
            (Quote-SqlText $metadata.TableName) + ", " +
            $metadata.RowCount + ", " +
            $metadata.ColumnCount + ", " +
            (Quote-SqlText $metadata.CsvSha256) + ", " +
            (Quote-SqlText $resolvedWorkbook) + ", " +
            (Quote-SqlText $sourceHash) + ", " +
            (Quote-SqlText $importedAt) + ");"
        )
    }
    $sql.Add("COMMIT;")
    [System.IO.File]::WriteAllLines($sqlPath, $sql, $utf8NoBom)

    $readCommand = '.read "' + $sqlPath.Replace("\", "/") + '"'
    $sqliteOutput = & $resolvedSqlite $temporaryDatabase $readCommand 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "SQLite import 실패: $sqliteOutput"
    }

    $integrity = (& $resolvedSqlite $temporaryDatabase "PRAGMA integrity_check;").Trim()
    if ($integrity -ne "ok") {
        throw "SQLite 무결성 검사 실패: $integrity"
    }
    foreach ($metadata in $tableMetadata) {
        $quotedTable = Quote-Identifier $metadata.TableName
        $actualRows = [int](& $resolvedSqlite $temporaryDatabase "SELECT COUNT(*) FROM $quotedTable;")
        $actualColumns = [int](& $resolvedSqlite $temporaryDatabase "SELECT COUNT(*) FROM pragma_table_info('$($metadata.TableName)');")
        if ($actualRows -ne $metadata.RowCount -or $actualColumns -ne $metadata.ColumnCount) {
            throw "검증 실패: $($metadata.TableName) Excel=$($metadata.RowCount)x$($metadata.ColumnCount), SQLite=${actualRows}x${actualColumns}"
        }
    }

    if (Test-Path -LiteralPath $resolvedDatabase) {
        $backupPath = $resolvedDatabase + "." + (Get-Date -Format "yyyyMMddHHmmss") + ".bak"
        Copy-Item -LiteralPath $resolvedDatabase -Destination $backupPath
    }
    Move-Item -LiteralPath $temporaryDatabase -Destination $resolvedDatabase -Force

    [pscustomobject]@{
        Database = $resolvedDatabase
        Tables = $tableMetadata.Count
        Rows = ($tableMetadata | Measure-Object -Property RowCount -Sum).Sum
        Integrity = $integrity
        SourceSha256 = $sourceHash
    } | Format-List
} finally {
    if ($null -ne $workbook) {
        $workbook.Close($false)
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($workbook) | Out-Null
    }
    if ($null -ne $excel) {
        $excel.Quit()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($excel) | Out-Null
    }
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}

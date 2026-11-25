$ErrorActionPreference = "Stop"
$docx = "C:\Users\Angel\air-quality-belarus\docs\Курсовая записка - Мониторинг экосистемы.docx"
$pdf  = "C:\Users\Angel\air-quality-belarus\docs\Курсовая записка - Мониторинг экосистемы.pdf"

Get-Process WINWORD -ErrorAction SilentlyContinue | Stop-Process -Force
if (Test-Path $pdf) { Remove-Item $pdf -Force }
Write-Output "STEP start"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
Write-Output "STEP word-created"

$doc = $word.Documents.Open($docx)
Write-Output "STEP opened"

$doc.Fields.Update() | Out-Null
Write-Output "STEP fields-updated"

$doc.Repaginate()
Write-Output "STEP repaginated"

if ($doc.TablesOfContents.Count -gt 0) {
    $doc.TablesOfContents.Item(1).Update()
    Write-Output "STEP toc-updated"
} else {
    Write-Output "STEP toc-missing"
}

$doc.Save()
Write-Output "STEP saved"

$doc.ExportAsFixedFormat($pdf, 17)
Write-Output "STEP pdf-exported"

$doc.Close(0)
$word.Quit()
Write-Output "STEP done"

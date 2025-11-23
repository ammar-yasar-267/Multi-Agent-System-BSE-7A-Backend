# Presentation Feedback Agent - Test Script
param(
    [string]$TestFile = "test_sample.json"
)

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Presentation Feedback Agent - Test" -ForegroundColor Cyan
Write-Host "Test File: $TestFile" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check if agent is running
Write-Host "[1/3] Checking agent..." -ForegroundColor Yellow
try {
    $healthCheck = Invoke-RestMethod -Uri "http://127.0.0.1:5019/health" -Method Get -ErrorAction Stop
    Write-Host "[OK] Agent healthy (v$($healthCheck.version))" -ForegroundColor Green
    Write-Host ""
} catch {
    Write-Host "[ERROR] Agent not running!" -ForegroundColor Red
    Write-Host "Start with: .\run_presentation_feedback.bat" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# Check test file exists
if (-not (Test-Path $TestFile)) {
    Write-Host "[ERROR] Test file not found: $TestFile" -ForegroundColor Red
    Write-Host "Available: test_sample.json, test_sample_confident.json, test_sample_poor.json, test_sample_technical.json" -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

# Send request
Write-Host "[2/3] Analyzing presentation..." -ForegroundColor Yellow
try {
    $response = Invoke-RestMethod -Uri "http://127.0.0.1:5019/process" `
        -Method Post `
        -ContentType "application/json" `
        -Body (Get-Content -Path $TestFile -Raw) `
        -ErrorAction Stop

    Write-Host "[OK] Analysis complete!" -ForegroundColor Green
    Write-Host ""

    # Display results
    Write-Host "[3/3] Results:" -ForegroundColor Yellow
    Write-Host "============================================" -ForegroundColor Cyan

    $output = $response.results.output
    Write-Host "ID: $($output.presentation_id)" -ForegroundColor White
    Write-Host "Score: $($output.summary.overall_score)/10" -ForegroundColor $(if ($output.summary.overall_score -ge 7) { "Green" } elseif ($output.summary.overall_score -ge 5) { "Yellow" } else { "Red" })
    Write-Host ""

    Write-Host "STRENGTHS:" -ForegroundColor Green
    $output.summary.strengths | ForEach-Object { Write-Host "  + $_" -ForegroundColor Green }
    Write-Host ""

    Write-Host "WEAKNESSES:" -ForegroundColor Red
    $output.summary.weaknesses | ForEach-Object { Write-Host "  - $_" -ForegroundColor Red }
    Write-Host ""

    Write-Host "OPTIMIZATIONS: ($($output.optimizations.Count))" -ForegroundColor Yellow
    $output.optimizations | ForEach-Object -Begin { $i=1 } -Process {
        Write-Host "  $i. [$($_.category.ToUpper())] $($_.issue)" -ForegroundColor Yellow
        Write-Host "     → $($_.suggestion)" -ForegroundColor Gray
        $i++
    }
    Write-Host ""

    Write-Host "IMPROVEMENT: $($output.overall_recommendations.estimated_improvement)" -ForegroundColor Cyan
    Write-Host "============================================" -ForegroundColor Cyan

    # Save results
    $response | ConvertTo-Json -Depth 10 | Out-File -FilePath "test_result.json" -Encoding UTF8
    Write-Host "Full results: test_result.json" -ForegroundColor Gray

} catch {
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host ""
Read-Host "Press Enter to exit"

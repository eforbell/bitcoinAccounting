<#
.SYNOPSIS
    Test runner for the bitcoinAccounting project.
    
.DESCRIPTION
    Runs all tests in the tests/ directory using pytest.
    Supports verbose output and coverage reporting.
    
.PARAMETER Verbose
    Enable verbose test output.
    
.PARAMETER Coverage
    Run with coverage reporting (requires coverage package).
    
.EXAMPLE
    .\run_tests.ps1
    
.EXAMPLE
    .\run_tests.ps1 -Verbose
    
.EXAMPLE
    .\run_tests.ps1 -Coverage
#>

param(
    [switch]$Verbose,
    [switch]$Coverage
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Colors for output
$SuccessColor = "Green"
$ErrorColor = "Red"
$InfoColor = "Cyan"
$WarningColor = "Yellow"

Write-Host "`n=== bitcoinAccounting Test Runner ===" -ForegroundColor $InfoColor

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir

try {
    $python = if (Test-Path (Join-Path $scriptDir ".venv/Scripts/python.exe")) {
        Join-Path $scriptDir ".venv/Scripts/python.exe"
    } elseif (Test-Path (Join-Path $scriptDir "venv/Scripts/python.exe")) {
        Join-Path $scriptDir "venv/Scripts/python.exe"
    } else {
        "python"
    }
    $pythonVersion = & $python --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor $ErrorColor
        exit 1
    }
    Write-Host "Python: $pythonVersion" -ForegroundColor $InfoColor

    # Build the test command
    $testArgs = @("-m", "pytest", "tests")
    if ($Verbose) {
        $testArgs += "-v"
        Write-Host "Running tests in verbose mode..." -ForegroundColor $InfoColor
    } else {
        Write-Host "Running tests..." -ForegroundColor $InfoColor
    }
    
    # Run tests
    Write-Host ""
    & $python @testArgs
    $testExitCode = $LASTEXITCODE
    
    Write-Host ""
    
    if ($testExitCode -eq 0) {
        Write-Host "All tests passed!" -ForegroundColor $SuccessColor
    } else {
        Write-Host "Tests failed with exit code: $testExitCode" -ForegroundColor $ErrorColor
    }
    
    # Optional: Run coverage if requested
    if ($Coverage) {
        Write-Host "`n=== Coverage Report ===" -ForegroundColor $InfoColor
        
        # Check if coverage is installed
        try {
            $coverageVersion = & $python -m pip show coverage 2>&1 | Select-String "Version"
            if ($null -eq $coverageVersion) {
                Write-Host "Installing coverage package..." -ForegroundColor $WarningColor
                & $python -m pip install coverage | Out-Null
            }
        } catch {
            Write-Host "Warning: Could not verify coverage installation" -ForegroundColor $WarningColor
        }
        
        # Run coverage
        Write-Host "Running coverage analysis..." -ForegroundColor $InfoColor
        & $python -m coverage run -m pytest tests 2>&1 | Out-Null
        & $python -m coverage report -m --include="src/python/*"
    }
    
    exit $testExitCode
    
} finally {
    Pop-Location
}

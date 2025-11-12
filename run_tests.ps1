<#
.SYNOPSIS
    Test runner for the cryptoAccounting project.
    
.DESCRIPTION
    Runs all unit tests in the tests/ directory using Python's unittest framework.
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

Write-Host "`n=== cryptoAccounting Test Runner ===" -ForegroundColor $InfoColor

# Check if Python is available
try {
    $pythonVersion = python --version 2>&1
    Write-Host "Python: $pythonVersion" -ForegroundColor $InfoColor
} catch {
    Write-Host "ERROR: Python is not installed or not in PATH" -ForegroundColor $ErrorColor
    exit 1
}

# Get the script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $scriptDir

try {
    # Build the test command
    $testCommand = "python -m unittest discover -s tests -p test_*.py"
    
    if ($Verbose) {
        $testCommand += " -v"
        Write-Host "Running tests in verbose mode..." -ForegroundColor $InfoColor
    } else {
        Write-Host "Running tests..." -ForegroundColor $InfoColor
    }
    
    # Run tests
    Write-Host ""
    Invoke-Expression $testCommand
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
            $coverageVersion = pip show coverage 2>&1 | Select-String "Version"
            if ($null -eq $coverageVersion) {
                Write-Host "Installing coverage package..." -ForegroundColor $WarningColor
                pip install coverage | Out-Null
            }
        } catch {
            Write-Host "Warning: Could not verify coverage installation" -ForegroundColor $WarningColor
        }
        
        # Run coverage
        Write-Host "Running coverage analysis..." -ForegroundColor $InfoColor
        coverage run -m unittest discover -s tests -p test_*.py 2>&1 | Out-Null
        coverage report -m --include="src/python/*"
    }
    
    exit $testExitCode
    
} finally {
    Pop-Location
}


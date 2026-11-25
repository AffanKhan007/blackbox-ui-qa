<#
.SYNOPSIS
Install the blackbox-ui-qa Agent Skill for supported hosts.

.EXAMPLE
.\install.ps1 -Scope Global

.EXAMPLE
.\install.ps1 -Scope Project -HostName opencode
#>
[CmdletBinding()]
param(
    [ValidateSet("Global", "Project")]
    [string]$Scope = "Global",

    [ValidateSet("universal", "claude", "opencode", "codex", "cursor", "windsurf", "gemini", "copilot", "all")]
    [string]$HostName = "universal"
)

$ErrorActionPreference = "Stop"
$SkillName = "blackbox-ui-qa"
$SrcDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$AllHosts = @("universal", "claude", "opencode", "codex", "cursor", "windsurf", "gemini", "copilot")

function Get-Destination {
    param([string]$AgentHost)

    $base = if ($Scope -eq "Global") { $HOME } else { (Get-Location).Path }

    switch ($AgentHost) {
        "universal" { return Join-Path $base ".agents\skills\$SkillName" }
        "claude"    { return Join-Path $base ".claude\skills\$SkillName" }
        "opencode"  {
            if ($Scope -eq "Global") { return Join-Path $base ".config\opencode\skills\$SkillName" }
            return Join-Path $base ".opencode\skills\$SkillName"
        }
        "codex"     { return Join-Path $base ".codex\skills\$SkillName" }
        "cursor"    { return Join-Path $base ".cursor\skills\$SkillName" }
        "windsurf"  {
            if ($Scope -eq "Global") { return Join-Path $base ".codeium\windsurf\skills\$SkillName" }
            return Join-Path $base ".windsurf\skills\$SkillName"
        }
        "gemini"    { return Join-Path $base ".gemini\skills\$SkillName" }
        "copilot"   {
            if ($Scope -eq "Global") { return Join-Path $base ".copilot\skills\$SkillName" }
            return Join-Path $base ".github\skills\$SkillName"
        }
        default     { throw "Unknown host: $AgentHost" }
    }
}

function Install-One {
    param([string]$AgentHost)

    $dest = Get-Destination -AgentHost $AgentHost
    $refDest = Join-Path $dest "references"
    $scriptDest = Join-Path $dest "scripts"

    if (Test-Path $refDest) { Remove-Item -Path $refDest -Recurse -Force }
    if (Test-Path $scriptDest) { Remove-Item -Path $scriptDest -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $refDest | Out-Null
    New-Item -ItemType Directory -Force -Path $scriptDest | Out-Null

    Copy-Item -Path (Join-Path $SrcDir "SKILL.md") -Destination (Join-Path $dest "SKILL.md") -Force
    Copy-Item -Path (Join-Path $SrcDir "references\*.md") -Destination $refDest -Force
    Copy-Item -Path (Join-Path $SrcDir "scripts\*.py") -Destination $scriptDest -Force
    $jsFiles = Get-ChildItem -Path (Join-Path $SrcDir "scripts\*.js") -ErrorAction SilentlyContinue
    if ($jsFiles) {
        Copy-Item -Path $jsFiles.FullName -Destination $scriptDest -Force
    }

    Write-Host "[+] Installed $SkillName -> $dest"
}

if ($HostName -eq "all") {
    foreach ($h in $AllHosts) {
        Install-One -AgentHost $h
    }
} else {
    Install-One -AgentHost $HostName
}

Write-Host ""
Write-Host "[OK] Installed. Start a new agent session so the skill is discovered."
Write-Host '     Then ask: "Use blackbox-ui-qa to audit https://staging.example.com ..."'
Write-Host ""
Write-Host "Requirements:"
Write-Host "  Python 3.10+ and openpyxl:   pip install openpyxl"
Write-Host "  Optional Playwright:         pip install playwright; playwright install chromium"

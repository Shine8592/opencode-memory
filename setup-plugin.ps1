<#
.SYNOPSIS
  Install universal-agent-memory plugin for opencode.
.DESCRIPTION
  Copies the plugin to .opencode/plugins/ and sets MEMORY_MCP_HOME env var.
#>
param(
  [string]$ProjectRoot = (Get-Location).Path,
  [string]$MemoryMcpHome = $null
)

if (-not $MemoryMcpHome) {
  $MemoryMcpHome = Join-Path $ProjectRoot "universal-agent-memory"
}

Write-Host "Installing universal-agent-memory plugin..." -ForegroundColor Cyan

# 1. Ensure .opencode/plugins/memory-plugin/
$pluginsDir = Join-Path (Join-Path $ProjectRoot ".opencode") "plugins"
$pluginDir = Join-Path $pluginsDir "memory-plugin"
New-Item -ItemType Directory -Path $pluginDir -Force | Out-Null

# 2. Copy plugin files
$pluginSrc = Join-Path $MemoryMcpHome "plugin" "src" "index.ts"
$pluginDst = Join-Path $pluginDir "index.ts"
Copy-Item -Path $pluginSrc -Destination $pluginDst -Force
Write-Host "  [OK] Plugin copied to $pluginDir" -ForegroundColor Green

# 3. Ensure .opencode/package.json for @opencode-ai/plugin
$opencodePkg = Join-Path (Join-Path $ProjectRoot ".opencode") "package.json"
if (-not (Test-Path $opencodePkg)) {
  $pkg = @{ dependencies = @{ "@opencode-ai/plugin" = "latest" } }
  $pkg | ConvertTo-Json | Set-Content -Path $opencodePkg -Encoding UTF8
  Write-Host "  [OK] Created .opencode/package.json" -ForegroundColor Green
}

# 4. Set MEMORY_MCP_HOME env var (user-level persistent)
try {
  [Environment]::SetEnvironmentVariable("MEMORY_MCP_HOME", $MemoryMcpHome, "User")
  Write-Host "  [OK] MEMORY_MCP_HOME = $MemoryMcpHome" -ForegroundColor Green
} catch {
  Write-Host "  [WARN] Could not set env var. Run manually:" -ForegroundColor Yellow
  Write-Host "    setx MEMORY_MCP_HOME \""$MemoryMcpHome"\"" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[DONE] Restart opencode to load the plugin." -ForegroundColor Cyan
Write-Host "  If @opencode-ai/plugin import fails, run: cd '$ProjectRoot\.opencode' && bun install" -ForegroundColor Yellow

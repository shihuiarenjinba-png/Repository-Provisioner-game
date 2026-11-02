# Real Signal Sprint GUI smoke: automated check-only, never human QA.
param([Parameter(Mandatory=$true)][string]$ExePath,
      [Parameter(Mandatory=$true)][string]$ReceiptPath,
      [string]$ScreenshotPath = "")
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$expectedSha = 'beb683b61b4fa4b2ec90fe1d413363c8a535bd4cb72b41b54b03a9685f516ee0'
$expectedSize = 11344389
$receipt = [ordered]@{
  schema_version = 1; product = 'Signal Sprint'; registration = 'GDK_GAME'
  evidence_kind = 'REAL_WINDOWS_EXE_UIAUTOMATION_CHECK_ONLY'
  source_sha = 'c058cbf7fe38e02d929c67d047d717ff74bd522e'
  new_request_id = 'game-signal-sprint-c058cbf7fe38e02d929c67d047d717ff74bd522e-reissue-sprint-41361263698-41361263698'
  github_run_id = 41361263698; github_artifact_id = 13105352227
  exe_sha256 = $expectedSha; exe_size_bytes = $expectedSize
  status = 'WINDOWS_GUI_CHECK_ONLY_HOLD'; reason = 'NOT_EXECUTED'
  process_launched = $false; window_observed = $false
  first_move_ui_observed = $false; loss_ui_observed = $false; retry_ui_observed = $false
  first_move_seconds = $null; screenshot_captured = $false; screenshot_dimensions = $null
  human_qa_pass = $false; consumer_sale_ready = $false; cas_return_pass = $false
  gdk_sdk_executed = $false; real_msixvc_built = $false; store_submitted = $false
}
function Save-Receipt {
  $parent = Split-Path -Parent $ReceiptPath
  if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
  $receipt | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ReceiptPath -Encoding UTF8
  Write-Host ($receipt | ConvertTo-Json -Compress -Depth 8)
}
function Require([bool]$ok, [string]$reason) {
  if (-not $ok) { throw $reason }
}
function Names($window) {
  $condition = [System.Windows.Automation.PropertyCondition]::new(
    [System.Windows.Automation.AutomationElement]::ControlTypeProperty,
    [System.Windows.Automation.ControlType]::Text)
  $nodes = $window.FindAll([System.Windows.Automation.TreeScope]::Descendants, $condition)
  $texts = @()
  for ($i = 0; $i -lt $nodes.Count; $i++) { $texts += [string]$nodes.Item($i).Current.Name }
  return ($texts -join [Environment]::NewLine)
}
function Send-RealKey([string]$key, [int]$targetProcessId) {
  [Microsoft.VisualBasic.Interaction]::AppActivate($targetProcessId) | Out-Null
  Start-Sleep -Milliseconds 120
  [System.Windows.Forms.SendKeys]::SendWait($key)
  Start-Sleep -Milliseconds 120
}
$proc = $null
try {
  Require ([Environment]::OSVersion.Platform -eq [PlatformID]::Win32NT) 'NOT_WINDOWS'
  Require (Test-Path -LiteralPath $ExePath -PathType Leaf) 'EXE_NOT_FOUND'
  $file = Get-Item -LiteralPath $ExePath
  Require ($file.Length -eq $expectedSize) 'EXE_SIZE_MISMATCH'
  $actual = (Get-FileHash -LiteralPath $ExePath -Algorithm SHA256).Hash.ToLowerInvariant()
  Require ($actual -ceq $expectedSha) 'EXE_SHA256_MISMATCH'
  $header = [System.IO.File]::ReadAllBytes($ExePath)
  Require ($header[0] -eq 77 -and $header[1] -eq 90) 'EXE_PE_HEADER_MISMATCH'
  Add-Type -AssemblyName UIAutomationClient
  Add-Type -AssemblyName UIAutomationTypes
  Add-Type -AssemblyName System.Windows.Forms
  Add-Type -AssemblyName System.Drawing
  Add-Type -AssemblyName Microsoft.VisualBasic
  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  $proc = Start-Process -FilePath (Resolve-Path -LiteralPath $ExePath).Path -WorkingDirectory $file.DirectoryName -PassThru
  $receipt.process_launched = $true
  $window = $null
  for ($attempt = 0; $attempt -lt 35; $attempt++) {
    Start-Sleep -Milliseconds 500
    $proc.Refresh()
    if ($proc.HasExited) { throw ('PROCESS_EXITED_BEFORE_WINDOW:' + $proc.ExitCode) }
    if ($proc.MainWindowHandle -ne [IntPtr]::Zero) {
      $window = [System.Windows.Automation.AutomationElement]::FromHandle($proc.MainWindowHandle)
      if ($null -ne $window -and $window.Current.Name -like 'Signal Sprint*') { break }
    }
  }
  Require ($null -ne $window -and $window.Current.Name -like 'Signal Sprint*') 'NO_INTERACTIVE_GUI_WINDOW_OR_SESSION'
  $receipt.window_observed = $true
  $initial = Names $window
  Require ($initial -match 'Moves left:\s*30' -and $initial -match 'Cells:\s*0/3') 'INITIAL_GAME_STATE_NOT_OBSERVABLE'
  Require ($initial -match 'Collect 3 energy cells' -and $initial -match 'Arrows / WASD') 'OBJECTIVE_OR_INPUT_GUIDANCE_NOT_OBSERVABLE'
  Send-RealKey '{RIGHT}' $proc.Id
  $afterMove = Names $window
  Require ($afterMove -match 'Moves left:\s*29' -and $afterMove -match 'Cells:\s*0/3') 'FIRST_REAL_INPUT_NO_OBSERVABLE_UI_CHANGE'
  $receipt.first_move_ui_observed = $true
  $receipt.first_move_seconds = [math]::Round($timer.Elapsed.TotalSeconds, 3)
  Require ($receipt.first_move_seconds -le 30) 'FIRST_INPUT_EXCEEDS_30_SECONDS'
  for ($i = 0; $i -lt 29; $i++) {
    if (($i % 2) -eq 0) { Send-RealKey '{LEFT}' $proc.Id }
    else { Send-RealKey '{RIGHT}' $proc.Id }
  }
  $afterLoss = Names $window
  Require ($afterLoss -match 'LOST' -and $afterLoss -match 'Out of moves') 'LOSS_REASON_NOT_OBSERVABLE'
  $receipt.loss_ui_observed = $true
  Send-RealKey 'r' $proc.Id
  $afterRetry = Names $window
  Require ($afterRetry -match 'PLAYING' -and $afterRetry -match 'Moves left:\s*30') 'RETRY_DID_NOT_RESET_UI'
  $receipt.retry_ui_observed = $true
  if ($ScreenshotPath) {
    try {
      $bounds = $window.Current.BoundingRectangle
      $screen = [System.Windows.Forms.Screen]::FromHandle($proc.MainWindowHandle).Bounds
      $width = [int][math]::Min(1024, $bounds.Width)
      $height = [int][math]::Min(768, $bounds.Height)
      if ($width -ge 820 -and $height -ge 640 -and
          $bounds.Left -ge $screen.Left -and $bounds.Top -ge $screen.Top -and
          ($bounds.Left + $width) -le $screen.Right -and
          ($bounds.Top + $height) -le $screen.Bottom) {
        $bitmap = [System.Drawing.Bitmap]::new($width, $height)
        try {
          $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
          try {
            $graphics.CopyFromScreen([int]$bounds.Left, [int]$bounds.Top, 0, 0,
              ([System.Drawing.Size]::new($width, $height)))
          } finally { $graphics.Dispose() }
          $bitmap.Save($ScreenshotPath, [System.Drawing.Imaging.ImageFormat]::Png)
          $receipt.screenshot_captured = $true
          $receipt.screenshot_dimensions = @($width, $height)
        } finally { $bitmap.Dispose() }
      }
    } catch { $receipt.screenshot_reason = 'CAPTURE_NOT_AVAILABLE:' + $_.Exception.GetType().Name }
  }
  $receipt.status = 'WINDOWS_GUI_AUTOMATED_CHECK_ONLY'
  $receipt.reason = 'REAL_WINDOW_FIRST_MOVE_LOSS_RETRY_OBSERVED_NOT_HUMAN_QA'
} catch {
  $receipt.status = 'WINDOWS_GUI_CHECK_ONLY_HOLD'
  $receipt.reason = [string]$_.Exception.Message
} finally {
  if ($null -ne $proc) {
    try {
      $proc.Refresh()
      if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction Stop }
    } catch { $receipt.process_cleanup_warning = $_.Exception.Message }
  }
  Save-Receipt
}
if ($receipt.status -ne 'WINDOWS_GUI_AUTOMATED_CHECK_ONLY') { exit 2 }
exit 0

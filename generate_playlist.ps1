#!/usr/bin/env pwsh
# TurkSpor/InatBox -> Tivimate M3U uretici (cdnlive sunucusu icin dogrulanmis yol)
# Cikti: playlist.m3u
$ErrorActionPreference = 'SilentlyContinue'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

function B64U($s){
  if(-not $s){ return '' }
  try{
    $t = $s.Replace('-','+').Replace('_','/')
    while($t.Length % 4 -ne 0){ $t += '=' }
    [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($t))
  } catch { '' }
}

# Kanal listesi -> belirtilen server turunu dondurur
function Get-NtvsChannels([string]$search, [string]$server, [int]$limit = 120, [int]$maxPages = 6){
  $out = @()
  for($off = 0; $off -lt ($maxPages * $limit); $off += $limit){
    $u = "https://www.ntvs.cx/api/get-channels?limit=$limit&offset=$off&search=$([uri]::EscapeDataString($search))"
    try {
      $r = Invoke-RestMethod -Uri $u -TimeoutSec 25 -Headers @{"User-Agent"="Mozilla/5.0"; "Referer"="https://www.ntvs.cx/"}
    } catch { break }
    $batch = $r.channels | Where-Object { $_.server -eq $server }
    if(-not $batch){ break }
    $out += $batch
    if($r.channels.Count -lt $limit){ break }
  }
  $out | Select-Object -Unique -Property channel_id, channel_name, channel_url, server
}

# cdnlive oyuncu sayfasindan imzali m3u8 URL'sini uretir
# Yontem (CloudStream eklentisindeki ile ayni): DOM sirasindaki base64 parcalarini
# cozup birlestirmek; sonuc 'cdnlivetv.tv/.../playlist.m3u8?token=...' cikar.
function Resolve-CdnLive([string]$playerUrl){
  if(-not $playerUrl){ return $null }
  $h = @{"User-Agent"="Mozilla/5.0"; "Referer"="https://www.ntvs.cx/"}
  $html = (Invoke-WebRequest -Uri $playerUrl -UseBasicParsing -TimeoutSec 25 -Headers $h).Content
  $vars = @{}
  foreach($m in [regex]::Matches($html, "var\s+([A-Za-z0-9_]+)\s*=\s*'([A-Za-z0-9+/=_-]{12,})'")){
    if(-not $vars.ContainsKey($m.Groups[1].Value)){ $vars[$m.Groups[1].Value] = $m.Groups[2].Value }
  }
  # en son 'var X = F(A)+F(B)+F(C)+...' zincirini bul (F = base64 decoder adi rastgele)
  $chain = [regex]::Match($html, "var\s+[A-Za-z0-9_]+\s*=\s*((?:[A-Za-z0-9_]+\([A-Za-z0-9_]+\)\s*\+\s*){8,}[A-Za-z0-9_]+\([A-Za-z0-9_]+\))")
  if(-not $chain.Success){ return $null }
  $url = ''
  foreach($c in [regex]::Matches($chain.Groups[1].Value, "\(([A-Za-z0-9_]+)\)")){
    if($vars.ContainsKey($c.Groups[1].Value)){ $url += B64U $vars[$c.Groups[1].Value] }
  }
  if($url -notmatch '^https?://'){ return $null }
  $url
}

# dlhd / hesgoales best-effort (kaynaklar sık değişir; başarısız olursa atlanır)
function Resolve-Dlhd([string]$playerUrl){ return $null }
function Resolve-Hesgoales([string]$playerUrl){ return $null }

$search = if($args.Count -gt 0){ $args[0] } else { 'spor' }
$outFile = if($args.Count -gt 1){ $args[1] } else { 'playlist.m3u' }

$entries = @()
$chans = Get-NtvsChannels -search $search -server 'cdnlive'
foreach($ch in $chans){
  $url = Resolve-CdnLive $ch.channel_url
  if($url){
    Write-Host "  + $($ch.channel_name)" -ForegroundColor Green
    $entries += [pscustomobject]@{ Name = $ch.channel_name; Url = $url }
  } else {
    Write-Host "  - $($ch.channel_name) (cozulemedi)" -ForegroundColor Yellow
  }
  Start-Sleep -Milliseconds 250
}

$lines = @('#EXTM3U')
foreach($e in $entries){
  $n = $e.Name -replace '"',''
  $lines += "#EXTINF:-1 tvg-id=`"$n`" tvg-name=`"$n`" group-title=`"TurkSpor`",$n"
  $lines += $e.Url
}
[System.IO.File]::WriteAllLines((Join-Path (Get-Location) $outFile), $lines, (New-Object System.Text.UTF8Encoding($false)))
Write-Host "OK: $outFile ($($entries.Count) kanal)" -ForegroundColor Cyan

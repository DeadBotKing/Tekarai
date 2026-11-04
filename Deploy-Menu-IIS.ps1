# Run in elevated Windows PowerShell. Touches only the Tekarai IIS site.
& {
    $ErrorActionPreference = 'Stop'
    Import-Module WebAdministration
    $siteName = 'Tekarai'
    $source = 'C:\Users\Mitra\Desktop\Tekarai\frontend-web\dist'
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $release = "C:\inetpub\TekaraiReleases\$stamp"
    $records = 'C:\ProgramData\Tekarai\Deployment'

    if (-not (Test-Path "$source\index.html")) { throw 'Built index.html not found.' }
    $site = Get-Website -Name $siteName
    if (-not $site) { throw 'Tekarai site not found.' }
    if ($site.applicationPool -ne 'TekaraiPool') { throw 'Unexpected application pool. Stop and report.' }
    if (-not (Get-WebBinding -Name $siteName -Protocol https | Where-Object { $_.bindingInformation -eq '*:443:tekarai' })) {
        throw 'Expected HTTPS binding not found.'
    }
    if (-not (Get-WindowsFeature Web-Static-Content).Installed) {
        throw 'IIS Static Content feature is not installed. Stop and report.'
    }
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/readyz/' `
        -Headers @{'X-Forwarded-Proto'='https'} -UseBasicParsing -TimeoutSec 20
    if ($health.StatusCode -ne 200) { throw 'Backend readiness failed.' }

    & "$env:windir\System32\inetsrv\appcmd.exe" add backup "Before-Tekarai-Static-$stamp"
    if ($LASTEXITCODE -ne 0) { throw 'IIS backup failed.' }
    New-Item -ItemType Directory -Path $records -Force | Out-Null
    $previous = @{ Site=$siteName; PhysicalPath=[string]$site.physicalPath; State=[string]$site.state; Release=$release }
    $previous | ConvertTo-Json | Set-Content "$records\Previous-$stamp.json" -Encoding UTF8
    New-Item -ItemType Directory -Path $release | Out-Null
    & robocopy.exe $source $release /E /XF *.map .env *.sqlite3 /R:1 /W:1 /NFL /NDL /NJH /NJS
    if ($LASTEXITCODE -gt 7) { throw 'Copy of frontend release failed.' }

    @'
<?xml version="1.0" encoding="utf-8"?>
<configuration>
  <system.webServer>
    <defaultDocument>
      <files><clear /><add value="index.html" /></files>
    </defaultDocument>
    <directoryBrowse enabled="false" />
    <staticContent>
      <remove fileExtension=".webmanifest" />
      <mimeMap fileExtension=".webmanifest" mimeType="application/manifest+json" />
      <remove fileExtension=".woff2" />
      <mimeMap fileExtension=".woff2" mimeType="font/woff2" />
      <remove fileExtension=".woff" />
      <mimeMap fileExtension=".woff" mimeType="font/woff" />
      <clientCache cacheControlMode="DisableCache" />
    </staticContent>
    <rewrite>
      <rules>
        <clear />
        <rule name="Tekarai HTTPS" stopProcessing="true">
          <match url="(.*)" />
          <conditions><add input="{HTTPS}" pattern="^OFF$" ignoreCase="true" /></conditions>
          <action type="Redirect" url="https://tekarai/{R:1}" redirectType="Found" appendQueryString="true" />
        </rule>
        <rule name="Tekarai API" stopProcessing="true">
          <match url="^(api(?:/.*)?|healthz/?|readyz/?)$" />
          <serverVariables><set name="HTTP_X_FORWARDED_PROTO" value="https" /></serverVariables>
          <action type="Rewrite" url="http://127.0.0.1:8000/{R:0}" appendQueryString="true" />
        </rule>
        <rule name="Tekarai SPA" stopProcessing="true">
          <match url=".*" />
          <conditions logicalGrouping="MatchAll">
            <add input="{REQUEST_FILENAME}" matchType="IsFile" negate="true" />
            <add input="{REQUEST_FILENAME}" matchType="IsDirectory" negate="true" />
            <add input="{URL}" pattern="^/(api|healthz|readyz|assets|icons|ws)(/|$)" negate="true" />
            <add input="{URL}" pattern="\.[^/]+$" negate="true" />
          </conditions>
          <action type="Rewrite" url="index.html" />
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
'@ | Set-Content "$release\web.config" -Encoding UTF8

    & icacls.exe $release /grant 'IIS AppPool\TekaraiPool:(OI)(CI)(RX)'
    if ($LASTEXITCODE -ne 0) { throw 'IIS release read permission failed.' }

    $allowed = Get-WebConfiguration -PSPath 'MACHINE/WEBROOT/APPHOST' -Location $siteName `
        -Filter 'system.webServer/rewrite/allowedServerVariables/add' |
        Where-Object { $_.name -eq 'HTTP_X_FORWARDED_PROTO' }
    if (-not $allowed) {
        Add-WebConfigurationProperty -PSPath 'MACHINE/WEBROOT/APPHOST' -Location $siteName `
            -Filter 'system.webServer/rewrite/allowedServerVariables' -Name '.' `
            -Value @{name='HTTP_X_FORWARDED_PROTO'}
    }

    try {
        Set-ItemProperty "IIS:\Sites\$siteName" -Name physicalPath -Value $release -ErrorAction Stop
        Start-Website -Name $siteName -ErrorAction Stop
        Write-Host 'IIS_RELEASE_ACTIVATED'
        Write-Host "FRONTEND: $release"
        Write-Host 'BACKEND: 127.0.0.1:8000'
        Write-Host 'SITE: https://tekarai'
        Write-Host "ROLLBACK_RECORD: $records\Previous-$stamp.json"
        Write-Host 'Other IIS sites and bindings were not changed. Browser testing is required.'
    } catch {
        Set-ItemProperty "IIS:\Sites\$siteName" -Name physicalPath -Value $previous.PhysicalPath
        if ($previous.State -eq 'Stopped') { Stop-Website -Name $siteName }
        throw
    }
}

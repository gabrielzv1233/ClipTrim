param(
    [string]$OutputPath = "licenses/Qt-6.11.2-THIRD-PARTY-NOTICES.txt"
)

$ErrorActionPreference = "Stop"
$indexUri = "https://doc.qt.io/qt-6/licenses-used-in-qt.html"
$baseUri = "https://doc.qt.io/qt-6/"
$indexHtml = (Invoke-WebRequest -UseBasicParsing -Uri $indexUri).Content
if ($indexHtml -notmatch 'Qt 6\.11\.2') {
    throw "Qt attribution index is no longer the expected 6.11.2 inventory."
}

$linkPattern = 'href="((?:qtcore|qtgui|qtmultimedia|qtnetwork)-attribution-[^"]+\.html)"'
$links = [System.Collections.Generic.List[string]]::new()
foreach ($match in [regex]::Matches($indexHtml, $linkPattern)) {
    $link = $match.Groups[1].Value
    if ($link.StartsWith("qtmultimedia-attribution-ffmpeg")) {
        continue
    }
    if (-not $links.Contains($link)) {
        $links.Add($link)
    }
}

if ($links.Count -ne 52) {
    throw "Expected 52 selected Qt attribution entries, found $($links.Count)."
}
$linkBytes = [System.Text.Encoding]::UTF8.GetBytes(($links -join "`n"))
$linkHash = [Convert]::ToHexString([System.Security.Cryptography.SHA256]::HashData($linkBytes))
if ($linkHash -ne "A7D6FD21E2B4ABE2CBB4FD7BF1C06B78B129CC31D0A834C3627AF8B8672EABBB") {
    throw "Qt attribution link inventory changed: $linkHash"
}

$output = [System.Collections.Generic.List[string]]::new()
$output.Add("Qt 6.11.2 third-party attribution statements")
$output.Add("================================================")
$output.Add("")
$output.Add("Generated from the official Qt 6.11 attribution pages for Qt Core, GUI,")
$output.Add("Network, and Multimedia. This is a conservative module-level set: it may")
$output.Add("include statements for platform-specific code not present in the Windows")
$output.Add("wheel. Qt Multimedia's FFmpeg entries are intentionally omitted because")
$output.Add("ClipTrim's build excludes that backend and its shared libraries.")
$output.Add("")
$output.Add("Index: $indexUri")
$output.Add("")

foreach ($link in $links) {
    $uri = $baseUri + $link
    $html = (Invoke-WebRequest -UseBasicParsing -Uri $uri).Content
    $contentMatch = [regex]::Match(
        $html,
        '(?s)<h1 class="title">(?<body>.*?)<!-- @@@[^>]+ -->'
    )
    if (-not $contentMatch.Success) {
        throw "Could not extract the attribution body from $uri"
    }

    $text = $contentMatch.Groups["body"].Value
    $text = [regex]::Replace($text, '(?is)<(script|style)[^>]*>.*?</\1>', '')
    $text = [regex]::Replace($text, '(?i)<br\s*/?>', "`n")
    $text = [regex]::Replace($text, '(?i)</(p|li|h1|h2|h3|h4|pre|div|tr|table)>', "`n")
    $text = [regex]::Replace($text, '<[^>]+>', '')
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    $text = $text.Replace([char]0x00a0, ' ')
    $text = [regex]::Replace($text, '(?m)[ \t]+$', '')
    $text = [regex]::Replace($text, '(\r?\n){3,}', "`n`n")
    $text = $text.Trim()

    $output.Add("------------------------------------------------------------------------")
    $output.Add("Source: $uri")
    $output.Add("------------------------------------------------------------------------")
    $output.Add($text)
    $output.Add("")
}

$resolvedOutput = [System.IO.Path]::GetFullPath($OutputPath)
[System.IO.Directory]::CreateDirectory([System.IO.Path]::GetDirectoryName($resolvedOutput)) | Out-Null
[System.IO.File]::WriteAllText(
    $resolvedOutput,
    (($output -join "`n").TrimEnd() + "`n"),
    [System.Text.UTF8Encoding]::new($false)
)
$outputHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedOutput).Hash
if ($outputHash -ne "4B6C0F2FF57A58560B676358010B7CB3B7417A62DD9E1F130C74E6819BBF1BD7") {
    throw "Generated Qt attribution bundle changed: $outputHash"
}
Write-Host "Wrote $($links.Count) Qt attribution statements to $resolvedOutput"

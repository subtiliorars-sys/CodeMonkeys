# generate_icons.ps1 — Generate PNG icons for the CodeMonkeys extension
Add-Type -AssemblyName System.Drawing

$iconDir = "C:\Users\subti\repos\CodeMonkeys\static\extension\icons"

$bg = [System.Drawing.Color]::FromArgb(5, 5, 7)
$gold = [System.Drawing.Color]::FromArgb(212, 175, 55)
$goldBright = [System.Drawing.Color]::FromArgb(240, 199, 94)

function New-Icon($size) {
    $n = [int]$size
    $bmp = New-Object System.Drawing.Bitmap($n, $n)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.SmoothingMode = 'HighQuality'
    $g.TextRenderingHint = 'AntiAlias'
    $g.Clear($bg)

    $pad = [int]([Math]::Max(1, $n * 0.08))
    $rx = $pad
    $ry = $pad
    $rw = $n - 2 * $pad
    $rh = $n - 2 * $pad

    if ($n -ge 48) {
        # Outer gold ellipse
        $brush1 = New-Object System.Drawing.SolidBrush($gold)
        $g.FillEllipse($brush1, $rx, $ry, $rw, $rh)
        $brush1.Dispose()

        # Inner dark ellipse
        $ip = [int]($n * 0.12)
        $brush2 = New-Object System.Drawing.SolidBrush($bg)
        $g.FillEllipse($brush2, $rx + $ip, $ry + $ip, $rw - 2*$ip, $rh - 2*$ip)
        $brush2.Dispose()

        # "CM" text
        $fs = [float]($n * 0.38)
        $font = New-Object System.Drawing.Font("Consolas", $fs, [System.Drawing.FontStyle]::Bold)
        $brushText = New-Object System.Drawing.SolidBrush($goldBright)
        $sf = New-Object System.Drawing.StringFormat
        $sf.Alignment = 'Center'
        $sf.LineAlignment = 'Center'
        $g.DrawString("CM", $font, $brushText, [System.Drawing.RectangleF]::new(0,0,$n,$n), $sf)
        $font.Dispose()
        $brushText.Dispose()
        $sf.Dispose()
    } else {
        # 16px: filled gold circle
        $brush = New-Object System.Drawing.SolidBrush($gold)
        $g.FillEllipse($brush, $rx, $ry, $rw, $rh)
        $brush.Dispose()
    }

    $g.Dispose()
    $outPath = Join-Path $iconDir "icon-$n.png"
    $bmp.Save($outPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $bmp.Dispose()
    Write-Host "Created $outPath ($($n)x$($n))"
}

New-Icon 16
New-Icon 48
New-Icon 128

Write-Host "All icons generated."


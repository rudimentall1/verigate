# Verigate CMC live demo runner for screen recording.
# The API key is entered locally and is never written to the repository.
$secure = Read-Host "CMC API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:CMC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    Set-Location (Join-Path $PSScriptRoot "..\..")
    python .\demo_cmc_rwa_video.py
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:CMC_API_KEY -ErrorAction SilentlyContinue
}

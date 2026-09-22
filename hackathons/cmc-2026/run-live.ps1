# Verigate CMC live demo runner.
# The key is entered locally and never written to the repository.
$secure = Read-Host "CMC API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $env:CMC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr)
    Set-Location (Join-Path $PSScriptRoot "..\..")
    python .\demo_cmc_rwa.py --symbol GOLD --amount-usd 500
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr)
    Remove-Item Env:CMC_API_KEY -ErrorAction SilentlyContinue
}

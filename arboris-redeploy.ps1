# Arboris: git pull + Cloud Run redeploy
# Run in PowerShell (VS Code integrated terminal), NOT Git Bash and NOT the
# standalone Cloud SDK cmd window. If PowerShell blocks scripts, run this once
# first:  Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
#
# What it does:
#   1. Pulls latest main (currently b60d77f) into your local clone
#   2. Builds the image with Cloud Build (NOT --source ., which hit a 403 before)
#   3. Deploys to Cloud Run with NO env flags, so the existing env list,
#      secret (GREENSEARCH_API_KEY=openrouterkey:latest), and CORS allowlist
#      are preserved. Never use --set-env-vars here: it replaces the whole list.
#   4. Checks /api/health on the live URL
#
# If any step fails, the script stops. Do not re-run the deploy step blindly;
# check the error first.

$ErrorActionPreference = "Stop"

$RepoPath = "$env:USERPROFILE\Desktop\Work\greensearch\greensearch-1"
$Project  = "arboris-513009"
$Region   = "us-central1"
$Image    = "us-central1-docker.pkg.dev/arboris-513009/arboris/arboris:latest"
$LiveUrl  = "https://arboris-1037861813679.us-central1.run.app"

if (-not (Test-Path "$RepoPath\Dockerfile")) {
    Write-Error "Repo root not found at $RepoPath (no Dockerfile there). Edit `$RepoPath at the top of this script to point at your greensearch-1 clone, then re-run."
}

Set-Location $RepoPath
Write-Host "== 1. Pulling latest main =="
git pull
git log -1 --oneline

Write-Host "== 2. Setting GCP project =="
gcloud config set project $Project

Write-Host "== 3. Building image with Cloud Build =="
gcloud builds submit --tag $Image --region $Region .

Write-Host "== 4. Deploying to Cloud Run (no env flags, on purpose) =="
gcloud run deploy arboris --image $Image --region $Region --allow-unauthenticated

Write-Host "== 5. Health check =="
curl.exe -s "$LiveUrl/api/health"
Write-Host ""
Write-Host "Done. Open $LiveUrl in a browser and check: Live starts on, hero input visible on load, first send switches to chatting mode, and live answers show the energy/task tags."

<#
.SYNOPSIS
  One-time bootstrap of MatchMind on Azure. After this, every push to main deploys through GitHub Actions.

.DESCRIPTION
  1. registers the resource providers;
  2. deploys infra/acr.bicep (registry);
  3. deploys infra/main.bicep in bootstrap mode (placeholder image) so the identities, roles, Key Vault,
     storage, environment, jobs, Static Web App, Foundry project connections, alerts and budget exist;
  4. uploads the local data/ folder (matches, warmed agent cache, TTS cache) to the Azure Files share;
  5. stores the three ids GitHub Actions needs as repository secrets (gh CLI) and triggers the workflow,
     which builds the real image and finishes the deployment.
  Re-running is safe: every step is idempotent.

.PARAMETER SpeechKey
  Azure AI Speech key (the Foundry resource's key works). Stored in Key Vault as speech-key; never printed.
.PARAMETER AlertEmail
  Address for the availability/failed-requests/restart alerts and the USD 30 budget. Empty disables both.
#>
param(
  [string] $ResourceGroup = 'rg-matchmind',
  [string] $Location = 'eastus2',
  [string] $FoundryAccount = 'matchmind-foundry',
  [string] $GithubRepo = 'agustin-perez-data/matchmind',
  [string] $SpeechKey = '',
  [string] $AlertEmail = '',
  [int] $MinReplicas = 1,
  [switch] $SkipDataUpload,
  [switch] $SkipGithub
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$env:MSYS_NO_PATHCONV = '1'

function Step($msg) { Write-Host "`n== $msg" -ForegroundColor Cyan }

Step 'Resource providers'
foreach ($ns in 'Microsoft.App', 'Microsoft.ContainerRegistry', 'Microsoft.KeyVault', 'Microsoft.OperationalInsights',
                'Microsoft.Storage', 'Microsoft.Web', 'Microsoft.EventGrid', 'Microsoft.Insights', 'Microsoft.ManagedIdentity',
                'Microsoft.Consumption', 'Microsoft.LoadTestService') {
  $state = az provider show -n $ns --query registrationState -o tsv 2>$null
  if ($state -ne 'Registered') { az provider register -n $ns -o none; Write-Host "  registering $ns" } else { Write-Host "  $ns ok" }
}

Step "Resource group $ResourceGroup ($Location)"
az group create -n $ResourceGroup -l $Location --tags project=matchmind -o none

Step 'Container registry (infra/acr.bicep)'
$acr = az deployment group create -g $ResourceGroup -n acr -f "$root/infra/acr.bicep" --query properties.outputs -o json | ConvertFrom-Json
$acrName = $acr.name.value
Write-Host "  $($acr.loginServer.value)"

Step 'Platform in bootstrap mode (infra/main.bicep with a placeholder image)'
$params = @("acrName=$acrName", "bootstrap=true", "minReplicas=$MinReplicas", "foundryAccountName=$FoundryAccount", "githubRepo=$GithubRepo")
if ($AlertEmail) { $params += "alertEmail=$AlertEmail" }
if ($SpeechKey) { $params += "speechKey=$SpeechKey" }
$out = az deployment group create -g $ResourceGroup -n bootstrap -f "$root/infra/main.bicep" -p @params --query properties.outputs -o json | ConvertFrom-Json
if (-not $out) { throw 'main.bicep bootstrap deployment failed' }
$storage = $out.storageAccount.value
Write-Host "  API (placeholder) $($out.apiUrl.value)"
Write-Host "  SWA https://$($out.swaHostname.value)"
Write-Host "  deploy identity clientId $($out.deployIdentityClientId.value)"

if (-not $SkipDataUpload) {
  Step "Data upload to the share matchmind-data on $storage (matches, agent cache, TTS cache)"
  $key = az storage account keys list -n $storage -g $ResourceGroup --query '[0].value' -o tsv
  az storage file upload-batch --account-name $storage --account-key $key --destination matchmind-data --source "$root/data" --no-progress -o none
  $n = az storage file list --account-name $storage --account-key $key --share-name matchmind-data --query "length(@)" -o tsv
  Write-Host "  $n entries at the share root"
}

if (-not $SkipGithub) {
  Step 'GitHub Actions: OIDC secrets and first run'
  $sub = az account show --query id -o tsv
  $tenant = az account show --query tenantId -o tsv
  gh secret set AZURE_CLIENT_ID --repo $GithubRepo --body $out.deployIdentityClientId.value
  gh secret set AZURE_TENANT_ID --repo $GithubRepo --body $tenant
  gh secret set AZURE_SUBSCRIPTION_ID --repo $GithubRepo --body $sub
  if ($AlertEmail) { gh variable set ALERT_EMAIL --repo $GithubRepo --body $AlertEmail }
  gh variable set MIN_REPLICAS --repo $GithubRepo --body "$MinReplicas"
  Write-Host '  secrets set; triggering the deploy workflow (it builds the image and finishes the rollout)'
  gh workflow run deploy.yml --repo $GithubRepo
  Write-Host "  follow it with: gh run watch --repo $GithubRepo"
}

Step 'Done'
Write-Host "Next: once the workflow is green, open https://$($out.swaHostname.value) and $($out.apiUrl.value)/health"

// Container registry for the MatchMind API image. Deployed once by infra/deploy.ps1, before main.bicep,
// because the Container App needs an image that exists. Admin user off: GitHub Actions pushes with a
// federated identity (AcrPush) and the Container App pulls with its user-assigned identity (AcrPull).
targetScope = 'resourceGroup'

@description('Region of the registry')
param location string = resourceGroup().location

@description('Registry name (globally unique, alphanumeric)')
param name string = 'acrmatchmind${uniqueString(resourceGroup().id)}'

resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' = {
  name: name
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    publicNetworkAccess: 'Enabled'
  }
  tags: { project: 'matchmind' }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
output id string = acr.id

// MatchMind on Azure: everything except the registry (infra/acr.bicep, deployed first) and the Foundry
// account with its model deployments (created by hand before the hackathon; referenced as existing).
//
// Idempotent: GitHub Actions runs this on every push to main with a new image tag; infra/deploy.ps1 runs it
// once first with the Speech key. What each resource does for the product is in infra/README.md.
targetScope = 'resourceGroup'

@description('Region for everything (the Foundry account lives here too)')
param location string = resourceGroup().location

@description('Existing Foundry (AIServices) account with the gpt-4o and gpt-4.1-mini deployments')
param foundryAccountName string = 'matchmind-foundry'

@description('Foundry project: the control plane for agents, traces, evaluations and hosted agents')
param foundryProjectName string = 'matchmind'

@description('Container registry created by infra/acr.bicep')
param acrName string

@description('Full image reference, e.g. acrmatchmindxxxx.azurecr.io/matchmind-api:<sha>; ignored when bootstrap is true')
param image string = ''

@description('First deploy before any image exists in the registry: a public placeholder serves port 80 with no probes, so the identities, roles and the rest come up and the pipeline can build the real image')
param bootstrap bool = false

@secure()
@description('Azure AI Speech key: stored in Key Vault as speech-key when given; omit on later deploys')
param speechKey string = ''

@description('Minimum API replicas (1 while judging, 0 to park the app)')
@minValue(0)
@maxValue(2)
param minReplicas int = 1

@description('E-mail for alerts and the budget; empty disables the action group and the budget')
param alertEmail string = ''

@description('GitHub repository allowed to deploy through OIDC, in the form GitHub presents in the OIDC subject since 2026: owner@ownerId/repo@repoId')
param githubRepo string = 'agustin-perez-data@115547741/matchmind@1427551358'

@description('First day of the month the budget starts counting from')
param budgetStart string = '2026-10-01'

@description('Monthly budget in USD')
param budgetAmount int = 30

var tags = { project: 'matchmind', purpose: 'hackathon-inside-the-game' }
var appImage = bootstrap ? 'mcr.microsoft.com/k8se/quickstart:latest' : image
var appPort = bootstrap ? 80 : 8000
var apiProbes = bootstrap ? [] : [
  { type: 'Startup', httpGet: { path: '/health', port: 8000 }, initialDelaySeconds: 5, periodSeconds: 5, failureThreshold: 12, timeoutSeconds: 3 }
  { type: 'Readiness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 10, failureThreshold: 2, timeoutSeconds: 3 }
  { type: 'Liveness', httpGet: { path: '/health', port: 8000 }, periodSeconds: 30, failureThreshold: 3, timeoutSeconds: 3 }
]
var suffix = uniqueString(resourceGroup().id)
var roles = {
  foundryUser: '53ca6127-db72-4b80-b1b0-d745d6d5456d'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  acrPull: '7f951dda-4ed3-4680-a7ca-43fe172d538d'
  acrPush: '8311e382-0749-4cb8-b61a-304f252e45ec'
  eventGridDataSender: 'd5a91429-5739-47e2-a06b-3470a27159e7'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'
  storageQueueDataMessageSender: 'c6a89b2d-59bc-44d0-9896-0f6e12d7b80a'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  rbacAdministrator: 'f58310d9-a9f6-439a-9e8d-f62e7b41a168'
}

// ------------------------------------------------------------------ existing
resource foundry 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = { name: foundryAccountName }
resource acr 'Microsoft.ContainerRegistry/registries@2025-04-01' existing = { name: acrName }

// ------------------------------------------------------------------ identities
resource apiIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-matchmind-api'
  location: location
  tags: tags
}

resource deployIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = {
  name: 'id-github-deploy'
  location: location
  tags: tags
}

resource deployFederation 'Microsoft.ManagedIdentity/userAssignedIdentities/federatedIdentityCredentials@2024-11-30' = {
  parent: deployIdentity
  name: 'github-main'
  properties: {
    issuer: 'https://token.actions.githubusercontent.com'
    subject: 'repo:${githubRepo}:ref:refs/heads/main'
    audiences: ['api://AzureADTokenExchange']
  }
}

// ------------------------------------------------------------------ observability
resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-matchmind'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
    workspaceCapping: { dailyQuotaGb: 1 }
    features: { enableLogAccessUsingOnlyResourcePermissions: true }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-matchmind'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logs.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: 30
  }
}

// ------------------------------------------------------------------ Foundry project + its Application Insights connection
resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundry
  name: foundryProjectName
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    displayName: 'MatchMind'
    description: 'Synthetic-league match intelligence: Analyst, Narrator, Director, Coach and Judge agents, graded in public'
  }
}

// Foundry tracing reads the Application Insights connected at the account level; isSharedToAll surfaces it in
// every project of the account (a project-level copy with the same name is rejected by the service).
resource foundryAppInsights 'Microsoft.CognitiveServices/accounts/connections@2025-04-01-preview' = {
  parent: foundry
  name: 'appinsights'
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: { key: appInsights.properties.ConnectionString }
    metadata: { ApiType: 'Azure', ResourceId: appInsights.id }
  }
}

// ------------------------------------------------------------------ Key Vault (only the Speech key lives here)
resource keyVault 'Microsoft.KeyVault/vaults@2024-11-01' = {
  name: 'kv-mm-${suffix}' // 3-24 chars
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
  }
}

resource speechSecret 'Microsoft.KeyVault/vaults/secrets@2024-11-01' = if (!empty(speechKey)) {
  parent: keyVault
  name: 'speech-key'
  properties: { value: speechKey, contentType: 'Azure AI Speech key' }
}

// ------------------------------------------------------------------ Storage: data share, event queue, report + eval blobs
resource storage 'Microsoft.Storage/storageAccounts@2024-01-01' = {
  name: 'stmatchmind${suffix}'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    accessTier: 'Hot'
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2024-01-01' = {
  parent: storage
  name: 'default'
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2024-01-01' = {
  parent: fileService
  name: 'matchmind-data'
  properties: { shareQuota: 5, accessTier: 'TransactionOptimized' }
}

resource queueService 'Microsoft.Storage/storageAccounts/queueServices@2024-01-01' = {
  parent: storage
  name: 'default'
}

resource eventsQueue 'Microsoft.Storage/storageAccounts/queueServices/queues@2024-01-01' = {
  parent: queueService
  name: 'matchmind-events'
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2024-01-01' = {
  parent: storage
  name: 'default'
}

resource reportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: 'reports'
}

resource evalContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2024-01-01' = {
  parent: blobService
  name: 'eval'
}

// ------------------------------------------------------------------ Event Grid: the product publishes, a job consumes
resource topic 'Microsoft.EventGrid/topics@2025-02-15' = {
  name: 'evgt-matchmind'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {
    inputSchema: 'CloudEventSchemaV1_0'
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource topicToQueue 'Microsoft.EventGrid/topics/eventSubscriptions@2025-02-15' = {
  parent: topic
  name: 'to-matchmind-events-queue'
  properties: {
    eventDeliverySchema: 'CloudEventSchemaV1_0'
    deliveryWithResourceIdentity: {
      identity: { type: 'SystemAssigned' }
      destination: {
        endpointType: 'StorageQueue'
        properties: { resourceId: storage.id, queueName: eventsQueue.name, queueMessageTimeToLiveInSeconds: 86400 }
      }
    }
    filter: { includedEventTypes: ['matchmind.risk.window_opened', 'matchmind.match.ended'] }
    retryPolicy: { maxDeliveryAttempts: 10, eventTimeToLiveInMinutes: 60 }
  }
  dependsOn: [topicQueueSender]
}

// ------------------------------------------------------------------ Container Apps environment + Azure Files mount
resource env 'Microsoft.App/managedEnvironments@2025-01-01' = {
  name: 'cae-matchmind'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: { customerId: logs.properties.customerId, sharedKey: logs.listKeys().primarySharedKey }
    }
    // Consumption-only environment (no workload profiles): everything here fits it (jobs, sticky sessions, the
    // Azure Files mount, KEDA rules) and it provisions in minutes; the workload-profile flavour sat in
    // "Waiting" for an hour on this subscription.
  }
}

// Azure Files by account key: the managed-identity SMB mount is still preview (see infra/README.md); the key
// never leaves the environment resource and is not an output.
resource dataMount 'Microsoft.App/managedEnvironments/storages@2025-01-01' = {
  parent: env
  name: 'matchmind-data'
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: dataShare.name
      accessMode: 'ReadWrite'
    }
  }
}

var apiEnv = [
  { name: 'AZURE_CLIENT_ID', value: apiIdentity.properties.clientId }
  { name: 'FOUNDRY_PROJECT_ENDPOINT', value: 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}' }
  { name: 'AZURE_OPENAI_ENDPOINT', value: foundry.properties.endpoint }
  { name: 'MATCHMIND_AUTH', value: 'identity' }
  { name: 'AZURE_OPENAI_DEPLOYMENT_FAST', value: 'gpt-4.1-mini' }
  { name: 'AZURE_OPENAI_DEPLOYMENT_SMART', value: 'gpt-4o' }
  { name: 'AZURE_SPEECH_REGION', value: location }
  { name: 'AZURE_SPEECH_KEY', secretRef: 'speech-key' }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
  { name: 'OTEL_SERVICE_NAME', value: 'matchmind-api' }
  { name: 'MATCHMIND_DATA_DIR', value: '/data' }
  { name: 'MATCHMIND_CACHE', value: '1' }
  { name: 'MATCHMIND_EVENTGRID_ENDPOINT', value: topic.properties.endpoint }
  { name: 'MATCHMIND_STORAGE_ACCOUNT', value: storage.name }
  { name: 'MATCHMIND_GUARDRAILS', value: '1' }
  { name: 'MATCHMIND_JUDGE', value: 'foundry' }
]

var jobEnv = filter(apiEnv, e => e.name != 'AZURE_SPEECH_KEY')

resource api 'Microsoft.App/containerApps@2025-01-01' = {
  name: 'matchmind-api'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${apiIdentity.id}': {} } }
  properties: {
    environmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      maxInactiveRevisions: 5
      ingress: {
        external: true
        targetPort: appPort
        transport: 'auto'
        allowInsecure: false
        stickySessions: { affinity: 'sticky' }
        traffic: [{ latestRevision: true, weight: 100 }]
      }
      registries: [{ server: acr.properties.loginServer, identity: apiIdentity.id }]
      secrets: [
        { name: 'speech-key', keyVaultUrl: '${keyVault.properties.vaultUri}secrets/speech-key', identity: apiIdentity.id }
      ]
    }
    template: {
      terminationGracePeriodSeconds: 120
      containers: [
        {
          name: 'api'
          image: appImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: apiEnv
          volumeMounts: [{ volumeName: 'data', mountPath: '/data' }]
          probes: apiProbes
        }
      ]
      volumes: [{ name: 'data', storageType: 'AzureFile', storageName: dataMount.name }]
      scale: {
        minReplicas: minReplicas
        maxReplicas: 2
        cooldownPeriod: 1800
        rules: [{ name: 'viewers', http: { metadata: { concurrentRequests: '20' } } }]
      }
    }
  }
  dependsOn: [apiAcrPull, apiKeyVault, speechSecret]
}

// ------------------------------------------------------------------ jobs: warm after deploy, report on event, nightly
var jobCommon = {
  environmentId: env.id
  registries: [{ server: acr.properties.loginServer, identity: apiIdentity.id }]
}

resource warmJob 'Microsoft.App/jobs@2025-01-01' = {
  name: 'matchmind-warm'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${apiIdentity.id}': {} } }
  properties: {
    environmentId: jobCommon.environmentId
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 2400
      replicaRetryLimit: 1
      manualTriggerConfig: { parallelism: 1, replicaCompletionCount: 1 }
      registries: jobCommon.registries
    }
    template: {
      containers: [
        {
          name: 'warm'
          image: appImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: jobEnv
          command: ['python', '-m', 'matchmind.agents.warm_cache']
          args: ['--base', 'https://${api.properties.configuration.ingress.fqdn}', '--match', 'THU-NBF-40', '--speed', '40']
        }
      ]
    }
  }
}

resource reportJob 'Microsoft.App/jobs@2025-01-01' = {
  name: 'matchmind-report'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${apiIdentity.id}': {} } }
  properties: {
    environmentId: jobCommon.environmentId
    configuration: {
      triggerType: 'Event'
      replicaTimeout: 300
      replicaRetryLimit: 1
      registries: jobCommon.registries
      eventTriggerConfig: {
        parallelism: 1
        replicaCompletionCount: 1
        scale: {
          minExecutions: 0
          maxExecutions: 5
          pollingInterval: 30
          rules: [
            {
              name: 'queue'
              type: 'azure-queue'
              metadata: { queueName: eventsQueue.name, queueLength: '1', accountName: storage.name }
              identity: apiIdentity.id
            }
          ]
        }
      }
    }
    template: {
      containers: [
        {
          name: 'report'
          image: appImage
          resources: { cpu: json('0.25'), memory: '0.5Gi' }
          env: jobEnv
          command: ['python', '-m', 'matchmind.reports.consume']
        }
      ]
    }
  }
  dependsOn: [apiStorageQueue, apiStorageBlob]
}

resource nightlyJob 'Microsoft.App/jobs@2025-01-01' = {
  name: 'matchmind-nightly'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${apiIdentity.id}': {} } }
  properties: {
    environmentId: jobCommon.environmentId
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 2400
      replicaRetryLimit: 1
      registries: jobCommon.registries
      scheduleTriggerConfig: { cronExpression: '0 4 * * *', parallelism: 1, replicaCompletionCount: 1 }
    }
    template: {
      containers: [
        {
          name: 'nightly'
          image: appImage
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: jobEnv
          volumeMounts: [{ volumeName: 'data', mountPath: '/data' }]
          command: ['python', '-m', 'matchmind.jobs.nightly']
          args: ['--base', 'https://${api.properties.configuration.ingress.fqdn}']
        }
      ]
      volumes: [{ name: 'data', storageType: 'AzureFile', storageName: dataMount.name }]
    }
  }
  dependsOn: [apiStorageBlob]
}

// ------------------------------------------------------------------ Static Web App (Free): the React frontend
resource swa 'Microsoft.Web/staticSites@2024-04-01' = {
  name: 'swa-matchmind'
  location: location
  tags: tags
  sku: { name: 'Free', tier: 'Free' }
  properties: {}
}

// ------------------------------------------------------------------ role assignments
resource apiFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, apiIdentity.id, roles.foundryUser)
  scope: project
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, apiIdentity.id, roles.cognitiveServicesOpenAIUser)
  scope: foundry
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

// Content Safety (the groundedness guardrail) on the same resource: data-plane access for the API identity
resource apiCognitiveUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, apiIdentity.id, roles.cognitiveServicesUser)
  scope: foundry
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesUser), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiKeyVault 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, apiIdentity.id, roles.keyVaultSecretsUser)
  scope: keyVault
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.keyVaultSecretsUser), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiAcrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, apiIdentity.id, roles.acrPull)
  scope: acr
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPull), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiEventGrid 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(topic.id, apiIdentity.id, roles.eventGridDataSender)
  scope: topic
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.eventGridDataSender), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiStorageQueue 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, apiIdentity.id, roles.storageQueueDataContributor)
  scope: storage
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataContributor), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource apiStorageBlob 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, apiIdentity.id, roles.storageBlobDataContributor)
  scope: storage
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor), principalId: apiIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource topicQueueSender 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, topic.id, roles.storageQueueDataMessageSender)
  scope: storage
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageQueueDataMessageSender), principalId: topic.identity.principalId, principalType: 'ServicePrincipal' }
}

resource deployContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deployIdentity.id, roles.contributor)
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.contributor), principalId: deployIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

// the pipeline re-applies this template, which carries role assignments: it needs to administer RBAC in the group
resource deployRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resourceGroup().id, deployIdentity.id, roles.rbacAdministrator)
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.rbacAdministrator), principalId: deployIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

resource deployAcrPush 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, deployIdentity.id, roles.acrPush)
  scope: acr
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.acrPush), principalId: deployIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

// registering agents and running evaluations from the pipeline goes through the project
resource deployFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, deployIdentity.id, roles.foundryUser)
  scope: project
  properties: { roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.foundryUser), principalId: deployIdentity.properties.principalId, principalType: 'ServicePrincipal' }
}

// ------------------------------------------------------------------ availability test, alerts, workbook, budget
resource webTest 'Microsoft.Insights/webtests@2022-06-15' = {
  name: 'matchmind-health'
  location: location
  kind: 'standard'
  tags: union(tags, { 'hidden-link:${appInsights.id}': 'Resource' })
  properties: {
    Name: 'matchmind-health'
    SyntheticMonitorId: 'matchmind-health'
    Kind: 'standard'
    Enabled: true
    Frequency: 300
    Timeout: 30
    RetryEnabled: true
    Locations: [
      { Id: 'us-va-ash-azr' }
      { Id: 'us-il-ch1-azr' }
      { Id: 'emea-nl-ams-azr' }
    ]
    Request: { RequestUrl: 'https://${api.properties.configuration.ingress.fqdn}/health', HttpVerb: 'GET', ParseDependentRequests: false }
    ValidationRules: { ExpectedHttpStatusCode: 200, SSLCheck: true, SSLCertRemainingLifetimeCheck: 7, ContentValidation: { ContentMatch: '"ready":true', IgnoreCase: false, PassIfTextFound: true } }
  }
}

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(alertEmail)) {
  name: 'ag-matchmind'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: 'matchmind'
    enabled: true
    emailReceivers: [{ name: 'owner', emailAddress: alertEmail, useCommonAlertSchema: true }]
  }
}

var actions = empty(alertEmail) ? [] : [{ actionGroupId: actionGroup.id }]

resource availabilityAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'matchmind-availability'
  location: 'global'
  tags: tags
  properties: {
    description: 'The /health probe failed from 2 of 3 locations over 15 minutes (SLO: 99.5 % of 5-minute probes)'
    severity: 1
    enabled: true
    scopes: [webTest.id, appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: { 'odata.type': 'Microsoft.Azure.Monitor.WebtestLocationAvailabilityCriteria', webTestId: webTest.id, componentId: appInsights.id, failedLocationCount: 2 }
    actions: actions
  }
}

resource failedRequestsAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'matchmind-failed-requests'
  location: 'global'
  tags: tags
  properties: {
    description: 'More than 20 failed requests in 5 minutes'
    severity: 2
    enabled: true
    scopes: [appInsights.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT5M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [{ criterionType: 'StaticThresholdCriterion', name: 'failed', metricName: 'requests/failed', metricNamespace: 'microsoft.insights/components', timeAggregation: 'Count', operator: 'GreaterThan', threshold: 20 }]
    }
    actions: actions
  }
}

resource restartsAlert 'Microsoft.Insights/metricAlerts@2018-03-01' = {
  name: 'matchmind-restarts'
  location: 'global'
  tags: tags
  properties: {
    description: 'A replica restarted (a crash or a failed liveness probe drops live viewers; they resume, but look)'
    severity: 2
    enabled: true
    scopes: [api.id]
    evaluationFrequency: 'PT5M'
    windowSize: 'PT15M'
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [{ criterionType: 'StaticThresholdCriterion', name: 'restarts', metricName: 'RestartCount', metricNamespace: 'Microsoft.App/containerApps', timeAggregation: 'Maximum', operator: 'GreaterThan', threshold: 0 }]
    }
    actions: actions
  }
}

var kql = {
  requests: 'requests | summarize requests = count() by resultCode, bin(timestamp, 5m) | render timechart'
  latency: 'customMetrics | where name == "matchmind.moment.latency_ms" | extend cache_hit = tostring(customDimensions.cache_hit) | summarize avg_ms = sum(valueSum) / sum(valueCount), max_ms = max(valueMax), moments = sum(valueCount) by cache_hit, bin(timestamp, 15m) | render timechart'
  cache: 'customMetrics | where name == "matchmind.cache.lookups" | extend hit = tostring(customDimensions.hit) | summarize lookups = sum(valueSum) by hit, bin(timestamp, 1h) | render columnchart'
  tokens: 'customMetrics | where name == "matchmind.tokens" | extend agent = tostring(customDimensions.agent), direction = tostring(customDimensions.direction) | summarize tokens = sum(valueSum) by agent, direction, bin(timestamp, 1h) | render columnchart'
  foundry: 'dependencies | where target has "ai.azure.com" or target has "openai.azure.com" or type has "foundry" | summarize calls = count(), failed = countif(success == false), p95_ms = percentile(duration, 95) by bin(timestamp, 15m) | render timechart'
  sessions: 'customMetrics | where name == "matchmind.sessions.active" | summarize viewers = max(valueMax) by bin(timestamp, 5m) | render timechart'
}

var workbookItems = [
  { type: 1, content: { json: '## MatchMind operations\nMoments explained per cache hit/miss, Foundry calls, tokens, viewers and request health. Metrics come from the API\'s OpenTelemetry meters (`matchmind.*`); agent spans are on the Foundry project\'s Traces page.' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.requests, size: 0, title: 'Requests by status code', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'timechart' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.latency, size: 0, title: 'Time to explain a moment: cache hit vs Foundry call (avg, max)', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'timechart' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.cache, size: 0, title: 'Agent cache lookups (hit / miss)', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'barchart' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.tokens, size: 0, title: 'Foundry tokens by agent and direction', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'barchart' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.foundry, size: 0, title: 'Foundry dependencies: calls, failures, p95', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'timechart' } }
  { type: 3, content: { version: 'KqlItem/1.0', query: kql.sessions, size: 0, title: 'Live viewer sessions', queryType: 0, resourceType: 'microsoft.insights/components', visualization: 'timechart' } }
]

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(resourceGroup().id, 'matchmind-ops')
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'MatchMind operations'
    category: 'workbook'
    sourceId: appInsights.id
    serializedData: string({ version: 'Notebook/1.0', items: workbookItems, isLocked: false, fallbackResourceIds: [appInsights.id] })
  }
}

resource budget 'Microsoft.Consumption/budgets@2024-08-01' = if (!empty(alertEmail)) {
  name: 'budget-matchmind'
  properties: {
    category: 'Cost'
    amount: budgetAmount
    timeGrain: 'Monthly'
    timePeriod: { startDate: budgetStart }
    notifications: {
      actual80: { enabled: true, operator: 'GreaterThan', threshold: 80, thresholdType: 'Actual', contactEmails: [alertEmail] }
      forecast100: { enabled: true, operator: 'GreaterThan', threshold: 100, thresholdType: 'Forecasted', contactEmails: [alertEmail] }
    }
  }
}

// ------------------------------------------------------------------ outputs (no secrets)
output apiFqdn string = api.properties.configuration.ingress.fqdn
output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output swaHostname string = swa.properties.defaultHostname
output swaName string = swa.name
output acrLoginServer string = acr.properties.loginServer
output projectEndpoint string = 'https://${foundryAccountName}.services.ai.azure.com/api/projects/${foundryProjectName}'
output topicEndpoint string = topic.properties.endpoint
output storageAccount string = storage.name
output apiIdentityClientId string = apiIdentity.properties.clientId
output deployIdentityClientId string = deployIdentity.properties.clientId
output appInsightsName string = appInsights.name
output logAnalyticsName string = logs.name

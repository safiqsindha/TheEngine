// The Engine — Live Scout infrastructure (Phase 1 Gate 2 + Phase 2)
// Team 2950 — The Devastators
//
// Provisions everything Live Scout needs to run on cron in Azure:
//   - Storage Account            (Tables for dispatcher, Blobs for pick_board)
//   - Log Analytics Workspace    (Container App logs land here)
//   - Container Apps Environment (the host)
//   - Container Registry         (private images, no Docker Hub auth)
//   - Container App Jobs (Phase 1):
//       * mode-a-worker        — high-frequency match OCR
//       * discovery-worker     — dispatcher state builder
//   - Container App Jobs (Phase 2):
//       * vision-worker        — T2 YOLO vision pass over cached frames
//       * synthesis-worker     — T3 Opus end-of-day strategic brief
//       * tba-uploader         — U post-match video publisher to TBA
//
// Deploy:
//   az deployment group create \
//     --resource-group <rg> \
//     --template-file infra/bicep/main.bicep \
//     --parameters environmentName=livescout-prod \
//                  tbaApiKey=<secret> \
//                  tbaTrustedAuthId=<secret> \
//                  tbaTrustedAuthSecret=<secret> \
//                  anthropicApiKey=<secret> \
//                  imageTag=<sha>
//
// Phase 2 secrets are optional at template level — workers whose secrets
// are missing will run but log an error. See GATE_2_HANDOFF.md §Phase 2.
//
// Resource names default to ${environmentName}-* so two environments
// (e.g. dev + prod) can coexist in the same subscription.

@description('Short identifier used as a prefix for every resource. Lowercase, 3-20 chars.')
@minLength(3)
@maxLength(20)
param environmentName string

@description('Azure region for every resource. Pick a region with Container Apps + low FRC latency.')
param location string = resourceGroup().location

@description('TBA API key — passed in as a secret, never written to source.')
@secure()
param tbaApiKey string

@description('Container image tag (typically the git SHA from the GitHub Action build).')
param imageTag string = 'latest'

@description('How often the Mode A worker fires when an event is active. Cron format.')
param modeACronExpression string = '*/1 * * * *'  // every minute

@description('How often the discovery worker rebuilds dispatcher state. Cron format.')
param discoveryCronExpression string = '*/15 * * * *'  // every 15 minutes

@description('Optional: pin the Mode A schedule to a date range so it does not waste compute outside of event days. Empty = always on.')
param modeAStartTime string = ''

// ─── Phase 2 params ───

@description('How often the vision worker runs on cached frames. Cron format.')
param visionCronExpression string = '*/10 * * * *'  // every 10 minutes

@description('Vision model name. "fake" runs the scripted stub (safe default); any other value routes to the real Roboflow loader which is NotImplementedError until V0a lands.')
param visionModelName string = 'fake'

@description('Optional GPU SKU for the vision worker. Empty = CPU-only (slow but works).')
param visionGpuSku string = ''

@description('How often the synthesis worker runs. Default 04:00 UTC ~= 20:00 PT (end-of-day strategic brief).')
param synthesisCronExpression string = '0 4 * * *'

@description('Anthropic model name for T3 synthesis. Defaults to claude-opus-4-6.')
param synthesisAnthropicModel string = 'claude-opus-4-6'

@description('How often the TBA uploader runs. Default every 15 minutes.')
param tbaUploaderCronExpression string = '*/15 * * * *'

@description('Anthropic API key for the T3 synthesis worker. Empty = synthesis-worker runs but errors out per tick.')
@secure()
param anthropicApiKey string = ''

@description('TBA Trusted User auth_id for the U TBA uploader. Empty = uploader runs in dry-run only.')
@secure()
param tbaTrustedAuthId string = ''

@description('TBA Trusted User auth_secret for the U TBA uploader. Empty = uploader runs in dry-run only.')
@secure()
param tbaTrustedAuthSecret string = ''

@description('When true, the TBA uploader never actually POSTs to TBA — logs only. Set to true in dev/staging.')
param tbaUploaderDryRun bool = true

// ─── Names ───

var storageAccountName    = toLower('${replace(environmentName, '-', '')}sa')
var logWorkspaceName      = '${environmentName}-logs'
var containerAppsEnvName  = '${environmentName}-cae'
var registryName          = toLower('${replace(environmentName, '-', '')}acr')
var modeAJobName          = '${environmentName}-mode-a'
var discoveryJobName      = '${environmentName}-discovery'
var visionJobName         = '${environmentName}-vision'
var synthesisJobName      = '${environmentName}-synthesis'
var tbaUploaderJobName    = '${environmentName}-tba-uploader'

var imageRepository = 'mode-a-worker'

// ─── Storage Account (dispatcher table + pick_board blob) ───

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'  // cheapest tier; we don't need redundancy for live scout state
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    accessTier: 'Hot'
  }
}

resource tableService 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource dispatcherTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tableService
  name: 'livescoutstate'
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource pickBoardContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'livescoutstate'
  properties: {
    publicAccess: 'None'
  }
}

// Compose the connection string used by the StateBackend factory.
// Built from the storage account's primary key so we don't need a
// separate Key Vault for Phase 1.
var storageKey = storageAccount.listKeys().keys[0].value
var storageConnectionString = 'DefaultEndpointsProtocol=https;AccountName=${storageAccount.name};AccountKey=${storageKey};EndpointSuffix=${environment().suffixes.storage}'

// ─── Log Analytics Workspace (Container App logs sink) ───

resource logWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logWorkspaceName
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30  // tighten if budget pressure
  }
}

// ─── Container Registry (private image host) ───

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'  // ~$5/month — no geo replication, fine for one event
  }
  properties: {
    adminUserEnabled: true  // GitHub Action auth via admin user; switch to OIDC later
  }
}

// ─── Container Apps Environment ───

resource containerAppsEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerAppsEnvName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logWorkspace.properties.customerId
        sharedKey: logWorkspace.listKeys().primarySharedKey
      }
    }
  }
}

// ─── Container App Job: Mode A worker ───

resource modeAJob 'Microsoft.App/jobs@2024-03-01' = {
  name: modeAJobName
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 600         // 10 min hard cap per execution
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: modeACronExpression
        parallelism: 1            // never run two replicas of the same cron tick
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'tba-api-key'
          value: tbaApiKey
        }
        {
          name: 'acr-password'
          value: registry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'mode-a-worker'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          command: [
            'python'
          ]
          args: [
            '-m'
            'workers.mode_a'
          ]
          resources: {
            cpu: json('1.0')   // PaddleOCR is single-threaded but benefits from headroom
            memory: '2.0Gi'
          }
          env: [
            {
              name: 'STATE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STATE_TABLE'
              value: 'livescoutstate'
            }
            {
              name: 'AZURE_STATE_BLOB_CONTAINER'
              value: 'livescoutstate'
            }
            {
              name: 'TBA_API_KEY'
              secretRef: 'tba-api-key'
            }
            {
              name: 'PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK'
              value: 'True'
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    dispatcherTable
    pickBoardContainer
  ]
}

// ─── Container App Job: Discovery worker ───

resource discoveryJob 'Microsoft.App/jobs@2024-03-01' = {
  name: discoveryJobName
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 300
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: discoveryCronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'tba-api-key'
          value: tbaApiKey
        }
        {
          name: 'acr-password'
          value: registry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'discovery-worker'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          command: [
            'python'
          ]
          args: [
            '-m'
            'workers.discovery'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'STATE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STATE_TABLE'
              value: 'livescoutstate'
            }
            {
              name: 'TBA_API_KEY'
              secretRef: 'tba-api-key'
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    dispatcherTable
  ]
}

// ─── Container App Job: Vision worker (Phase 2 T2) ───

resource visionJob 'Microsoft.App/jobs@2024-03-01' = {
  name: visionJobName
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 1800        // 30 min — YOLO on a full backlog can take a while
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: visionCronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'acr-password'
          value: registry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'vision-worker'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          command: [
            'python'
          ]
          args: [
            '-m'
            'workers.vision_worker'
            '--frames-dir-pattern'
            'eye/.cache/{event}/{match_short}/frames'
          ]
          // CPU-only until V0b picks a GPU SKU. Container Apps don't
          // expose GPU scheduling on the basic SKU path anyway — when
          // V0b lands, move this job to a GPU-capable environment.
          resources: {
            cpu: json('2.0')
            memory: '4.0Gi'
          }
          env: [
            {
              name: 'STATE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STATE_TABLE'
              value: 'livescoutstate'
            }
            {
              name: 'AZURE_STATE_BLOB_CONTAINER'
              value: 'livescoutstate'
            }
            {
              name: 'MODEL_NAME'
              value: visionModelName
            }
            {
              name: 'VISION_GPU_SKU'
              value: visionGpuSku
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    dispatcherTable
    pickBoardContainer
  ]
}

// ─── Container App Job: Synthesis worker (Phase 2 T3) ───

resource synthesisJob 'Microsoft.App/jobs@2024-03-01' = {
  name: synthesisJobName
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 600        // 10 min — one Anthropic call + state read/write
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: synthesisCronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'anthropic-api-key'
          value: anthropicApiKey
        }
        {
          name: 'acr-password'
          value: registry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'synthesis-worker'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          command: [
            'python'
          ]
          args: [
            '-m'
            'workers.synthesis_worker'
          ]
          resources: {
            cpu: json('0.5')
            memory: '1.0Gi'
          }
          env: [
            {
              name: 'STATE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STATE_TABLE'
              value: 'livescoutstate'
            }
            {
              name: 'AZURE_STATE_BLOB_CONTAINER'
              value: 'livescoutstate'
            }
            {
              name: 'ANTHROPIC_API_KEY'
              secretRef: 'anthropic-api-key'
            }
            {
              name: 'ANTHROPIC_MODEL'
              value: synthesisAnthropicModel
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    pickBoardContainer
  ]
}

// ─── Container App Job: TBA uploader (Phase 2 U) ───

resource tbaUploaderJob 'Microsoft.App/jobs@2024-03-01' = {
  name: tbaUploaderJobName
  location: location
  properties: {
    environmentId: containerAppsEnv.id
    configuration: {
      triggerType: 'Schedule'
      replicaTimeout: 300
      replicaRetryLimit: 1
      scheduleTriggerConfig: {
        cronExpression: tbaUploaderCronExpression
        parallelism: 1
        replicaCompletionCount: 1
      }
      registries: [
        {
          server: registry.properties.loginServer
          username: registry.listCredentials().username
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        {
          name: 'storage-connection-string'
          value: storageConnectionString
        }
        {
          name: 'tba-trusted-auth-id'
          value: tbaTrustedAuthId
        }
        {
          name: 'tba-trusted-auth-secret'
          value: tbaTrustedAuthSecret
        }
        {
          name: 'acr-password'
          value: registry.listCredentials().passwords[0].value
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'tba-uploader'
          image: '${registry.properties.loginServer}/${imageRepository}:${imageTag}'
          command: [
            'python'
          ]
          args: [
            '-m'
            'workers.tba_uploader'
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            {
              name: 'STATE_BACKEND'
              value: 'azure'
            }
            {
              name: 'AZURE_STORAGE_CONNECTION_STRING'
              secretRef: 'storage-connection-string'
            }
            {
              name: 'AZURE_STATE_BLOB_CONTAINER'
              value: 'livescoutstate'
            }
            {
              name: 'TBA_TRUSTED_AUTH_ID'
              secretRef: 'tba-trusted-auth-id'
            }
            {
              name: 'TBA_TRUSTED_AUTH_SECRET'
              secretRef: 'tba-trusted-auth-secret'
            }
            {
              name: 'TBA_UPLOADER_DRY_RUN'
              value: string(tbaUploaderDryRun)
            }
          ]
        }
      ]
    }
  }
  dependsOn: [
    pickBoardContainer
  ]
}

// ─── Outputs (referenced by the GitHub Action after first deploy) ───

output registryLoginServer string = registry.properties.loginServer
output registryName string = registry.name
output storageAccountName string = storageAccount.name
output containerAppsEnvironmentName string = containerAppsEnv.name
output modeAJobName string = modeAJob.name
output discoveryJobName string = discoveryJob.name
output visionJobName string = visionJob.name
output synthesisJobName string = synthesisJob.name
output tbaUploaderJobName string = tbaUploaderJob.name

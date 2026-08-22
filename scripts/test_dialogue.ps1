$ErrorActionPreference = "Stop"

$payload = @{
    npcId = "Wizard"
    displayName = "Rasmodia"
    sourceMods = @("Romanceable Rasmodius")
    date = "春 1 日"
    weather = "晴天"
    location = "法师塔"
    friendship = 128
    relationship = "未婚"
    message = "你好，今天过得怎么样？"
    provider = "fake"
} | ConvertTo-Json

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:5678/api/dialogue/test" `
    -ContentType "application/json" `
    -Body $payload

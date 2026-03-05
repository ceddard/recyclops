# 🌍 Recyclops — GitHub Accessibility Analyzer with LLM

**Reciclops** é um sistema de análise de acessibilidade HTML em pull requests do GitHub, alimentado por um LLM (GPT-4o-mini) rodando em AWS ECS, com orquestração de fila, validação de acessibilidade WCAG 2.1 e sistema de bypass para exceções.

---

## 📑 Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura AWS Completa](#arquitetura-aws-completa)
3. [Services](#services)
4. [Fluxo de Dados](#fluxo-de-dados)
5. [Configuração](#configuração)
6. [Como Usar](#como-usar)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 Visão Geral

### O que é?

Uma plataforma automatizada que:
- ✅ Recebe webhooks do GitHub (push/PR)
- 🧠 Analisa acessibilidade HTML com LLM
- 📊 Bloqueia PRs com score < 50
- 🔓 Permite bypass para exceções aprovadas
- 💾 Salva relatórios e histórico
- 📝 Comenta em PRs com resultados

### Benefícios

| Benefício | Descrição |
|-----------|-----------|
| **Automático** | Roda em todo push/PR sem intervenção manual |
| **Preciso** | Usa GPT-4o para análise semântica de acessibilidade |
| **Configurável** | Threshold, timeout, e bypass rules podem ser ajustados |
| **Auditável** | Relatórios salvos no DynamoDB com histórico |
| **Escalável** | ECS Fargate auto-scales conforme volume de PRs |

### Caso de Uso

```
Desenvolvedor faz PR com HTML
         ↓
GitHub notifica via webhook
         ↓
Sistema analisa acessibilidade
         ↓
Se score < 50: bloqueia merge (PRs ruim precisam fix)
Se score >= 50 ou tem bypass: aprova merge (ótimo!)
         ↓
Comentário postado no PR com report
```

---

## 🏗️ Arquitetura AWS Completa

```
┌─────────────────────────────────────────────────────────────────┐
│                         GITHUB                                   │
│              (Webhook: push, pull_request events)                │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    API GATEWAY (HTTPS)                           │
│  URL: https://<api-id>.execute-api.us-east-1.amazonaws.com      │
│  POST /webhook (validação HMAC + Lambda)                        │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                    LAMBDA (webhook-lambda)                       │
│  • Valida assinatura HMAC do GitHub                             │
│  • Extrai repo, PR #, commit SHA, etc                           │
│  • Envia mensagem para SQS FIFO                                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│                   SQS FIFO (recyclops-accessibility.fifo)        │
│  • Fila de análise com deduplication                            │
│  • Usa Group ID = repo para ordering                            │
│  • DLQ para mensagens com erro                                  │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│         ECS FARGATE CLUSTER (recyclops-cluster)                  │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SERVICE 1: recyclops-analyzer (1 task, 1vCPU, 2GB)      │   │
│  │ ┌──────────────────────────────────────────────────┐   │   │
│  │ │ • Long-polls SQS FIFO                            │   │   │
│  │ │ • Fetch files from GitHub API                    │   │   │
│  │ │ • Calls CERS-IA LLM via ALB internal             │   │   │
│  │ │ • Checks bypass-api for exceptions               │   │   │
│  │ │ • Posts comments on PR                           │   │   │
│  │ │ • Saves reports to DynamoDB                      │   │   │
│  │ │ • Sends errors to DLQ                            │   │   │
│  │ └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SERVICE 2: recyclops-service (1 task, 0.5vCPU, 1GB)    │   │
│  │ ┌──────────────────────────────────────────────────┐   │   │
│  │ │ CERS-IA: LLM FastAPI server                      │   │   │
│  │ │ • Receives HTML content from analyzer            │   │   │
│  │ │ • Calls OpenAI GPT-4o-mini for analysis          │   │   │
│  │ │ • Returns score, issues, suggestions, summary    │   │   │
│  │ │ • Timeout: 120 seconds                           │   │   │
│  │ └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ SERVICE 3: recyclops-bypass-api (1 task, 0.25vCPU, 512MB)│  │
│  │ ┌──────────────────────────────────────────────────┐   │   │
│  │ │ • GET /bypass/{repo}/{pr} - check active bypass  │   │   │
│  │ │ • POST /bypass - create new bypass               │   │   │
│  │ │ • DELETE /bypass/{repo}/{pr} - revoke bypass     │   │   │
│  │ │ • LIST /bypass/{repo} - list all bypasses        │   │   │
│  │ └──────────────────────────────────────────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                   │
│         ┌──────────────────────────────────┐                    │
│         │   ALB INTERNO (application)      │                    │
│         │ • Port 80 (internal only)        │                    │
│         │ • Targets: CERS-IA:8000          │                    │
│         │            Bypass-API:8001       │                    │
│         └──────────────────────────────────┘                    │
└─────────────────────────────────────────────────────────────────┘
         │                         │
         │                         ▼
         │            ┌────────────────────────┐
         │            │  GitHub API (v2022)    │
         │            │ • List PR files        │
         │            │ • Post comments        │
         │            │ • Create check runs    │
         │            │ • Post PR reviews      │
         │            └────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DATA LAYER (DynamoDB)                           │
│                                                                   │
│  TABLE 1: recyclops-reports                                      │
│  ├─ PK: REPO#{owner/repo}                                       │
│  ├─ SK: PR#{pr_number}#{sha8}                                   │
│  ├─ Attrs: score, issues_count, issues_json, bypass_used, ttl   │
│  └─ TTL: 90 days                                                │
│                                                                   │
│  TABLE 2: recyclops-bypass-rules                                │
│  ├─ PK: REPO#{owner/repo}                                       │
│  ├─ SK: PR#{pr_number}                                          │
│  ├─ Attrs: reason, created_by, expires_at, created_at, ttl      │
│  └─ TTL: dynamic (based on expires_at)                          │
└─────────────────────────────────────────────────────────────────┘

         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 SECRETS & CONFIG (SSM)                           │
│                                                                   │
│  /recyclops/GITHUB_TOKEN - repo read + PR comments permissions  │
│  /recyclops/OPENAI_API_KEY - GPT-4o-mini access                 │
│  /recyclops/GITHUB_WEBHOOK_SECRET - HMAC validation             │
│  /recyclops/SCORE_THRESHOLD - blocking threshold (default: 50)  │
└─────────────────────────────────────────────────────────────────┘

         ▼
┌─────────────────────────────────────────────────────────────────┐
│                 LOGGING (CloudWatch)                             │
│                                                                   │
│  /ecs/recyclops/accessibility-analyzer                          │
│  /ecs/recyclops/recyclops-service                               │
│  /ecs/recyclops/bypass-api                                      │
└─────────────────────────────────────────────────────────────────┘
```

### Componentes AWS Utilizados

| Serviço | Uso | Config |
|---------|-----|--------|
| **API Gateway** | Webhook endpoint HTTPS | POST /webhook → Lambda |
| **Lambda** | Validação de webhook | Node.js, 128MB, timeout 30s |
| **SQS FIFO** | Fila de análise | recyclops-accessibility.fifo, DLQ |
| **ECS Fargate** | Container orchestration | 3 services, auto-scaling |
| **ALB** | Load balancing interno | Internal, porta 80, 2 target groups |
| **ECR** | Container registry | 3 repos (analyzer, recyclops, bypass) |
| **DynamoDB** | Persistência reports/bypass | 2 tables, TTL habilitado |
| **SSM Parameter Store** | Secrets management | 4 parameters criptografados |
| **CloudWatch** | Logging | Log groups por service, retention 7 dias |
| **IAM** | Controle de acesso | Roles para Lambda, ECS, Fargate |
| **VPC** | Isolamento de rede | 1 VPC, 2 subnets públicas, SGs |

---

## 🔧 Services

### 1. webhook-lambda

**Localização**: `services/webhook-lambda/handler.py`

**Responsabilidade**: Gateway de entrada para eventos GitHub

#### Fluxo
```
GitHub Webhook (POST)
    ↓
Valida assinatura HMAC-SHA256 (ssm.get_parameter)
    ↓
Extrai evento (pull_request, push)
    ↓
Prepara payload estruturado
    ↓
Envia para SQS FIFO
    ↓
Retorna 200 OK ao GitHub
```

#### Eventos Processados

**Pull Request**
- `opened`, `synchronize`, `reopened` → envia para SQS
- Campos: repo, pr_number, head_sha, action

**Push**
- Qualquer commit → envia para SQS
- Campos: repo, ref, head_sha

#### Validação de Segurança

```python
# GitHub envia: x-hub-signature-256: sha256=<hash>
expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
hmac.compare_digest(signature, expected)  # Time-constant comparison
```

#### Integração SQS

```python
sqs.send_message(
    QueueUrl=SQS_URL,
    MessageBody=json.dumps(event),
    MessageGroupId=repo,  # Group ID = repo (FIFO ordering)
    MessageDeduplicationId=f"{sha}#{type}"  # Dedup ID
)
```

**Timeout**: 30s  
**Memória**: 128MB  
**Retry**: API Gateway retenta automaticamente

---

### 2. accessibility-analyzer

**Localização**: `services/accessibility-analyzer/`

**Responsabilidade**: Worker que orquestra a análise completa

#### Arquivos Principais

| Arquivo | Função |
|---------|--------|
| `main.py` | Entry point, setup Uvicorn |
| `analyzer.py` | Lógica de análise (pull_request vs push) |
| `client.py` | Integração com GitHub API |
| `dynamodb.py` | Persistência em DynamoDB |
| `models.py` | Pydantic models (SQSEvent, AnalysisResult, etc) |

#### Fluxo de Análise (PR)

```
SQS message recebido (pull_request event)
    ↓
Parse evento (repo, pr_number, head_sha)
    ↓
Cria Check Run no GitHub
    ↓
Fetch arquivos HTML modificados da PR
    ↓
Loop para cada arquivo HTML:
    ├─ POST para CERS-IA (http://<alb>/cers-ia/invoke)
    ├─ Recebe: score, issues, suggestions, summary
    └─ Acumula resultados
    ↓
Calcula score médio dos arquivos
    ↓
Se score < 50:
    └─ Query bypass-api (http://<alb>:8001/bypass)
    ↓
Define: passed = (score >= 50) OR (bypass ativo)
    ↓
Salva relatório no DynamoDB
    ↓
Posta comentário no PR
    ↓
Posta review (APPROVE ou REQUEST_CHANGES)
    ↓
Finaliza Check Run com conclusão (success/failure)
    ↓
Deleta mensagem da fila SQS
```

#### Lógica de Aprovação

```python
SCORE_THRESHOLD = 50  # Configurável via SSM

# Verificação de bypass (apenas se score < threshold)
if avg_score < SCORE_THRESHOLD:
    bypass_remote = await github.check_bypass_api(repo, pr_number)

# Bypass local (DynamoDB) como fallback
bypass_local = await db.check_bypass(repo, pr_number)

# Prioridade: remoto primeiro
bypass = bypass_remote or bypass_local

# Aprovação final
passed = avg_score >= SCORE_THRESHOLD or bypass is not None
conclusion = "success" if passed else "failure"
```

#### Timeouts e Retentativas

| Operação | Timeout | Retry |
|----------|---------|-------|
| GitHub API | 30s | Manual (logged as error) |
| CERS-IA LLM | 120s | Nenhuma (salva score 0 + erro) |
| Bypass-API | 10s | Nenhuma (assume sem bypass) |
| DynamoDB | Padrão boto3 | Boto3 automático (exponential backoff) |

#### Tratamento de Erros

```
Erro CERS-IA (timeout, 500, etc)
    ↓
Score = 0, issues = [], summary = erro_message
    ↓
Continua análise (não falha todo a PR)
    ↓
Se SQS: envia para DLQ após exceção não tratada
```

#### Variáveis de Ambiente

```bash
CERS_IA_URL=http://internal-recyclops-internal-xxx.us-east-1.elb.amazonaws.com
BYPASS_API_URL=http://internal-recyclops-internal-xxx.us-east-1.elb.amazonaws.com:8001
GITHUB_TOKEN=ghp_xxxxx (SSM secret)
OPENAI_API_KEY=sk-xxxxx (SSM secret)
SQS_URL=https://sqs.us-east-1.amazonaws.com/656661782834/recyclops-accessibility.fifo
DLQ_URL=https://sqs.us-east-1.amazonaws.com/656661782834/recyclops-analyzer-dlq.fifo
DYNAMODB_REPORTS=recyclops-reports
DYNAMODB_BYPASS=recyclops-bypass-rules
SCORE_THRESHOLD=50
AWS_REGION=us-east-1
```

---

### 3. recyclops-service (CERS-IA LLM)

**Localização**: `services/recyclops/`

**Responsabilidade**: FastAPI server que executa análise com LLM

#### Endpoint

```
POST /cers-ia/invoke
Content-Type: application/json

{
  "html_content": "<html>...</html>",
  "pr_metadata": {
    "filename": "index.html",
    "repo": "ceddard/mecontrataaipfvr"
  }
}
```

#### Response

```json
{
  "score": 85,
  "issues": [
    {
      "severity": "critical",
      "message": "Missing alt text on image",
      "element": "<img src='photo.png'>",
      "wcag_criterion": "WCAG 1.1.1",
      "fix": "Add alt attribute"
    }
  ],
  "suggestions": [
    {
      "line": 15,
      "description": "Use semantic HTML <main> instead of <div>",
      "fixed_code": "<main>content</main>"
    }
  ],
  "summary": "Good accessibility foundation. Main issues are missing landmarks and color contrast."
}
```

#### Prompt LLM

O prompt é construído para analisar HTML conforme WCAG 2.1 e NBR 17060:

```
Analyze this HTML for accessibility issues.

Report format:
{
  "score": 0-100,
  "issues": [{"severity": "critical|warning|info", "message": "", "element": "", "wcag_criterion": "", "fix": ""}],
  "suggestions": [{"line": number, "description": "", "fixed_code": ""}],
  "summary": "..."
}

Scoring:
- 100: Perfect accessibility
- 80+: Minor issues
- 50-79: Moderate issues
- <50: Major accessibility barriers
```

#### Lazy Initialization

```python
_llm = None

def _get_llm():
    global _llm
    if _llm is None:
        _llm = ChatOpenAI(
            model="gpt-4o-mini",
            temperature=0,
            api_key=os.environ.get("OPENAI_API_KEY"),
            timeout=120
        )
    return _llm
```

**Por quê**: Evita timeout no ECS task startup (LLM init demora ~10s). Iniciação acontece na primeira requisição.

#### Health Check

```
GET /health

Response: {"status": "ok", "service": "recyclops-service"}

Check: curl -f http://localhost:8000/health || exit 1
```

#### Recurso

- **CPU**: 0.5 vCPU (512 MB de CPU)
- **Memória**: 1 GB
- **Timeout requisição**: 120s
- **Porta**: 8000

---

### 4. bypass-api

**Localização**: `services/bypass-api/`

**Responsabilidade**: CRUD de regras de bypass para PRs bloqueadas

#### Endpoints

**POST /bypass** - Registrar bypass
```bash
curl -X POST http://alb:8001/bypass \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "ceddard/mecontrataaipfvr",
    "pr_number": 3,
    "reason": "Layout redesign approved by tech lead",
    "created_by": "carlos",
    "expires_in_hours": 48
  }'
```

**GET /bypass/{owner}/{repo}/{pr}** - Verificar bypass ativo
```bash
curl http://alb:8001/bypass/ceddard/mecontrataaipfvr/3
```

**DELETE /bypass/{owner}/{repo}/{pr}** - Remover bypass
```bash
curl -X DELETE http://alb:8001/bypass/ceddard/mecontrataaipfvr/3
```

**GET /bypass/{owner}/{repo}** - Listar todos os bypasses
```bash
curl http://alb:8001/bypass/ceddard/mecontrataaipfvr
```

#### Schema DynamoDB

```
Table: recyclops-bypass-rules
PK: REPO#{owner/repo}
SK: PR#{pr_number}

Attributes:
- reason: string
- created_by: string
- expires_at: int (Unix timestamp)
- created_at: int (Unix timestamp)
- TTL: expires_at (DynamoDB TTL)
```

#### Validação

- Bypass expirado → 404 (TTL do DynamoDB remove automaticamente)
- PR sem bypass → 404
- Criação bem-sucedida → 201 Created

#### Recurso

- **CPU**: 0.25 vCPU
- **Memória**: 512 MB
- **Timeout**: Default (30s)
- **Porta**: 8001

---

## 📊 Fluxo de Dados Detalhado

### Cenário 1: PR com Score >= 50 (Aprovada)

```
1. Dev faz commit com index.html
                ↓
2. GitHub envia webhook (push + pull_request)
                ↓
3. Lambda recebe, valida HMAC, envia SQS
                ↓
4. Analyzer recebe SQS message
                ↓
5. Fetch index.html do GitHub
                ↓
6. POST para CERS-IA → score = 85
                ↓
7. avg_score (85) >= threshold (50) → passed = True
                ↓
8. Salva report DynamoDB: {score: 85, bypass_used: false}
                ↓
9. Posta PR comment: "✅ APROVADO — Score: 85/100"
                ↓
10. Posta review: event = "APPROVE"
                ↓
11. Check Run finaliza: conclusion = "success"
                ↓
12. GitHub permite merge ✅
```

### Cenário 2: PR com Score < 50 (Bloqueada, sem bypass)

```
1. Dev faz commit com acessibilidade ruim
                ↓
2. GitHub envia webhook
                ↓
3. Lambda envia SQS
                ↓
4. Analyzer recebe SQS message
                ↓
5. Fetch HTML do GitHub
                ↓
6. POST para CERS-IA → score = 35
                ↓
7. avg_score (35) < threshold (50)
   → Query bypass-api: GET /bypass/repo/pr → 404
   → Query DynamoDB bypass table → null
   → bypass = None
                ↓
8. passed = (35 >= 50) OR (None is not None) = False
                ↓
9. Salva report: {score: 35, bypass_used: false}
                ↓
10. Posta PR comment: "❌ BLOQUEADO — Score: 35/100"
    "Problemas encontrados: 5 críticos, 3 avisos"
                ↓
11. Posta review: event = "REQUEST_CHANGES"
                ↓
12. Check Run finaliza: conclusion = "failure"
                ↓
13. GitHub bloqueia merge ❌
    (Developer deve fixar acessibilidade)
```

### Cenário 3: PR com Score < 50 (mas com bypass)

```
1-7. [Igual ao cenário 2: score = 35, abaixo do threshold]
                ↓
8. avg_score (35) < threshold (50)
   → Query bypass-api: GET /bypass/repo/3 → 200 OK
   → bypass = {reason: "Layout redesign", created_by: "tech-lead", expires_at: xxx}
                ↓
9. passed = (35 >= 50) OR (bypass is not None) = True
                ↓
10. Salva report: {score: 35, bypass_used: true}
                ↓
11. Posta PR comment: "⚠️ LIBERTO POR BYPASS"
    "Score: 35/100 (abaixo de 50)"
    "🔓 Bypass ativo: Layout redesign (por tech-lead)"
                ↓
12. Posta review: event = "APPROVE"
                ↓
13. Check Run finaliza: conclusion = "success"
                ↓
14. GitHub permite merge ✅
    (Com anotação de que foi desbloqueado)
```

---

## ⚙️ Configuração

### 1. Variáveis de Ambiente (SSM Parameter Store)

```bash
# Desenvolvimento
aws ssm put-parameter --name /recyclops/GITHUB_TOKEN \
  --value "ghp_xxxx" --type SecureString

aws ssm put-parameter --name /recyclops/OPENAI_API_KEY \
  --value "sk-xxxx" --type SecureString

aws ssm put-parameter --name /recyclops/GITHUB_WEBHOOK_SECRET \
  --value "webhook-secret-xxx" --type SecureString

aws ssm put-parameter --name /recyclops/SCORE_THRESHOLD \
  --value "50" --type String
```

### 2. AWS Secrets Manager (Alternativa)

```bash
aws secretsmanager create-secret --name recyclops/api-keys \
  --secret-string '{
    "github_token": "ghp_xxxx",
    "openai_api_key": "sk-xxxx",
    "webhook_secret": "secret-xxx"
  }'
```

### 3. Task Definition (ECS)

```json
{
  "family": "recyclops-analyzer",
  "taskRoleArn": "arn:aws:iam::xxxx:role/ecs-task-role",
  "executionRoleArn": "arn:aws:iam::xxxx:role/ecs-execution-role",
  "containerDefinitions": [
    {
      "name": "accessibility-analyzer",
      "image": "656661782834.dkr.ecr.us-east-1.amazonaws.com/recyclops/accessibility-analyzer:latest",
      "secrets": [
        {"name": "GITHUB_TOKEN", "valueFrom": "/recyclops/GITHUB_TOKEN"},
        {"name": "OPENAI_API_KEY", "valueFrom": "/recyclops/OPENAI_API_KEY"}
      ],
      "environment": [
        {"name": "SQS_URL", "value": "https://sqs.us-east-1.amazonaws.com/.."},
        {"name": "CERS_IA_URL", "value": "http://internal-alb..."},
        {"name": "SCORE_THRESHOLD", "value": "50"}
      ]
    }
  ]
}
```

### 4. Security Groups

**ALB SG** (`sg-013a15bd9f38ef72d`)
```
Ingress:
  - Port 80/tcp from 10.0.0.0/16 (VPC CIDR)
Egress:
  - All traffic allowed
```

**ECS Tasks SG** (`sg-049ed982001487908`)
```
Ingress:
  - Port 8000-8001/tcp from ALB SG
Egress:
  - All traffic allowed
```

### 5. IAM Roles

**ecs-execution-role**: Permissions para ECS agent
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "ecr:GetAuthorizationToken",
        "ecr:BatchGetImage",
        "ecr:GetDownloadUrlForLayer"
      ],
      "Resource": "*"
    },
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogStream",
        "logs:PutLogEvents"
      ],
      "Resource": "arn:aws:logs:*:*:*"
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:*:*:parameter/recyclops/*"
    }
  ]
}
```

**ecs-task-role**: Permissions para container
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["sqs:*"],
      "Resource": ["arn:aws:sqs:*:*:recyclops-*"]
    },
    {
      "Effect": "Allow",
      "Action": ["dynamodb:*"],
      "Resource": ["arn:aws:dynamodb:*:*:table/recyclops-*"]
    },
    {
      "Effect": "Allow",
      "Action": ["ssm:GetParameter"],
      "Resource": "arn:aws:ssm:*:*:parameter/recyclops/*"
    }
  ]
}
```

---

## 🚀 Como Usar

### 1. Local Development

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Variáveis locais
export GITHUB_TOKEN=ghp_xxx
export OPENAI_API_KEY=sk-xxx
export CERS_IA_URL=http://localhost:8000
export BYPASS_API_URL=http://localhost:8001

# Terminal 1: CERS-IA server
cd services/recyclops
python main.py  # Starts on port 8000

# Terminal 2: Bypass API server
cd services/bypass-api
python main.py  # Starts on port 8001

# Terminal 3: Analyzer (local testing)
cd services/accessibility-analyzer
python -c "
import asyncio
from test_analyzer import test_pr_analysis
asyncio.run(test_pr_analysis(
  repo='ceddard/mecontrataaipfvr',
  pr_number=3,
  sha='abc123'
))
"
```

### 2. Deploy para AWS

```bash
# Build Docker images
docker buildx build --platform linux/amd64 -t recyclops-service:latest \
  -f services/recyclops/Dockerfile services/recyclops/

docker push 656661782834.dkr.ecr.us-east-1.amazonaws.com/recyclops/recyclops-service:latest

# Terraform deploy
cd infra/terraform
terraform plan -var-file=poc.tfvars
terraform apply -var-file=poc.tfvars
```

### 3. Register GitHub Webhook

```bash
# Gerar secret
WEBHOOK_SECRET=$(openssl rand -hex 20)

# Registrar no GitHub (Settings → Webhooks)
curl -X POST https://api.github.com/repos/{OWNER}/{REPO}/hooks \
  -H "Authorization: token $GITHUB_TOKEN" \
  -d '{
    "name": "web",
    "active": true,
    "events": ["push", "pull_request"],
    "config": {
      "url": "https://<api-id>.execute-api.us-east-1.amazonaws.com/webhook",
      "content_type": "json",
      "secret": "'$WEBHOOK_SECRET'"
    }
  }'

# Salvar secret no SSM
aws ssm put-parameter --name /recyclops/GITHUB_WEBHOOK_SECRET \
  --value "$WEBHOOK_SECRET" --type SecureString
```

### 4. Criar/Remover Bypass

```bash
# Criar bypass (via API)
curl -X POST http://ALB:8001/bypass \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "ceddard/mecontrataaipfvr",
    "pr_number": 10,
    "reason": "SVG images with dynamic alt-text",
    "created_by": "tech-lead",
    "expires_in_hours": 72
  }'

# Listar bypasses ativos
curl http://ALB:8001/bypass/ceddard/mecontrataaipfvr

# Remover bypass
curl -X DELETE http://ALB:8001/bypass/ceddard/mecontrataaipfvr/10
```

### 5. Monitorar Análises

```bash
# Ver logs em tempo real
aws logs tail /ecs/recyclops/accessibility-analyzer --follow

# Buscar relatórios no DynamoDB
aws dynamodb query --table-name recyclops-reports \
  --key-condition-expression "pk = :pk" \
  --expression-attribute-values '{":pk": {"S": "REPO#ceddard/mecontrataaipfvr"}}' \
  --output json | jq '.Items[] | {pr: .sk, score: .score, created: .created_at}'

# Ver bypasses cadastrados
aws dynamodb scan --table-name recyclops-bypass-rules \
  --filter-expression "begins_with(pk, :prefix)" \
  --expression-attribute-values '{":prefix": {"S": "REPO#ceddard"}}' \
  --output table
```

---

## 🐛 Troubleshooting

### Erro: ConnectTimeout ao chamar CERS-IA

**Causa**: ALB resolvendo para IP público em vez de privado  
**Solução**: Verificar que ALB está com `internal = true` em Terraform

```bash
aws elbv2 describe-load-balancers --names recyclops-internal \
  --query 'LoadBalancers[0].Scheme'
# Deve retornar: internal
```

### Erro: "Name or service not known" em Route53

**Causa**: ECS Fargate não configurado para usar VPC DNS resolver  
**Solução**: Usar ALB DNS direto em vez de Route53 custom domain

```bash
# ALB DNS
aws elbv2 describe-load-balancers --names recyclops-internal \
  --query 'LoadBalancers[0].DNSName'
```

### Score sempre 0/100

**Causa 1**: OPENAI_API_KEY faltando ou inválido  
**Solução**: Verificar SSM parameter
```bash
aws ssm get-parameter --name /recyclops/OPENAI_API_KEY --with-decryption
```

**Causa 2**: CERS-IA timeout (120s)  
**Solução**: Aumentar timeout em analyzer.py
```python
async with httpx.AsyncClient(timeout=180) as client:
```

**Causa 3**: LLM não inicializou  
**Solução**: Verificar logs de health check
```bash
curl -f http://ALB:8000/health
```

### Mensagem presa na SQS (NotVisible > 1 min)

**Causa**: Analyzer crash durante processamento  
**Solução**: Verificar logs e DLQ
```bash
aws logs tail /ecs/recyclops/accessibility-analyzer --since 1h
aws sqs receive-message --queue-url https://sqs..../analyzer-dlq.fifo
```

### GitHub token sem permissão (403 Forbidden)

**Causa**: Token expirado ou sem permissões necessárias  
**Permissões necessárias**:
- `repo` (full control of repositories)
- `gist` (gist access, optional)

**Solução**: Regenerar token no GitHub
```bash
# Settings → Developer settings → Personal access tokens
# Copiar novo token para SSM
aws ssm put-parameter --name /recyclops/GITHUB_TOKEN \
  --value "ghp_new_token" --type SecureString --overwrite
```

### Auto-scaling não funciona

**Causa**: Target tracking policy não configurado  
**Solução**: Verificar ALB target group health

```bash
aws elbv2 describe-target-health \
  --target-group-arn arn:aws:elasticloadbalancing:...
# Todos os targets devem estar "healthy"
```

### Relatórios não aparecem em DynamoDB

**Causa**: DynamoDB table com TTL ativo removendo itens antigos  
**Solução**: Aumentar TTL ou desabilitar
```bash
aws dynamodb update-time-to-live --table-name recyclops-reports \
  --time-to-live-specification Enabled=false
```

---

## 📚 Referências

### WCAG 2.1 Critérios de Sucesso
- [1.1.1 Non-text Content (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/non-text-content.html)
- [1.4.3 Contrast (Minimum) (Level AA)](https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html)
- [2.1.1 Keyboard (Level A)](https://www.w3.org/WAI/WCAG21/Understanding/keyboard.html)

### NBR 17060 (Acessibilidade em Web)
- [NBR 17060:2023 - Acessibilidade digital](https://www.abnt.org.br/)

### Documentação AWS
- [ECS Fargate Documentation](https://docs.aws.amazon.com/ecs/)
- [DynamoDB Best Practices](https://docs.aws.amazon.com/amazondynamodb/)
- [SQS FIFO Queues](https://docs.aws.amazon.com/sqs/latest/dg/FIFO-queues.html)

### GitHub API
- [Webhooks Documentation](https://docs.github.com/en/developers/webhooks-and-events/webhooks)
- [Checks API](https://docs.github.com/en/rest/checks)
- [Pull Requests API](https://docs.github.com/en/rest/pulls)

---

## 📝 License

MIT License - Veja [LICENSE](LICENSE) para detalhes

---

## 👨‍💻 Autores

- Carlos Eduardo Soares (@ceddard)

**Última atualização**: 5 de março de 2026
# Judge0 em Kubernetes

Projeto prático desenvolvido para o Trabalho de Conclusão de Curso (TCC), com foco na implantação do **Judge0 em Kubernetes**, separando seus principais componentes para permitir testes de disponibilidade, escalabilidade e comportamento sob carga.

O ambiente atual utiliza **Minikube** com driver Docker e executa o Judge0 de forma distribuída entre diferentes Deployments.

## Arquitetura

```text
Cliente
   |
   v
judge0-service
   |
   v
srv-judge0
   |
   +-------------------+
   |                   |
   v                   v
 Redis              PostgreSQL
   |
   v
wk-judge0
   |
   v
Execução do código
```

### Componentes

- **srv-judge0**: API do Judge0.
- **wk-judge0**: Worker responsável por consumir e executar as submissões.
- **Redis**: fila utilizada pelo Judge0 para armazenar os trabalhos pendentes.
- **PostgreSQL**: banco de dados utilizado pelo Judge0.
- **Service**: disponibiliza a API dentro do cluster.
- **Grafana + Prometheus + kube-state-metrics**: monitoramento visual simples dos Pods e Workers.

A separação entre `srv-judge0` e `wk-judge0` permite aumentar a quantidade de Workers sem necessariamente aumentar a quantidade de instâncias da API.

---

## Estrutura do projeto

Exemplo:

```text
judge0-kubernetes/
|
|-- deployments.yaml
|-- services.yaml
|-- database.yaml
|-- monitor.yaml
|-- config/
|   `-- judge0.conf
|
`-- REGISTROS.md
```

---

## Pré-requisitos

- Docker Desktop
- Minikube
- kubectl
- PowerShell

O ambiente utilizado atualmente é um cluster Minikube com driver Docker.

Exemplo de criação:

```powershell
minikube start -p judge0-local --driver=docker --cpus=2 --memory=4096
```

---

## Implantação

A ideia é que o ambiente possa ser reproduzido em outra máquina apenas seguindo os passos abaixo.

### 1. Criar o cluster Minikube

Com o Docker Desktop aberto:

```powershell
minikube start -p judge0-local --driver=docker --cpus=2 --memory=4096
```

Verifique o cluster:

```powershell
kubectl get nodes
```

### 2. Criar os Secrets utilizados pelo Judge0

Os Deployments dependem de dois Secrets:

```text
vol-config
judge0-env
```

Eles são criados a partir do arquivo:

```text
config/judge0.conf
```

Crie o Secret utilizado para montar o arquivo `/judge0.conf`:

```powershell
kubectl create secret generic vol-config `
  --from-file=judge0.conf=config/judge0.conf `
  --dry-run=client -o yaml | kubectl apply -f -
```

Crie o Secret utilizado pelas variáveis de ambiente do Redis e PostgreSQL:

```powershell
kubectl create secret generic judge0-env `
  --from-env-file=config/judge0.conf `
  --dry-run=client -o yaml | kubectl apply -f -
```

### Atenção ao formato do `judge0.conf`

O arquivo:

```text
config/judge0.conf
```

deve utilizar quebra de linha:

```text
LF
```

e não:

```text
CRLF
```

Caso seja salvo com CRLF no Windows, o container pode apresentar erros semelhantes a:

```text
$'\r': command not found
```

No VS Code, o formato pode ser alterado no canto inferior direito do editor, trocando `CRLF` por `LF`.

### 3. Aplicar os manifests

Com os arquivos YAML na raiz do projeto:

```powershell
kubectl apply -f .
```

Verifique os recursos principais:

```powershell
kubectl get deployments
kubectl get pods
kubectl get svc
```

Verifique também o ambiente de monitoramento:

```powershell
kubectl get pods -n monitor
```

Para acompanhar a inicialização dos Pods:

```powershell
kubectl get pods -w
```

O ambiente estará pronto quando os componentes principais estiverem semelhantes a:

```text
db-xxxxx             1/1   Running
redis-xxxxx          1/1   Running
srv-judge0-xxxxx     1/1   Running
wk-judge0-xxxxx      1/1   Running
```

E o monitoramento:

```text
grafana-xxxxx              1/1   Running
prometheus-xxxxx           1/1   Running
kube-state-metrics-xxxxx   1/1   Running
```

---

## Acessando a API Judge0

No Minikube com Docker no Windows, o acesso está sendo realizado através de `port-forward`.

Abra um terminal e mantenha-o aberto:

```powershell
kubectl port-forward svc/judge0-service 2358:2358
```

A API ficará disponível em:

```text
http://127.0.0.1:2358
```

Teste:

```powershell
curl.exe http://127.0.0.1:2358/languages
```

---

## Testando uma submissão

Exemplo utilizando Python 3 (`language_id = 71`):

```powershell
$body = @{
    source_code = 'print("Hello Kubernetes")'
    language_id = 71
} | ConvertTo-Json

Invoke-RestMethod `
    -Uri 'http://127.0.0.1:2358/submissions?base64_encoded=false&wait=true' `
    -Method POST `
    -ContentType 'application/json' `
    -Body $body
```

O resultado esperado deve apresentar:

```text
Accepted
```

---

# Teste com múltiplas submissões

Os testes atuais utilizam **200 submissões assíncronas**, permitindo comparar a capacidade de processamento com diferentes quantidades de Workers.

Diferente do teste com:

```text
wait=true
```

as submissões são enviadas sem aguardar o resultado imediato. Cada chamada retorna um token e, posteriormente, o script consulta os tokens até que todas as submissões tenham sido concluídas.

Isso permite medir o tempo total para processar o lote.

## Script de teste

```powershell
$uri = 'http://127.0.0.1:2358/submissions?base64_encoded=false'

$body = @{
    source_code = 'print("Teste Kubernetes")'
    language_id = 71
} | ConvertTo-Json -Compress

$tokens = @()
$errosEnvio = 0

$inicio = Get-Date

for ($i = 1; $i -le 200; $i++) {

    try {

        $r = Invoke-RestMethod `
            -Uri $uri `
            -Method POST `
            -ContentType 'application/json' `
            -Body $body `
            -ErrorAction Stop

        $tokens += $r.token
    }
    catch {

        $errosEnvio++
        Write-Host "Erro ao enviar submissão $i"
    }
}

Write-Host "Tokens recebidos: $($tokens.Count)"
Write-Host "Tokens únicos: $(($tokens | Select-Object -Unique).Count)"
Write-Host "Erros de envio: $errosEnvio"

$concluidos = @{}

while ($concluidos.Count -lt $tokens.Count) {

    foreach ($token in $tokens) {

        if (-not $concluidos.ContainsKey($token)) {

            $r = Invoke-RestMethod `
                -Uri "http://127.0.0.1:2358/submissions/$token"

            if ($r.status.id -gt 2) {
                $concluidos[$token] = $r.status.description
            }
        }
    }

    Write-Host "`rConcluídos: $($concluidos.Count)/$($tokens.Count)" -NoNewline

    Start-Sleep -Milliseconds 300
}

$fim = Get-Date

$tempoTotal = ($fim - $inicio).TotalSeconds

$workers = kubectl get deployment wk-judge0 -o jsonpath='{.spec.replicas}'

Write-Host ""
Write-Host "============================"
Write-Host "Workers:       $workers"
Write-Host "Submissoes:    $($tokens.Count)"
Write-Host "Concluidas:    $($concluidos.Count)"
Write-Host "Tempo total:   $([math]::Round($tempoTotal,3)) s"
Write-Host "Throughput:    $([math]::Round($concluidos.Count/$tempoTotal,2)) submissoes/s"
Write-Host "============================"
```

Para uma rodada ser considerada válida, o esperado é:

```text
Tokens recebidos: 200
Tokens únicos: 200
Erros de envio: 0
Concluídas: 200
```

## Cenários

### 1 Worker

```powershell
kubectl scale deployment wk-judge0 --replicas=1
```

### 2 Workers

```powershell
kubectl scale deployment wk-judge0 --replicas=2
```

### 3 Workers

```powershell
kubectl scale deployment wk-judge0 --replicas=3
```

Antes de cada rodada, aguarde todos os Workers ficarem prontos:

```powershell
kubectl get pods -l app=wk-judge0
```

O objetivo é manter as mesmas condições de teste e alterar apenas a quantidade de réplicas dos Workers.

Os resultados são registrados no arquivo:

```text
REGISTROS.md
```

---

# Teste de autorrecuperação

Para observar o comportamento do Kubernetes quando um Worker é removido:

```powershell
kubectl get pods -l app=wk-judge0 -w
```

Em outro terminal:

```powershell
kubectl delete pod -l app=wk-judge0
```

O Deployment deve detectar que o número atual de Pods ficou abaixo do estado desejado e criar automaticamente uma nova instância.

Esse comportamento é chamado de **self-healing (autorrecuperação)**.

> Não se trata de rollback. Rollback é o retorno de um Deployment para uma revisão anterior.

---

# Monitoramento

O projeto possui um monitoramento simples com:

```text
kube-state-metrics
        |
        v
   Prometheus
        |
        v
     Grafana
```

O objetivo é facilitar a visualização durante os testes e durante a apresentação do TCC, sem transformar observabilidade no foco principal do trabalho.

Recursos observados na dashboard:

- Judge0 API online/offline;
- quantidade de Workers online;
- Redis online/offline;
- PostgreSQL online/offline;
- Workers desejados;
- Workers disponíveis;
- reinicializações;
- Pods prontos.

Verifique os Pods:

```powershell
kubectl get pods -n monitor
```

Abra o Grafana:

```powershell
kubectl port-forward -n monitor svc/grafana 3000:3000
```

Acesse:

```text
http://127.0.0.1:3000
```

Credenciais utilizadas apenas no laboratório local:

```text
usuario: admin
senha: admin
```

---

# Registro dos experimentos

Os resultados e observações dos experimentos são armazenados em:

```text
REGISTROS.md
```

A ideia é manter separados:

- **README.md**: como o projeto funciona e como executá-lo;
- **REGISTROS.md**: resultados obtidos durante os experimentos.

---

## Reprodução rápida em outra máquina

Resumo do processo para subir o ambiente em outro computador:

```text
1. Instalar Docker Desktop, Minikube e kubectl
2. Clonar este repositório
3. Garantir que config/judge0.conf esteja em LF
4. Criar o cluster Minikube
5. Criar os Secrets vol-config e judge0-env
6. Executar kubectl apply -f .
7. Confirmar os Pods
8. Abrir os port-forwards
```

Comandos principais:

```powershell
minikube start -p judge0-local --driver=docker --cpus=2 --memory=4096

kubectl create secret generic vol-config `
  --from-file=judge0.conf=config/judge0.conf `
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create secret generic judge0-env `
  --from-env-file=config/judge0.conf `
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -f .

kubectl get pods
kubectl get pods -n monitor
```

API Judge0:

```powershell
kubectl port-forward svc/judge0-service 2358:2358
```

Grafana:

```powershell
kubectl port-forward -n monitor svc/grafana 3000:3000
```

---

## Próximas etapas

- aumentar progressivamente a quantidade de requisições;
- comparar 1, 2 e 3 Workers;
- repetir os testes para reduzir influência de variações pontuais;
- testar autorrecuperação durante processamento;
- observar disponibilidade da aplicação;
- medir comportamento da fila;
- posteriormente repetir os experimentos em infraestrutura distribuída.

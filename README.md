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

Com os arquivos YAML na raiz do projeto:

```powershell
kubectl apply -f .
```

Verifique os recursos:

```powershell
kubectl get deployments
kubectl get pods
kubectl get svc
```

Para acompanhar os Pods:

```powershell
kubectl get pods -w
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

# Teste com múltiplas requisições

O script abaixo envia **10 submissões simultâneas** para o Judge0 e registra o tempo individual de cada uma.

```powershell
$uri = 'http://127.0.0.1:2358/submissions?base64_encoded=false&wait=true'

$body = @{
    source_code = 'print("Teste Kubernetes")'
    language_id = 71
} | ConvertTo-Json

$jobs = foreach ($i in 1..10) {

    Start-Job -ArgumentList $i,$uri,$body -ScriptBlock {

        param($id,$uri,$body)

        $tempo = [System.Diagnostics.Stopwatch]::StartNew()

        try {

            $resultado = Invoke-RestMethod `
                -Uri $uri `
                -Method POST `
                -ContentType 'application/json' `
                -Body $body

            $tempo.Stop()

            [PSCustomObject]@{
                Requisicao = $id
                Status     = $resultado.status.description
                Tempo      = [math]::Round($tempo.Elapsed.TotalSeconds, 3)
            }

        }
        catch {

            $tempo.Stop()

            [PSCustomObject]@{
                Requisicao = $id
                Status     = "ERRO"
                Tempo      = [math]::Round($tempo.Elapsed.TotalSeconds, 3)
            }
        }
    }
}

$jobs | Wait-Job | Out-Null

$resultados = $jobs | Receive-Job

$jobs | Remove-Job

$resultados |
    Sort-Object Requisicao |
    Select-Object Requisicao, Status, Tempo |
    Format-Table
```

Esse teste pode ser repetido alterando apenas a quantidade de réplicas do Worker.

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

Antes de iniciar um novo teste, confirme que todos os Workers estão disponíveis:

```powershell
kubectl get pods -l app=wk-judge0
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

Os resultados dos testes são armazenados em:

```text
REGISTROS.md
```

A ideia é manter separados:

- **README.md**: como o projeto funciona e como executá-lo;
- **REGISTROS.md**: resultados obtidos durante os experimentos.

---

## Próximas etapas

- aumentar progressivamente a quantidade de requisições;
- comparar 1, 2 e 3 Workers;
- repetir os testes para reduzir influência de variações pontuais;
- testar autorrecuperação durante processamento;
- observar disponibilidade da aplicação;
- medir comportamento da fila;
- posteriormente repetir os experimentos em infraestrutura distribuída.

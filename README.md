# Judge0 em Kubernetes

> Infraestrutura distribuída para execução automatizada de códigos do **Dev³**, com foco em escalabilidade, distribuição de carga, persistência e disponibilidade.

Este repositório reúne os manifests, configurações e registros experimentais utilizados no Trabalho de Conclusão de Curso **“Avaliação de uma Infraestrutura Kubernetes para Execução Automatizada de Códigos: Escalabilidade, Distribuição de Carga e Disponibilidade”**.

O projeto parte do Judge0 como mecanismo de execução e avaliação de submissões e utiliza Kubernetes para separar e distribuir API, Workers, fila e banco de dados. O ambiente foi inicialmente validado em Minikube e posteriormente migrado para um **cluster físico experimental**, que atualmente concentra os testes do trabalho.

---

## Objetivos do projeto

A infraestrutura foi construída para permitir a avaliação prática de:

- distribuição das requisições entre múltiplas instâncias da API;
- processamento concorrente das submissões por múltiplos Workers;
- escalabilidade horizontal dos Workers;
- comportamento da fila Redis sob carga;
- persistência dos dados;
- replicação do PostgreSQL e do Redis entre nós diferentes;
- autorrecuperação de Pods;
- comportamento do ambiente durante falhas de Pods e nós;
- disponibilidade da aplicação durante os experimentos.

> O objetivo não é substituir o Dev³ ou modificar sua lógica de negócio. O cluster fornece a infraestrutura responsável pela execução automatizada dos códigos enviados pela plataforma.

---

# Arquitetura atual

```text
                         Dev³
                          |
                          v
                +-------------------+
                | judge0-service    |
                | Service/NodePort  |
                +---------+---------+
                          |
               +----------+----------+
               |                     |
               v                     v
        +-------------+       +-------------+
        | Judge0 API  |       | Judge0 API  |
        |   Pod 1     |       |   Pod 2     |
        +------+------+       +------+------+
               |                     |
               +----------+----------+
                          |
              +-----------+-----------+
              |                       |
              v                       v
      +---------------+       +----------------+
      | Redis Primary |       | PostgreSQL     |
      |     fila      |       |    Primary     |
      +-------+-------+       +--------+-------+
              |                        |
              | replicação             | streaming replication
              v                        v
      +---------------+       +----------------+
      | Redis Replica |       | PostgreSQL     |
      |               |       |    Replica     |
      +---------------+       +----------------+

              Redis
                |
                v
       +------------------+
       | Judge0 Workers   |
       | 4 Pods iniciais  |
       | COUNT=2 por Pod  |
       +--------+---------+
                |
                v
          Execução do código
```

O `Service` fornece um ponto estável de acesso às instâncias da API. As submissões recebidas pela API são enfileiradas no Redis e posteriormente consumidas pelos Workers. O PostgreSQL mantém os dados persistentes utilizados pelo Judge0.

---

## Distribuição física

O cluster possui um nó de controle e dois nós AMD64 destinados às cargas do Judge0.

```text
Control Plane
└── arquitetura ARM
    └── gerenciamento do cluster

srv-kube-worker-1
├── PostgreSQL Primary
├── Redis Replica
├── Judge0 API
└── Judge0 Workers

srv-kube-worker-2
├── PostgreSQL Replica
├── Redis Primary
├── Judge0 API
└── Judge0 Workers
```

A API e os Workers utilizam:

```yaml
nodeSelector:
  kubernetes.io/arch: amd64
```

Isso impede que essas cargas sejam agendadas no nó ARM sem prendê-las a um Worker específico.

Para as duas réplicas da API é utilizada **Pod Anti-Affinity**, de forma que as duas instâncias não sejam executadas no mesmo nó:

```yaml
affinity:
  podAntiAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      - labelSelector:
          matchExpressions:
            - key: app
              operator: In
              values:
                - srv-judge0
        topologyKey: kubernetes.io/hostname
```

Como existem apenas dois node Workers no cluster Kubernetes, o RollingUpdate da API pode ser configurado para não tentar criar uma terceira instância durante uma atualização:

```yaml
strategy:
  type: RollingUpdate
  rollingUpdate:
    maxSurge: 0
    maxUnavailable: 1
```

---

# Componentes

| Componente | Função | Configuração atual |
|---|---|---|
| **Judge0 API** | Receber e consultar submissões | 2 réplicas |
| **Judge0 Workers** | Consumir a fila e executar códigos | 4 réplicas iniciais |
| **Redis Primary** | Fila principal do Judge0 | Worker 2 + AOF + PVC |
| **Redis Replica** | Réplica da fila | Worker 1 + AOF + PVC |
| **PostgreSQL Primary** | Banco principal | Worker 1 + PVC |
| **PostgreSQL Replica** | Standby por streaming replication | Worker 2 + PVC |
| **Service** | Endpoint estável para a API | NodePort |
| **HPA** | Escalonamento horizontal dos Workers | baseado em CPU |
| **Prometheus** | Coleta de métricas | monitoramento |
| **kube-state-metrics** | Métricas de objetos Kubernetes | monitoramento |
| **Grafana** | Visualização das métricas | dashboards |

---

# Persistência

## PostgreSQL

O PostgreSQL deixou de utilizar armazenamento efêmero e passou a utilizar `PersistentVolume` e `PersistentVolumeClaim`.

```text
PostgreSQL Primary
        |
        v
 postgres-data
        |
        v
postgres-pv-primary
        |
        v
armazenamento local do Worker 1
```

A réplica possui seu próprio volume no Worker 2:

```text
PostgreSQL Replica
        |
        v
postgres-replica-data
        |
        v
postgres-pv-replica
        |
        v
armazenamento local do Worker 2
```

A sincronização entre as instâncias utiliza **streaming replication**. O standby é inicializado a partir de uma cópia do Primary feita com `pg_basebackup`.

Validação:

```bash
kubectl exec deploy/db-replica -- \
  psql -U judge0 -d postgres \
  -c "SELECT pg_is_in_recovery();"
```

Resultado esperado:

```text
t
```

No Primary:

```bash
kubectl exec deploy/db -- \
  psql -U judge0 -d postgres \
  -c "SELECT client_addr, usename, application_name, state, sync_state FROM pg_stat_replication;"
```

O estado esperado da réplica é:

```text
state = streaming
```

---

## Redis

O Redis utiliza persistência AOF:

```text
--appendonly yes
```

O Primary e a Replica possuem volumes independentes.

```text
Worker 1                         Worker 2

Redis Replica   <-------------  Redis Primary
     |            replicação          |
     v                                v
PVC Replica                       PVC Primary
```

Validação no Primary:

```bash
kubectl exec deploy/redis -- sh -c \
'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli INFO replication'
```

Resultado esperado:

```text
role:master
connected_slaves:1
```

Validação na Replica:

```bash
kubectl exec deploy/redis-replica -- sh -c \
'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli INFO replication'
```

Resultado esperado:

```text
role:slave
master_host:redis
master_link_status:up
```

Teste simples:

```bash
kubectl exec deploy/redis -- sh -c \
'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli SET teste-replica "funcionando"'
```

```bash
kubectl exec deploy/redis-replica -- sh -c \
'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli GET teste-replica'
```

Resultado:

```text
funcionando
```

> **Importante:** replicação não significa failover automático. No estado atual do projeto, a existência das réplicas protege os dados e permite testes de promoção, mas a troca automática de Primary ainda precisa de um mecanismo específico de failover.

---

# Estrutura sugerida do repositório

```text
judge0-kubernetes/
|
|-- judge0/
|   |
|   |-- config/
|   |   |-- judge0.conf.example
|   |   `-- .env.example
|   |
|   |-- db/
|   |   |-- primary/
|   |   |   |-- db.yaml
|   |   |   |-- db-pv.yaml
|   |   |   |-- db-pvc.yaml
|   |   |   `-- services.yaml
|   |   |
|   |   `-- replica/
|   |       |-- db-replica.yaml
|   |       |-- replica-db-pv.yaml
|   |       |-- replica-db-pvc.yaml
|   |       `-- services.yaml
|   |
|   |-- redis/
|   |   |-- primary/
|   |   |   |-- redis.yaml
|   |   |   |-- redis-pv.yaml
|   |   |   |-- redis-pvc.yaml
|   |   |   `-- services.yaml
|   |   |
|   |   `-- replica/
|   |       |-- redis-replica.yaml
|   |       |-- redis-pv.yaml
|   |       |-- redis-pvc.yaml
|   |       `-- services.yaml
|   |
|   |-- deployments.yaml
|   |-- services.yaml
|   |-- hpa.yaml
|   `-- REGISTROS.md
|
|-- monitor/
|   `-- monitor.yaml
|
|-- .gitignore
`-- README.md
```

A estrutura acima separa os componentes com estado dos componentes que podem ser distribuídos livremente pelo Scheduler.

---

# Configuração e Secrets

Credenciais reais **não devem ser versionadas no Git**.

Utilize arquivos locais para os valores sensíveis:

```text
.env
judge0.conf
```

E mantenha no repositório apenas modelos:

```text
.env.example
judge0.conf.example
```

Exemplo de `.env.example`:

```env
REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=

POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=judge0
POSTGRES_USER=judge0
POSTGRES_PASSWORD=

RAILS_ENV=production
```

Criação do Secret das variáveis:

```bash
kubectl create secret generic judge0-env \
  --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -
```

Criação do arquivo de configuração utilizado pelo Judge0:

```bash
kubectl create secret generic vol-config \
  --from-file=judge0.conf=config/judge0.conf \
  --dry-run=client -o yaml | kubectl apply -f -
```

> Kubernetes Secrets não devem ser tratados como um cofre por si só. O acesso ao cluster, RBAC e ao armazenamento do control plane também deve ser protegido.

---

# Arquivos que não devem ir para o Git

Exemplo de `.gitignore`:

```gitignore
# Credenciais
.env
.env.*
!.env.example

# Configuração real
judge0.conf
!judge0.conf.example

# Kubernetes
kubeconfig
*.kubeconfig
secret.yaml
secrets.yaml
*-secret.yaml
*-secrets.yaml

# Chaves
*.key
*.pem
id_rsa
id_ed25519

# Banco / backups
*.sql
*.dump
*.backup
backups/

# Logs
*.log
logs/

# Dados locais
data/
postgres-data/
redis-data/

# Editores / sistema
.vscode/
.idea/
.DS_Store
Thumbs.db
```

---

# Implantação

## 1. Verificar o cluster

```bash
kubectl get nodes -o wide
```

## 2. Criar os Secrets

```bash
kubectl get secret judge0-env
kubectl get secret vol-config
```

Caso ainda não existam, crie-os conforme a seção anterior.

## 3. PostgreSQL

```bash
kubectl apply -f judge0/db/primary/
kubectl apply -f judge0/db/replica/
```

Verifique:

```bash
kubectl get pods -l app=db -o wide
kubectl get pods -l app=db-replica -o wide
kubectl get pv,pvc
```

## 4. Redis

```bash
kubectl apply -f judge0/redis/primary/
kubectl apply -f judge0/redis/replica/
```

Verifique:

```bash
kubectl get pods -l app=redis -o wide
kubectl get pods -l app=redis-replica -o wide
kubectl get pv,pvc
```

## 5. API e Workers

```bash
kubectl apply -f judge0/deployments.yaml
kubectl apply -f judge0/services.yaml
```

Caso o HPA esteja separado:

```bash
kubectl apply -f judge0/hpa.yaml
```

## 6. Verificar o ambiente

```bash
kubectl get pods -o wide
kubectl get svc
kubectl get deployments
kubectl get hpa
kubectl get pv,pvc
```

---

# Acesso ao Judge0

No cluster físico, o acesso externo ao Judge0 é realizado através do `Service` da API.

Verifique:

```bash
kubectl get svc judge0-service
```

Exemplo de teste:

```bash
curl http://<NODE_IP>:<NODEPORT>/system_info
```

ou:

```bash
curl http://<NODE_IP>:<NODEPORT>/languages
```

O Dev³ deve apontar para o `Service`, e não diretamente para o IP de um Pod da API.

---

# Escalabilidade

## Workers

Os Workers são separados da API para que a capacidade de execução possa ser aumentada sem necessariamente aumentar o número de instâncias que recebem requisições.

Escala manual:

```bash
kubectl scale deployment wk-judge0 --replicas=6
```

Verificação:

```bash
kubectl get pods -l app=wk-judge0 -o wide
```

## HPA

O HorizontalPodAutoscaler pode ajustar automaticamente a quantidade de Workers com base nas métricas definidas no manifesto.

```bash
kubectl get hpa
```

```bash
kubectl describe hpa wk-judge0
```

> O HPA reage às métricas configuradas, como utilização de CPU. Ele não deve ser interpretado como um mecanismo que detecta diretamente a falha de um nó.

---

# Distribuição da API

A API possui duas réplicas e utiliza anti-affinity para evitar que ambas fiquem no mesmo Worker.

Validação:

```bash
kubectl get pods -l app=srv-judge0 -o wide
```

O esperado é:

```text
API 1 -> Worker 1
API 2 -> Worker 2
```

---

# Autorrecuperação

Para observar a reposição de um Pod gerenciado pelo Deployment:

```bash
kubectl get pods -l app=wk-judge0 -w
```

Em outro terminal:

```bash
kubectl delete pod <NOME_DO_POD>
```

O Deployment mantém o estado desejado e cria uma nova instância para substituir o Pod removido.

> Autorrecuperação não é rollback. Rollback corresponde ao retorno de um Deployment para uma revisão anterior.

---

# Testes de disponibilidade

Os testes de disponibilidade são realizados provocando falhas controladas enquanto submissões estão em processamento.

Exemplos:

- remoção de um Pod da API;
- remoção de um Worker;
- reinicialização de um nó de execução;
- indisponibilidade de um nó que contém um componente Primary;
- validação da persistência após recriação do Pod;
- promoção controlada de uma réplica.

Durante os testes são observados:

```text
requisições enviadas
requisições aceitas
falhas de POST
submissões concluídas
timeouts de polling
tempo total
throughput
estado dos Pods
estado dos Nodes
estado da fila
```

Os resultados experimentais devem permanecer separados da documentação de implantação:

```text
README.md     -> arquitetura e reprodução
REGISTROS.md  -> resultados e observações dos experimentos
```

---

# Monitoramento

A camada de monitoramento utiliza:

```text
kube-state-metrics
        |
        v
   Prometheus
        |
        v
     Grafana
```

O objetivo do monitoramento neste projeto é auxiliar os experimentos e a apresentação dos resultados, sem transformar observabilidade no foco principal do trabalho.

Podem ser acompanhados:

- estado dos Pods;
- quantidade de réplicas desejadas e disponíveis;
- reinicializações;
- estado da API;
- quantidade de Workers;
- utilização de CPU e memória;
- comportamento do HPA;
- disponibilidade dos componentes.

Verifique:

```bash
kubectl get pods -n monitor
```

---

# Ambiente local com Minikube

O Minikube foi utilizado na etapa inicial do projeto para validar a separação dos componentes e os primeiros experimentos.

Exemplo:

```bash
minikube start -p judge0-local \
  --driver=docker \
  --cpus=2 \
  --memory=4096
```

O ambiente físico passou a ser utilizado posteriormente para avaliar distribuição real entre máquinas, persistência local, falhas de nós e replicação entre Workers.

---

# Limitações atuais

Alguns pontos devem ser considerados ao interpretar o ambiente:

1. Os `PersistentVolumes` utilizados são locais e, portanto, vinculados fisicamente aos nós que armazenam os dados.
2. PostgreSQL Primary + Replica fornece replicação, mas não representa sozinho failover automático.
3. Redis Primary + Replica fornece replicação, mas a promoção automática exige um mecanismo adicional, como Redis Sentinel.
4. Com apenas dois Workers, a falha de um deles reduz significativamente a capacidade computacional disponível.
5. O HPA escala Pods com base nas métricas configuradas; ele não substitui mecanismos de alta disponibilidade para banco de dados e fila.
6. Os resultados obtidos representam este cluster e estas configurações e não devem ser interpretados como limites universais do Judge0 ou do Kubernetes.

---

# Documentação e referências utilizadas

As referências abaixo são, preferencialmente, documentações oficiais utilizadas ao longo da implantação e dos experimentos.

## Judge0

- [Judge0 — repositório oficial](https://github.com/judge0/judge0)
- [Judge0 — arquivo oficial `judge0.conf`](https://github.com/judge0/judge0/blob/master/judge0.conf)
- [Judge0 — documentação da API](https://ce.judge0.com/)
- [Judge0 — Configuration Info](https://github.com/judge0/judge0/blob/master/docs/api/system_and_configuration/configuration_info.md)

## Kubernetes — conceitos e cluster

- [Kubernetes — Concepts](https://kubernetes.io/docs/concepts/)
- [Kubernetes — Creating a cluster with kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/create-cluster-kubeadm/)
- [Kubernetes — Installing kubeadm](https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/install-kubeadm/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes — Services, Load Balancing and Networking](https://kubernetes.io/docs/concepts/services-networking/)
- [Kubernetes — Self-Healing](https://kubernetes.io/docs/concepts/architecture/self-healing/)

## Kubernetes — escalabilidade e recursos

- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)
- [Kubernetes — Resource Management for Pods and Containers](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [Kubernetes — Deployment RollingUpdate](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/#rolling-update-deployment)

## Kubernetes — agendamento

- [Kubernetes — Assigning Pods to Nodes](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/)
- [Kubernetes — Pod Affinity and Anti-Affinity](https://kubernetes.io/docs/concepts/scheduling-eviction/assign-pod-node/#affinity-and-anti-affinity)
- [Kubernetes — Pod Topology Spread Constraints](https://kubernetes.io/docs/concepts/scheduling-eviction/topology-spread-constraints/)
- [Kubernetes — Taints and Tolerations](https://kubernetes.io/docs/concepts/scheduling-eviction/taint-and-toleration/)

## Kubernetes — armazenamento e configuração

- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [Kubernetes — Volumes / Local volumes](https://kubernetes.io/docs/concepts/storage/volumes/#local)
- [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)

## PostgreSQL

- [PostgreSQL — Replication settings](https://www.postgresql.org/docs/current/runtime-config-replication.html)
- [PostgreSQL — Log-Shipping Standby Servers / Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [PostgreSQL — `pg_basebackup`](https://www.postgresql.org/docs/current/app-pgbasebackup.html)
- [PostgreSQL — `pg_hba.conf`](https://www.postgresql.org/docs/current/auth-pg-hba-conf.html)

## Redis

- [Redis — Replication](https://redis.io/docs/latest/manual/replication/)
- [Redis — Persistence](https://redis.io/docs/latest/management/persistence/)
- [Redis — High availability with Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)

## Monitoramento

- [Prometheus — Overview](https://prometheus.io/docs/introduction/overview/)
- [Prometheus — First steps](https://prometheus.io/docs/introduction/first_steps/)
- [Grafana — Documentation](https://grafana.com/docs/grafana/latest/)
- [Grafana — Getting started](https://grafana.com/docs/grafana/latest/fundamentals/getting-started/)
- [kube-state-metrics — projeto oficial](https://github.com/kubernetes/kube-state-metrics)

## Rede, runtime e ambiente local

- [Flannel — projeto oficial](https://github.com/flannel-io/flannel)
- [containerd — documentação](https://containerd.io/docs/)
- [Docker — documentação](https://docs.docker.com/)
- [Minikube — documentação](https://minikube.sigs.k8s.io/docs/)
- [Minikube — `minikube start`](https://minikube.sigs.k8s.io/docs/commands/start/)

---

# Trabalho de Conclusão de Curso

Este repositório faz parte do desenvolvimento prático do TCC sobre avaliação de uma infraestrutura Kubernetes aplicada à execução automatizada de códigos.

O ambiente é utilizado para relacionar conceitos de:

```text
Online Judge
     +
Judge0
     +
Kubernetes
     +
filas
     +
balanceamento de carga
     +
escalabilidade
     +
persistência
     +
disponibilidade
```

com resultados obtidos em um cluster físico experimental.

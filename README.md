<p align="center">
  <img width="100%" alt="Judge0 no Kubernetes" src="https://github.com/user-attachments/assets/2fdb240a-262b-4137-8ef5-349ff836cb4f" />

</p>

<h1 align="center">Judge0 no Kubernetes</h1>

<p align="center">
  <strong>Escalabilidade, persistência, replicação e experimentos de disponibilidade em um cluster físico.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Kubernetes-Orquestração-326CE5?logo=kubernetes&logoColor=white" alt="Kubernetes">
  <img src="https://img.shields.io/badge/Judge0-Execução%20de%20código-2F80ED" alt="Judge0">
  <img src="https://img.shields.io/badge/Redis-Sentinel-DC382D?logo=redis&logoColor=white" alt="Redis Sentinel">
  <img src="https://img.shields.io/badge/PostgreSQL-Streaming%20Replication-4169E1?logo=postgresql&logoColor=white" alt="PostgreSQL">
  <img src="https://img.shields.io/badge/Prometheus%20%2B%20Grafana-Observabilidade-F46800?logo=prometheus&logoColor=white" alt="Prometheus e Grafana">
</p>

## Sobre o projeto

Este repositório reúne os manifests, scripts e registros experimentais utilizados no Trabalho de Conclusão de Curso:

> **Avaliação de uma Infraestrutura Kubernetes para Execução Automatizada de Códigos: Escalabilidade, Distribuição de Carga e Disponibilidade**

O estudo faz parte de um projeto na qual colocamos em prática o motor de execução judge0 da plataforma avaliadora de códigos em pleno funcionamento em um cluster Kubernetes físico e totalmente _self-hosted_. A plataforma web permanece fora do cluster e utiliza o Judge0 para receber, enfileirar, executar e consultar submissões de código.

O foco do projeto não é modificar a lógica do Judge0 ou da plataforma. O objetivo é avaliar, na prática, como a infraestrutura influencia:

- o recebimento concorrente de submissões;
- a distribuição dos trabalhos entre múltiplos Workers;
- o escalonamento horizontal com HPA;
- a persistência e a replicação de Redis e PostgreSQL;
- a recuperação diante da falha de Pods e nodes;
- a latência, a vazão, a taxa de sucesso e os limites do cluster.

## Destaques técnicos

- cluster físico com **1 control plane ARM** e **2 nodes AMD64**;
- duas réplicas da API distribuídas por **Pod Anti-Affinity**;
- Workers com `COUNT=2`, requests/limits e escala horizontal por HPA;
- PostgreSQL Primary/Replica por **streaming replication**;
- Redis com AOF, replicação e experimentos com **Redis Sentinel**;
- armazenamento por PV/PVC locais e política `Retain`;
- testes automatizados de carga, falha e recuperação;
- monitoramento com Prometheus, kube-state-metrics e Grafana;
- coleta de eventos, CPU, memória, criação de Pods e decisões do HPA.

## Arquitetura experimental

```text
                          cliente de carga
                                  |
                                  v
                       +---------------------+
                       | judge0-service      |
                       | Service / NodePort  |
                       +----------+----------+
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
                +-----------------+-----------------+
                |                                   |
                v                                   v
        +------------------+               +------------------+
        | Redis / Resque   |               | PostgreSQL       |
        | fila assíncrona  |               | persistência     |
        +--------+---------+               +---------+--------+
                 |                                   |
                 v                                   v
        +------------------+               +------------------+
        | Redis Replica    |               | PostgreSQL       |
        | + Sentinel       |               | Replica          |
        +------------------+               +------------------+
                 |
                 v
        +---------------------------+
        | Judge0 Workers            |
        | 4 a 10 Pods pelo HPA      |
        | COUNT=2 por Pod           |
        +-------------+-------------+
                      |
                      v
             compilação e execução
```

### Distribuição física

```text
srv-kube-master-cplane
└── Raspberry Pi / ARM
    └── control plane Kubernetes

srv-kube-worker-1 / AMD64
├── PostgreSQL Primary
├── Redis Replica
├── Judge0 API
└── Judge0 Workers

srv-kube-worker-2 / AMD64
├── PostgreSQL Replica
├── Redis Primary
├── Judge0 API
└── Judge0 Workers
```

A API e os Workers usam `nodeSelector` para arquitetura AMD64. As duas APIs utilizam anti-affinity obrigatória para evitar que sejam executadas no mesmo node.

## Configuração experimental de referência

| Componente | Configuração |
|---|---|
| Judge0 API | 2 réplicas, `RAILS_SERVER_PROCESSES=2`, `RAILS_MAX_THREADS=4` |
| Workers | mínimo 4 réplicas, máximo 10 pelo HPA |
| Paralelismo interno | `COUNT=2` por Worker |
| CPU do Worker | request `500m`, limit `1500m` |
| Memória do Worker | request `512Mi`, limit `2048Mi` |
| HPA | alvo de CPU igual a 100% do request |
| PostgreSQL | Primary + Replica por streaming replication |
| Redis | AOF, replicação e Sentinel avaliados experimentalmente |

## Resultados principais

### Paralelismo interno dos Workers

| COUNT | Execuções | Tempo | Vazão | Resultado |
|---:|---:|---:|---:|---|
| 1 | 200/200 | 70,470 s | 2,84 exec./s | Estável |
| 2 | 200/200 | 43,265 s | 4,62 exec./s | Melhor equilíbrio |
| 3 | 200/200 | 48,114 s | 4,16 exec./s | Estável |
| 4 | — | — | — | Instabilidade/OOM |

### Teste prolongado com HPA

O teste teve aproximadamente duas horas, 24 rodadas e seis níveis progressivos de carga. Cada nível foi repetido quatro vezes.

| Execuções por rodada | Concorrência | Accepted | Falhas POST | Vazão média | p95 médio |
|---:|---:|---:|---:|---:|---:|
| 600 | 10 | 2400/2400 | 0 | 7,97 exec./s | 1,64 s |
| 800 | 20 | 3200/3200 | 0 | 11,52 exec./s | 2,55 s |
| 1000 | 30 | 4000/4000 | 0 | 13,23 exec./s | 3,33 s |
| 1200 | 40 | 4800/4800 | 0 | 13,29 exec./s | 4,23 s |
| 1500 | 50 | 5997/6000 | 3 | 13,23 exec./s | 5,15 s |
| 2000 | 75 | 7147/8000 | 853 | 13,79 exec./s | 5,67 s |

Durante esse experimento:

- o HPA saiu do mínimo de 4 e chegou ao máximo de **10 réplicas**;
- a utilização registrada pelo HPA chegou a **279%** do objetivo;
- mesmo com 10 réplicas, houve períodos com CPU acima da meta;
- o `worker-1` chegou a aproximadamente **99% de CPU** e o `worker-2` a **96%**;
- os novos Pods passaram por `Pending → ContainerCreating → Running`;
- não foram observados eventos de `Insufficient cpu` nessa execução;
- a vazão entrou em um platô próximo de 13 execuções/s, enquanto a latência e as falhas aumentaram.

**Leitura do resultado:** 1200 execuções com concorrência 40 foram o maior nível concluído sem falhas em todas as repetições. O nível 1500/50 ainda obteve 99,95% de sucesso. Em 2000/75, a taxa de aceitação caiu para aproximadamente 89,34%, caracterizando uma região de saturação do ambiente avaliado.

### Testes de falha

Em três rodadas de 800 submissões, um node de execução foi reiniciado aproximadamente na metade do processamento, mantendo Redis e PostgreSQL no outro node. O cliente confirmou 2381 das 2400 submissões como `Accepted`, mostrando continuidade parcial com perda temporária de capacidade.

Em um cenário mais crítico, o node indisponível também hospedava Redis, PostgreSQL, uma API e parte dos Workers. A indisponibilidade dos componentes stateful comprometeu o recebimento de novas submissões, demonstrando que replicar apenas API e Workers não elimina todos os pontos únicos de falha.

## O que o projeto demonstra

1. **Mais paralelismo não produz ganho linear.** O melhor valor de `COUNT` depende dos recursos disponíveis.
2. **O HPA reage corretamente à CPU**, mas não cria capacidade física inexistente.
3. **Escalar Pods não resolve sozinho Redis e PostgreSQL.** Componentes stateful exigem replicação e failover próprios.
4. **Replicação não é sinônimo de alta disponibilidade.** A aplicação cliente também precisa localizar o novo Primary.
5. **A capacidade deve ser medida por vazão, latência e falhas**, e não apenas pelo número total de requisições processadas.

## Organização do repositório

```text
judge0-kubernetes/
├── judge0/
│   ├── config/
│   ├── db/
│   │   ├── primary/
│   │   └── replica/
│   ├── redis/
│   │   ├── primary/
│   │   ├── replica/
│   │   └── sentinel/
│   ├── deployments.yaml
│   ├── services.yaml
│   └── hpa.yaml
├── testes/
├── monitor/
├── replicacao/
├── docs/
└── README.md
```

## Implantação resumida

> Os manifests devem ser revisados conforme nodes, caminhos de volumes e credenciais do ambiente de destino.

```bash
# 1. Configurações e Secrets
kubectl get secret judge0-env
kubectl get secret vol-config

# 2. PostgreSQL
kubectl apply -f judge0/db/primary/
kubectl apply -f judge0/db/replica/

# 3. Redis
kubectl apply -f judge0/redis/primary/
kubectl apply -f judge0/redis/replica/
kubectl apply -f judge0/redis/sentinel/

# 4. API, Workers, Service e HPA
kubectl apply -f judge0/deployments.yaml
kubectl apply -f judge0/services.yaml
kubectl apply -f judge0/hpa.yaml

# 5. Estado geral
kubectl get pods -o wide
kubectl get svc
kubectl get hpa
kubectl get pv,pvc
```

<details>
<summary><strong>Validações rápidas</strong></summary>

### HPA e Workers

```bash
kubectl get hpa
kubectl describe hpa wk-judge0-hpa
kubectl top pods -l app=wk-judge0
```

### PostgreSQL Replica

```bash
kubectl exec deploy/db-replica -- \
  psql -U judge0 -d judge0 \
  -c "SELECT pg_is_in_recovery();"
```

### Redis

```bash
kubectl exec deploy/redis -- sh -c \
'REDISCLI_AUTH="$REDIS_PASSWORD" redis-cli INFO replication'
```

### Distribuição da API

```bash
kubectl get pods -l app=srv-judge0 -o wide
```

</details>

## Credenciais e arquivos sensíveis

Não versione:

- `.env` real;
- `judge0.conf` real;
- Secrets exportados;
- kubeconfig;
- certificados e chaves privadas;
- dumps de banco;
- logs contendo tokens ou dados internos.

Mantenha apenas modelos como `.env.example` e `judge0.conf.example`.

## Limitações e próximos passos

- os PVs locais permanecem vinculados fisicamente aos nodes;
- PostgreSQL possui replicação, mas a promoção automática ainda precisa ser implementada;
- o failover do Redis foi avaliado, porém a descoberta automática do novo Primary pelo cliente Judge0 ainda precisa ser concluída e validada ponta a ponta;
- o control plane está concentrado em um único node ARM com memória limitada;
- a disponibilidade temporal formal ainda precisa ser medida em uma janela definida;
- os resultados representam este cluster e não devem ser tratados como limites universais do Judge0 ou do Kubernetes.
- a limitação do controlplane e a falta de mais uma máquina até o momento impediu aplicar a alta disponibilidade

## Tecnologias

`Kubernetes` · `Docker` · `containerd` · `Judge0` · `Redis` · `Redis Sentinel` · `PostgreSQL` · `Prometheus` · `Grafana` · `Python` · `Bash` · `Linux`

## Referências principais

- [Judge0 — repositório oficial](https://github.com/judge0/judge0)
- [Judge0 — documentação da API](https://ce.judge0.com/)
- [Kubernetes — Horizontal Pod Autoscaling](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/)
- [Kubernetes — Deployments](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/)
- [Kubernetes — Services](https://kubernetes.io/docs/concepts/services-networking/service/)
- [Kubernetes — Persistent Volumes](https://kubernetes.io/docs/concepts/storage/persistent-volumes/)
- [PostgreSQL — Streaming Replication](https://www.postgresql.org/docs/current/warm-standby.html)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Sentinel](https://redis.io/docs/latest/operate/oss_and_stack/management/sentinel/)

## Autor

**Paulo Henrique da Rosa**  
Tecnologia em Análise e Desenvolvimento de Sistemas — IFPR

- [LinkedIn](https://www.linkedin.com/in/hxpaulo/)
- [Portfólio](https://paulodarosa.com)

# RESULTADOS

Este arquivo reúne os resultados dos testes práticos realizados com o Judge0 em Kubernetes.

O objetivo é manter um histórico dos experimentos, comparar diferentes quantidades de réplicas dos Workers e registrar observações metodológicas importantes para utilização posterior no TCC.

---

# Ambiente de teste

Configuração utilizada nos testes atuais:

```text
Cluster: Minikube
Driver: Docker
Judge0 Server: 1 réplica
Redis: 1 réplica
PostgreSQL: 1 réplica
COUNT por Worker: 1
Linguagem: Python 3.8.1
language_id: 71
Quantidade de submissões por teste: 200
```

Código submetido:

```python
print("Teste Kubernetes")
```

Endpoint utilizado:

```text
POST /submissions?base64_encoded=false
```

As submissões foram enviadas de forma assíncrona. Cada requisição retorna um token e, após o envio do lote, o script consulta os tokens até que todas as submissões tenham atingido um estado final.

O tempo registrado representa o período entre o início do envio do lote e a conclusão das submissões consultadas pelo script.

---

# Teste de escalabilidade horizontal

## Objetivo

Avaliar o impacto do aumento da quantidade de Pods Worker na capacidade de processamento do Judge0.

A principal variável alterada foi a quantidade de réplicas do Deployment:

```text
wk-judge0
```

Foram avaliados os cenários:

```text
1 Worker
2 Workers
3 Workers
```

Todos os Workers permaneceram com:

```text
COUNT=1
```

---

# Cenário 1 - 1 Worker

Comando:

```powershell
kubectl scale deployment wk-judge0 --replicas=1
```

Foram executadas três rodadas com 200 submissões utilizando uma única réplica do Worker.

## Rodada 1

```text
Submissões:    200
Concluídas:    200
Tempo total:   92,720 s
Throughput:    2,16 submissões/s
```

## Rodada 2

```text
Submissões:    200
Concluídas:    200
Tempo total:   94,979 s
Throughput:    2,11 submissões/s
```

## Rodada 3

```text
Submissões:    200
Concluídas:    200
Tempo total:   91,435 s
Throughput:    2,19 submissões/s
```

## Resumo

| Rodada | Tempo total | Throughput | Situação |
|---:|---:|---:|---|
| 1 | 92,720 s | 2,16 sub/s | Válida |
| 2 | 94,979 s | 2,11 sub/s | Válida |
| 3 | 91,435 s | 2,19 sub/s | Válida |

### Média das três execuções

```text
Tempo médio:          93.045 s
Throughput médio:     2.15 submissões/s
```

Em notação com vírgula:

```text
Tempo médio:          93,045 s
Throughput médio:     2,15 submissões/s
```

As três execuções ficaram próximas entre si, indicando boa consistência neste cenário.

---

# Cenário 2 - 2 Workers

Comando:

```powershell
kubectl scale deployment wk-judge0 --replicas=2
```

## Rodada 1

```text
Submissões:    200
Concluídas:    200
Tempo total:   70,550 s
Throughput:    2,83 submissões/s
```

## Rodada 2

```text
Submissões:    200
Concluídas:    200
Tempo total:   71,653 s
Throughput:    2,79 submissões/s
```

## Rodada 3

Durante o envio das submissões ocorreu o erro:

```text
Invoke-RestMethod:
A conexão subjacente estava fechada:
Uma conexão que deveria ser mantida ativa foi fechada pelo servidor.
```

Apesar disso, o script terminou apresentando:

```text
Concluídas:    200
Tempo total:   65,390 s
Throughput:    3,06 submissões/s
```

### Atenção metodológica

Esta terceira rodada **não deve ser utilizada como resultado oficial ainda**.

O motivo é que, quando uma chamada `Invoke-RestMethod` falha dentro do `for`, o script atual continua sua execução. Existe a possibilidade de o valor anterior da variável `$r` permanecer disponível e seu token ser adicionado novamente ao array.

Assim, o fato de o script mostrar:

```text
200/200
```

não garante, neste caso específico, que 200 submissões distintas tenham sido criadas e concluídas.

A rodada deve ser repetida posteriormente.

## Resumo

| Rodada | Tempo total | Throughput | Situação |
|---:|---:|---:|---|
| 1 | 70,550 s | 2,83 sub/s | Válida |
| 2 | 71,653 s | 2,79 sub/s | Válida |
| 3 | 65,390 s | 3,06 sub/s | Válida |

### Média usando apenas as rodadas válidas

```text
Tempo médio:          71.102 s
Throughput médio:     2.81 submissões/s
```

Em notação com vírgula:

```text
Tempo médio:          71.102 s
Throughput médio:     2.81 submissões/s
```

A média acima considera somente as Rodadas 1 e 2.

### Referência informativa incluindo a rodada com erro

Se a terceira rodada fosse incluída apenas para comparação informal:

```text
Tempo médio:          69.198 s
Throughput médio:     2.89 submissões/s
```

Esses valores **não devem ser utilizados como consolidação final** até a rodada ser refeita.

---

# Cenário 3 - 3 Workers

Comando:

```powershell
kubectl scale deployment wk-judge0 --replicas=3
```

## Rodada 1

```text
Submissões:    200
Concluídas:    200
Tempo total:   59,892 s
Throughput:    3,34 submissões/s
```

## Rodada 2

```text
Submissões:    200
Concluídas:    200
Tempo total:   67,479 s
Throughput:    2,96 submissões/s
```

## Rodada 3

```text
Submissões:    200
Concluídas:    200
Tempo total:   66,351 s
Throughput:    3,01 submissões/s
```

## Resumo

| Rodada | Tempo total | Throughput | Situação |
|---:|---:|---:|---|
| 1 | 59,892 s | 3,34 sub/s | Válida |
| 2 | 67,479 s | 2,96 sub/s | Válida |
| 3 | 66,351 s | 3,01 sub/s | Válida |

### Média das três execuções

```text
Tempo médio:          64.574 s
Throughput médio:     3.10 submissões/s
```

Em notação com vírgula:

```text
Tempo médio:          64,574 s
Throughput médio:     3,10 submissões/s
```

---

# Comparação atual

A comparação abaixo utiliza as três rodadas válidas de 1 Worker, as duas rodadas válidas de 2 Workers e as três rodadas válidas de 3 Workers.

| Workers | Rodadas válidas | Tempo médio | Throughput médio |
|---:|---:|---:|---:|
| 1 | 3 | 93.045 s | 2.15 sub/s |
| 2 | 2 | 71.102 s | 2.81 sub/s |
| 3 | 3 | 64.574 s | 3.10 sub/s |

---

# Ganhos preliminares observados

## 1 Worker para 2 Workers

Comparando a média das três rodadas de 1 Worker com a média das duas rodadas válidas de 2 Workers:

```text
1 Worker:   93.045 s
2 Workers:  71.102 s
```

A redução média observada no tempo total foi de aproximadamente:

```text
23.6%
```

O throughput médio passou de:

```text
2.15 sub/s
```

para:

```text
2.81 sub/s
```

representando um aumento aproximado de:

```text
30.5%
```

---

## 2 Workers para 3 Workers

Comparando a média das duas rodadas válidas de 2 Workers com a média das três rodadas de 3 Workers:

```text
2 Workers:  71.102 s
3 Workers:  64.574 s
```

A redução média observada no tempo total foi de aproximadamente:

```text
9.2%
```

O throughput médio passou de:

```text
2.81 sub/s
```

para:

```text
3.10 sub/s
```

representando um aumento aproximado de:

```text
10.4%
```

---

## 1 Worker para 3 Workers

Comparando as médias dos cenários com 1 e 3 Workers:

```text
1 Worker:   93.045 s
3 Workers:  64.574 s
```

A redução média observada no tempo total foi de aproximadamente:

```text
30.6%
```

O throughput médio passou de:

```text
2.15 sub/s
```

para:

```text
3.10 sub/s
```

representando um aumento aproximado de:

```text
44.1%
```

---

# Interpretação preliminar

Os resultados continuam indicando que o aumento do número de Workers melhora a capacidade de processamento do Judge0 no ambiente testado.

O cenário com 3 Workers apresentou, nas três rodadas válidas, tempo médio inferior à média das três execuções com 1 Worker.

Entretanto, também existe uma variação perceptível entre as execuções.

No cenário com 3 Workers, por exemplo:

```text
59,892 s
67,479 s
66,351 s
```

Isso mostra por que uma única execução não é suficiente para caracterizar o desempenho do ambiente.

A diferença pode estar relacionada a diversos fatores do laboratório, como:

- utilização momentânea do host;
- Docker Desktop;
- Minikube;
- escalonamento de CPU;
- concorrência entre containers;
- Judge0 Server;
- Redis;
- PostgreSQL;
- rede interna do cluster;
- processos do próprio Windows.

Por esse motivo, a utilização de múltiplas rodadas é necessária para reduzir o peso de resultados pontuais.

---

# Observação importante sobre escalabilidade

Os resultados não indicam crescimento linear de desempenho.

Adicionar mais Workers aumenta a capacidade de processamento, porém as réplicas continuam compartilhando os mesmos recursos físicos disponíveis no host.

A arquitetura pode ser representada de forma simplificada por:

```text
                 Minikube
                    |
          recursos físicos limitados
                    |
          +---------+---------+
          |         |         |
       Worker 1  Worker 2  Worker 3
```

Além dos Workers, a execução depende de outros componentes:

```text
Cliente
   |
   v
Judge0 Server
   |
   v
Redis
   |
   v
Workers
   |
   v
PostgreSQL / resultado
```

Portanto, em determinado momento, outro componente ou a própria infraestrutura física pode se tornar o gargalo.

---

# Problema identificado no script de teste

Para as próximas execuções, o script deve tratar erros de envio explicitamente.

Uma abordagem recomendada é utilizar:

```powershell
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
    Write-Host "Erro ao enviar submissão $i"
}
```

Além disso, antes de iniciar a etapa de consulta, deve ser verificado:

```powershell
$tokens.Count
```

O valor esperado para o teste atual é:

```text
200
```

Também é útil verificar quantos tokens são distintos:

```powershell
($tokens | Select-Object -Unique).Count
```

O resultado também deve ser:

```text
200
```

Isso evita considerar uma rodada como válida caso tenha ocorrido duplicação de token após uma falha de conexão.

---

# Situação atual dos testes

```text
1 Worker
[x] Rodada 1
[x] Rodada 2
[x] Rodada 3

2 Workers
[x] Rodada 1
[x] Rodada 2
[x] Rodada 3

3 Workers
[x] Rodada 1
[x] Rodada 2
[x] Rodada 3
```

---

# Próximos passos

* Calcular a média final com três rodadas válidas para cada cenário.
* Comparar tempo total, throughput e variação entre as execuções.
* Posteriormente realizar o teste de autorrecuperação durante uma carga.
* Em uma etapa futura, repetir os mesmos experimentos em infraestrutura distribuída para comparar com o Minikube local.

---

# Modelo para novos registros

```markdown
## Rodada X

Workers:

Submissões enviadas:

Tokens recebidos:

Tokens únicos:

Submissões concluídas:

Erros de envio:

Tempo total:

Throughput:

Observações:
```

---

# Observação metodológica

Para que os resultados possam ser utilizados de maneira mais confiável no TCC, todos os cenários devem ser executados sob condições semelhantes.

Devem permanecer constantes:

- quantidade de submissões;
- código submetido;
- linguagem utilizada;
- configuração do Judge0 Server;
- configuração do Redis;
- configuração do PostgreSQL;
- `COUNT` dos Workers;
- recursos destinados ao Minikube;
- método de geração e consulta da carga.

A variável principal alterada entre os cenários deve ser a quantidade de réplicas do Deployment `wk-judge0`.

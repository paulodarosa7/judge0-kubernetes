#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   ./trocar_rails.sh 2
#   ./trocar_rails.sh 2 default
#
# Argumentos:
#   $1 = novo valor de RAILS_MAX_THREADS
#   $2 = namespace (opcional, padrao: default)

THREADS="${1:-}"
NAMESPACE="${2:-default}"

CONF="/opt/judge0-kubernetes/judge0/config/judge0.conf"
SECRET_CONF="vol-config"
SECRET_ENV="judge0-env"
DEPLOYMENT="srv-judge0"
LABEL="app=srv-judge0"

if [[ -z "$THREADS" ]]; then
  echo "Uso: $0 <RAILS_MAX_THREADS> [namespace]"
  echo "Exemplo: $0 2"
  exit 1
fi

if ! [[ "$THREADS" =~ ^[1-9][0-9]*$ ]]; then
  echo "Erro: RAILS_MAX_THREADS deve ser um numero inteiro maior que zero."
  exit 1
fi

if [[ ! -f "$CONF" ]]; then
  echo "Erro: arquivo de configuracao nao encontrado:"
  echo "  $CONF"
  exit 1
fi

echo "=================================================="
echo "Judge0 - alteracao de RAILS_MAX_THREADS"
echo "=================================================="
echo "Namespace : $NAMESPACE"
echo "Arquivo   : $CONF"
echo "Deployment: $DEPLOYMENT"
echo "Novo valor: $THREADS"
echo "=================================================="

echo
echo "[1/7] Valor atual:"
grep '^RAILS_MAX_THREADS=' "$CONF" || \
  echo "RAILS_MAX_THREADS nao encontrado no arquivo."

echo
echo "[2/7] Alterando RAILS_MAX_THREADS no judge0.conf..."
if grep -q '^RAILS_MAX_THREADS=' "$CONF"; then
  sed -i "s/^RAILS_MAX_THREADS=.*/RAILS_MAX_THREADS=$THREADS/" "$CONF"
else
  echo "RAILS_MAX_THREADS=$THREADS" >> "$CONF"
fi

echo "Arquivo local:"
grep '^RAILS_MAX_THREADS=' "$CONF"

echo
echo "[3/7] Atualizando Secret $SECRET_CONF..."
kubectl create secret generic "$SECRET_CONF" \
  -n "$NAMESPACE" \
  --from-file=judge0.conf="$CONF" \
  --dry-run=client -o yaml | kubectl apply -f -

# Mantem o Secret de variaveis sincronizado com o mesmo arquivo.
# A API atual usa /judge0.conf via vol-config, mas isso evita divergencia
# entre os dois Secrets usados pelo ambiente.
echo
echo "[4/7] Sincronizando Secret $SECRET_ENV..."
kubectl create secret generic "$SECRET_ENV" \
  -n "$NAMESPACE" \
  --from-env-file="$CONF" \
  --dry-run=client -o yaml | kubectl apply -f -

echo
echo "[5/7] Reiniciando somente a API Judge0..."
kubectl rollout restart deployment/"$DEPLOYMENT" -n "$NAMESPACE"

echo
echo "[6/7] Aguardando rollout..."
kubectl rollout status deployment/"$DEPLOYMENT" \
  -n "$NAMESPACE" \
  --timeout=300s

echo
echo "Aguardando Pods antigos do RollingUpdate serem removidos..."

DESIRED=$(kubectl get deployment "$DEPLOYMENT" \
  -n "$NAMESPACE" \
  -o jsonpath='{.spec.replicas}')

for i in {1..60}; do
  ATIVOS=$(kubectl get pods \
    -n "$NAMESPACE" \
    -l "$LABEL" \
    --field-selector=status.phase=Running \
    -o name | wc -l)

  if [[ "$ATIVOS" -eq "$DESIRED" ]]; then
    break
  fi

  sleep 2
done

echo
echo "[7/7] Validando /judge0.conf em todas as replicas da API..."

PODS=$(kubectl get pods \
  -n "$NAMESPACE" \
  -l "$LABEL" \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}')

if [[ -z "$PODS" ]]; then
  echo "Erro: nenhum Pod da API encontrado com label '$LABEL'."
  exit 1
fi

echo
ERRO=0

while IFS= read -r POD; do
  [[ -z "$POD" ]] && continue

  VALUE=$(kubectl exec -n "$NAMESPACE" "$POD" -- \
    sh -c "grep '^RAILS_MAX_THREADS=' /judge0.conf 2>/dev/null | head -n1" || true)

  echo "$POD -> ${VALUE:-NAO_ENCONTRADO}"

  if [[ "$VALUE" != "RAILS_MAX_THREADS=$THREADS" ]]; then
    ERRO=1
  fi
done <<< "$PODS"

echo
if [[ "$ERRO" -ne 0 ]]; then
  echo "ERRO: pelo menos uma replica nao carregou RAILS_MAX_THREADS=$THREADS."
  exit 1
fi

echo "=================================================="
echo "Alteracao concluida."
echo "RAILS_MAX_THREADS aplicado: $THREADS"
echo "=================================================="

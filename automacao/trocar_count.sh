#!/usr/bin/env bash
set -euo pipefail

# Uso:
#   ./trocar_count.sh 2
#   ./trocar_count.sh 2 default
#
# Argumentos:
#   $1 = novo valor de COUNT
#   $2 = namespace (opcional, padrao: default)

COUNT="${1:-}"
NAMESPACE="${2:-default}"

CONF="/opt/judge0-kubernetes/judge0/config/judge0.conf"
SECRET_CONF="vol-config"
SECRET_ENV="judge0-env"
DEPLOYMENT="wk-judge0"
LABEL="app=wk-judge0"

if [[ -z "$COUNT" ]]; then
  echo "Uso: $0 <COUNT> [namespace]"
  echo "Exemplo: $0 2"
  exit 1
fi

if ! [[ "$COUNT" =~ ^[1-9][0-9]*$ ]]; then
  echo "Erro: COUNT deve ser um numero inteiro maior que zero."
  exit 1
fi

if [[ ! -f "$CONF" ]]; then
  echo "Erro: arquivo de configuracao nao encontrado:"
  echo "  $CONF"
  exit 1
fi

echo "=================================================="
echo "Judge0 - alteracao de COUNT"
echo "=================================================="
echo "Namespace : $NAMESPACE"
echo "Arquivo   : $CONF"
echo "Deployment: $DEPLOYMENT"
echo "Novo COUNT: $COUNT"
echo "=================================================="

echo
echo "[1/7] Valor atual:"
grep '^COUNT=' "$CONF" || echo "COUNT nao encontrado no arquivo."

echo
echo "[2/7] Alterando COUNT no judge0.conf..."
if grep -q '^COUNT=' "$CONF"; then
  sed -i "s/^COUNT=.*/COUNT=$COUNT/" "$CONF"
else
  echo "COUNT=$COUNT" >> "$CONF"
fi

echo "Arquivo local:"
grep '^COUNT=' "$CONF"

echo
echo "[3/7] Atualizando Secret $SECRET_CONF..."
kubectl create secret generic "$SECRET_CONF" \
  -n "$NAMESPACE" \
  --from-file=judge0.conf="$CONF" \
  --dry-run=client -o yaml | kubectl apply -f -

echo
echo "[4/7] Atualizando Secret $SECRET_ENV..."
kubectl create secret generic "$SECRET_ENV" \
  -n "$NAMESPACE" \
  --from-env-file="$CONF" \
  --dry-run=client -o yaml | kubectl apply -f -

echo
echo "[5/7] Reiniciando somente os workers..."
kubectl rollout restart deployment/"$DEPLOYMENT" -n "$NAMESPACE"

echo
echo "[6/7] Aguardando rollout..."
kubectl rollout status deployment/"$DEPLOYMENT" \
  -n "$NAMESPACE" \
  --timeout=300s

echo
echo "[7/7] Validando configuracao nos Pods atuais..."

sleep 5

PODS=$(kubectl get pods \
  -n "$NAMESPACE" \
  -l "$LABEL" \
  -o go-template='{{range .items}}{{if not .metadata.deletionTimestamp}}{{.metadata.name}}{{"\n"}}{{end}}{{end}}')

if [[ -z "$PODS" ]]; then
  echo "Erro: nenhum Pod ativo encontrado com label '$LABEL'."
  exit 1
fi

echo
ERRO=0

while IFS= read -r POD; do
  [[ -z "$POD" ]] && continue

  CONF_VALUE=$(kubectl exec -n "$NAMESPACE" "$POD" -- \
    sh -c "grep '^COUNT=' /judge0.conf 2>/dev/null | head -n1" || true)

  ENV_VALUE=$(kubectl exec -n "$NAMESPACE" "$POD" -- \
    printenv COUNT 2>/dev/null || true)

  echo "$POD"
  echo "  /judge0.conf : ${CONF_VALUE:-NAO_ENCONTRADO}"
  echo "  env COUNT    : ${ENV_VALUE:-NAO_ENCONTRADO}"

  if [[ "$CONF_VALUE" != "COUNT=$COUNT" ]]; then
    ERRO=1
  fi
done <<< "$PODS"

echo

if [[ "$ERRO" -ne 0 ]]; then
  echo "ERRO: pelo menos um worker ativo nao carregou COUNT=$COUNT."
  exit 1
fi

echo "=================================================="
echo "Alteracao concluida."
echo "COUNT aplicado: $COUNT"
echo "=================================================="

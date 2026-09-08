#!/bin/bash

# Formas de uso:
# chmod +x trocar_count.sh
# ./trocar_count.sh 2 (ou qualquer outro número de workers desejado)
# Forma automatizada de alterar o COUNT no config/judge0.conf e reiniciar o wk-judge0.
# Essa forma altera as réplicas de paralelismo nativas Judge0
# O COUNT é o número de workers que processam submissões de código em paralelo e
# Neste contexto, o COUNT é o número de réplicas paralelas dentro de um único POD do wk-judge0.

set -e

if [ -z "$1" ]; then
  echo "Uso: $0 <COUNT>"
  echo "Exemplo: $0 2"
  exit 1
fi

COUNT=$1

echo "Alterando COUNT para $COUNT..."

sed -i "s/^COUNT=.*/COUNT=$COUNT/" config/judge0.conf

echo "Atualizando Secret vol-config..."
kubectl create secret generic vol-config \
  --from-file=judge0.conf=config/judge0.conf \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Atualizando Secret judge0-env..."
kubectl create secret generic judge0-env \
  --from-env-file=config/judge0.conf \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Reiniciando wk-judge0..."
kubectl rollout restart deployment/wk-judge0

echo "Aguardando rollout..."
kubectl rollout status deployment/wk-judge0

sleep 10s

echo
echo "Configuracao aplicada:"
kubectl exec deployment/wk-judge0 -- grep '^COUNT=' /judge0.conf

echo
echo "Pods atuais:"
kubectl get pods -l app=wk-judge0
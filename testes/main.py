# SCRIPT DE TESTES
# nessesário: pip install requests
# python main.py

import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_URL = "http://192.168.10.71:30000"

TOTAL = 200
CONCURRENCY = 20

payload = {
    "source_code": 'print("Teste Kubernetes")',
    "language_id": 71
}

tokens = []
erros = []

inicio = time.time()

def enviar():
    try:
        r = requests.post(
            f"{BASE_URL}/submissions?base64_encoded=false",
            json=payload,
            timeout=30
        )

        r.raise_for_status()

        token = r.json().get("token")

        if not token:
            raise Exception("Resposta sem token")

        return token

    except Exception as e:
        return e


print(f"Enviando {TOTAL} submissões...")
print(f"Concorrência: {CONCURRENCY}")

with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:

    futures = [
        executor.submit(enviar)
        for _ in range(TOTAL)
    ]

    for future in as_completed(futures):

        resultado = future.result()

        if isinstance(resultado, Exception):
            erros.append(str(resultado))
        else:
            tokens.append(resultado)


tempo_envio = time.time() - inicio

print()
print(f"Aceitas: {len(tokens)}/{TOTAL}")
print(f"Erros:   {len(erros)}")
print(f"Tempo de envio: {tempo_envio:.2f}s")


pendentes = set(tokens)
concluidos = {}

while pendentes:

    for token in list(pendentes):

        try:

            r = requests.get(
                f"{BASE_URL}/submissions/{token}",
                timeout=10
            )

            if r.ok:

                dados = r.json()

                if dados["status"]["id"] > 2:

                    concluidos[token] = dados["status"]["description"]
                    pendentes.remove(token)

        except Exception:
            pass

    print(
        f"\rConcluídos: {len(concluidos)}/{len(tokens)}",
        end="",
        flush=True
    )

    time.sleep(0.3)


fim = time.time()
tempo_total = fim - inicio

print()
print()
print("================================")
print("RESULTADO")
print("================================")
print(f"Solicitadas : {TOTAL}")
print(f"Aceitas     : {len(tokens)}")
print(f"Concluídas  : {len(concluidos)}")
print(f"Erros       : {len(erros)}")
print(f"Envio       : {tempo_envio:.3f}s")
print(f"Tempo total : {tempo_total:.3f}s")
print(f"Throughput  : {len(concluidos)/tempo_total:.2f} sub/s")
print("================================")
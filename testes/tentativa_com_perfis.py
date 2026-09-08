#!/usr/bin/env python3
"""
Teste de carga realista para Judge0.

Simula:
- varios alunos;
- varias tentativas por aluno;
- varios casos de teste por problema;
- cada caso de teste vira uma submissao separada no Judge0.

Exemplo padrao:
50 alunos x 1 tentativa x 10 casos = 500 execucoes Judge0.

Uso:
    python3 teste_carga_realista.py

Exemplo:
    python3 teste_carga_realista.py \
        --url http://192.168.10.71:30000 \
        --alunos 50 \
        --tentativas 1 \
        --casos 10 \
        --concorrencia 30
"""

import argparse
import concurrent.futures
import json
import math
import statistics
import threading
import time
from collections import Counter

import requests


STATUS = {
    1: "In Queue",
    2: "Processing",
    3: "Accepted",
    4: "Wrong Answer",
    5: "Time Limit Exceeded",
    6: "Compilation Error",
    7: "Runtime Error (SIGSEGV)",
    8: "Runtime Error (SIGXFSZ)",
    9: "Runtime Error (SIGFPE)",
    10: "Runtime Error (SIGABRT)",
    11: "Runtime Error (NZEC)",
    12: "Runtime Error (Other)",
    13: "Internal Error",
    14: "Exec Format Error",
}

_thread_local = threading.local()
http_counter = Counter()
counter_lock = threading.Lock()


def get_session():
    if not hasattr(_thread_local, "session"):
        s = requests.Session()
        s.headers.update({"Content-Type": "application/json"})
        _thread_local.session = s
    return _thread_local.session


def count_http(kind):
    with counter_lock:
        http_counter[kind] += 1


def percentile(values, p):
    if not values:
        return 0.0
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return xs[int(k)]
    return xs[f] * (c - k) + xs[c] * (k - f)


CODIGO_LEVE = """a, b = map(int, input().split())
print(a + b)
"""

CODIGO_CPU = """n = int(input())
s = 0
for i in range(n):
    s = (s + i) % 1000000007
print(s)
"""

CODIGO_MEMORIA = """n = int(input())
dados = list(range(n))
print(len(dados), dados[0], dados[-1])
"""


def gerar_caso(numero, perfil):
    """Gera source_code, stdin e expected_output para um caso."""
    if perfil == "leve":
        a = numero
        b = numero * 2
        return {
            "numero": numero,
            "perfil": "leve",
            "source_code": CODIGO_LEVE,
            "stdin": f"{a} {b}\n",
            "expected_output": f"{a + b}\n",
        }

    if perfil == "cpu":
        # Carga CPU-bound deterministica.
        # ~1 milhao de iteracoes Python por submissao.
        n = 1_000_000 + (numero % 10) * 10_000
        esperado = (n * (n - 1) // 2) % 1_000_000_007
        return {
            "numero": numero,
            "perfil": "cpu",
            "source_code": CODIGO_CPU,
            "stdin": f"{n}\n",
            "expected_output": f"{esperado}\n",
        }

    if perfil == "memoria":
        # Aloca cerca de 1 milhao de inteiros por submissao.
        n = 1_000_000 + (numero % 5) * 20_000
        return {
            "numero": numero,
            "perfil": "memoria",
            "source_code": CODIGO_MEMORIA,
            "stdin": f"{n}\n",
            "expected_output": f"{n} 0 {n - 1}\n",
        }

    raise ValueError(f"Perfil desconhecido: {perfil}")


def gerar_casos(qtd, perfil):
    casos = []
    for i in range(1, qtd + 1):
        perfil_caso = perfil
        if perfil == "misto":
            perfil_caso = ("leve", "cpu", "memoria")[(i - 1) % 3]
        casos.append(gerar_caso(i, perfil_caso))
    return casos


def criar_submissao(base_url, language_id, payload, request_timeout):
    session = get_session()
    url = f"{base_url.rstrip('/')}/submissions?base64_encoded=false&wait=false"

    inicio = time.perf_counter()
    try:
        count_http("POST")
        r = session.post(
            url,
            data=json.dumps(payload),
            timeout=request_timeout,
        )
        elapsed = time.perf_counter() - inicio

        if r.status_code not in (200, 201):
            return {
                "ok": False,
                "fase": "POST",
                "http_status": r.status_code,
                "erro": r.text[:300],
                "post_time": elapsed,
            }

        data = r.json()
        token = data.get("token")
        if not token:
            return {
                "ok": False,
                "fase": "POST",
                "http_status": r.status_code,
                "erro": "Resposta sem token",
                "post_time": elapsed,
            }

        return {
            "ok": True,
            "token": token,
            "post_time": elapsed,
        }

    except requests.RequestException as exc:
        return {
            "ok": False,
            "fase": "POST",
            "erro": str(exc),
            "post_time": time.perf_counter() - inicio,
        }


def aguardar_resultado(base_url, token, poll_interval, submission_timeout, request_timeout):
    session = get_session()
    url = (
        f"{base_url.rstrip('/')}/submissions/{token}"
        "?base64_encoded=false"
        "&fields=token,status,time,memory,wall_time,exit_code,message"
    )

    inicio = time.perf_counter()
    polls = 0

    while True:
        decorrido = time.perf_counter() - inicio
        if decorrido >= submission_timeout:
            return {
                "timeout": True,
                "status_id": None,
                "status": "TIMEOUT DE POLLING",
                "polls": polls,
                "execution_wait": decorrido,
            }

        try:
            count_http("GET")
            polls += 1
            r = session.get(url, timeout=request_timeout)

            if r.status_code != 200:
                time.sleep(poll_interval)
                continue

            data = r.json()
            status = data.get("status") or {}
            status_id = status.get("id")

            if status_id is not None and status_id > 2:
                return {
                    "timeout": False,
                    "status_id": status_id,
                    "status": status.get("description") or STATUS.get(status_id, str(status_id)),
                    "polls": polls,
                    "execution_wait": time.perf_counter() - inicio,
                    "judge_time": data.get("time"),
                    "memory": data.get("memory"),
                    "wall_time": data.get("wall_time"),
                    "exit_code": data.get("exit_code"),
                    "message": data.get("message"),
                }

        except requests.RequestException:
            pass

        time.sleep(poll_interval)


def executar_trabalho(job, args):
    payload = {
        "source_code": job["source_code"],
        "language_id": args.language_id,
        "stdin": job["stdin"],
        "expected_output": job["expected_output"],
    }

    total_inicio = time.perf_counter()

    criado = criar_submissao(
        args.url,
        args.language_id,
        payload,
        args.request_timeout,
    )

    if not criado["ok"]:
        return {
            **job,
            **criado,
            "total_time": time.perf_counter() - total_inicio,
        }

    resultado = aguardar_resultado(
        args.url,
        criado["token"],
        args.poll_interval,
        args.submission_timeout,
        args.request_timeout,
    )

    return {
        **job,
        **criado,
        **resultado,
        "total_time": time.perf_counter() - total_inicio,
    }


def construir_jobs(alunos, tentativas, casos, perfil):
    casos_base = gerar_casos(casos, perfil)
    jobs = []

    for aluno in range(1, alunos + 1):
        for tentativa in range(1, tentativas + 1):
            for caso in casos_base:
                jobs.append(
                    {
                        "aluno": aluno,
                        "tentativa": tentativa,
                        "caso": caso["numero"],
                        "perfil": caso["perfil"],
                        "source_code": caso["source_code"],
                        "stdin": caso["stdin"],
                        "expected_output": caso["expected_output"],
                    }
                )

    return jobs


def main():
    parser = argparse.ArgumentParser(
        description="Teste de carga realista para Judge0"
    )
    parser.add_argument(
        "--url",
        default="http://192.168.10.71:30000",
        help="URL base do Judge0",
    )
    parser.add_argument("--alunos", type=int, default=50)
    parser.add_argument("--tentativas", type=int, default=1)
    parser.add_argument("--casos", type=int, default=10)
    parser.add_argument("--concorrencia", type=int, default=30)
    parser.add_argument("--language-id", type=int, default=71)
    parser.add_argument("--poll-interval", type=float, default=0.5)
    parser.add_argument("--submission-timeout", type=float, default=120.0)
    parser.add_argument("--request-timeout", type=float, default=10.0)
    parser.add_argument(
        "--perfil",
        choices=["leve", "cpu", "memoria", "misto"],
        default="leve",
        help="Perfil da submissao: leve, cpu, memoria ou misto (padrao: leve)",
    )
    args = parser.parse_args()

    jobs = construir_jobs(
        args.alunos,
        args.tentativas,
        args.casos,
        args.perfil,
    )
    total_execucoes = len(jobs)

    print("=" * 72)
    print("TESTE DE CARGA REALISTA - JUDGE0")
    print("=" * 72)
    print(f"URL                : {args.url}")
    print(f"Perfil             : {args.perfil}")
    print(f"Alunos             : {args.alunos}")
    print(f"Tentativas/aluno   : {args.tentativas}")
    print(f"Casos/tentativa    : {args.casos}")
    print(f"Execucoes Judge0   : {total_execucoes}")
    print(f"Concorrencia       : {args.concorrencia}")
    print()
    print(
        f"Carga simulada = {args.alunos} alunos x "
        f"{args.tentativas} tentativa(s) x "
        f"{args.casos} caso(s) = {total_execucoes} execucoes"
    )
    print("=" * 72)
    print()

    resultados = []
    inicio_global = time.perf_counter()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.concorrencia
    ) as executor:
        futuros = [
            executor.submit(executar_trabalho, job, args)
            for job in jobs
        ]

        concluidos = 0

        for futuro in concurrent.futures.as_completed(futuros):
            resultado = futuro.result()
            resultados.append(resultado)
            concluidos += 1

            if concluidos % 10 == 0 or concluidos == total_execucoes:
                print(
                    f"\rFinalizados: {concluidos}/{total_execucoes}",
                    end="",
                    flush=True,
                )

    tempo_total = time.perf_counter() - inicio_global
    print("\n")

    erros_post = [r for r in resultados if not r.get("ok", False)]
    validos = [r for r in resultados if r.get("ok", False)]
    timeouts = [r for r in validos if r.get("timeout")]
    terminais = [
        r for r in validos
        if not r.get("timeout") and r.get("status_id") is not None
    ]

    status_counter = Counter(
        r["status_id"] for r in terminais
    )

    aceitos = status_counter.get(3, 0)

    latencias = [
        r["total_time"]
        for r in terminais
    ]

    post_times = [
        r["post_time"]
        for r in validos
        if r.get("post_time") is not None
    ]

    throughput = aceitos / tempo_total if tempo_total else 0

    print("=" * 72)
    print("RESULTADO")
    print("=" * 72)
    print(f"Execucoes solicitadas : {total_execucoes}")
    print(f"POST aceitos pela API : {len(validos)}")
    print(f"Falhas no POST        : {len(erros_post)}")
    print(f"Timeouts de polling   : {len(timeouts)}")
    print(f"Accepted (status 3)   : {aceitos}")
    print(f"Tempo total           : {tempo_total:.3f}s")
    print(f"Throughput Accepted   : {throughput:.2f} exec/s")
    print()
    print("REQUISICOES HTTP")
    print(f"POST                  : {http_counter['POST']}")
    print(f"GET de polling        : {http_counter['GET']}")
    print(f"Total HTTP            : {http_counter['POST'] + http_counter['GET']}")

    if post_times:
        print()
        print("LATENCIA DO POST")
        print(f"Media                 : {statistics.mean(post_times):.3f}s")
        print(f"p50                   : {percentile(post_times, 50):.3f}s")
        print(f"p95                   : {percentile(post_times, 95):.3f}s")

    if latencias:
        print()
        print("LATENCIA FIM-A-FIM POR EXECUCAO")
        print(f"Media                 : {statistics.mean(latencias):.3f}s")
        print(f"Mediana / p50         : {percentile(latencias, 50):.3f}s")
        print(f"p95                   : {percentile(latencias, 95):.3f}s")
        print(f"Max                   : {max(latencias):.3f}s")

    print()
    print("STATUS TERMINAIS")
    if status_counter:
        for status_id in sorted(status_counter):
            descricao = STATUS.get(status_id, "Desconhecido")
            print(
                f"{status_id:>2} - {descricao:<30}: "
                f"{status_counter[status_id]}"
            )
    else:
        print("Nenhum status terminal recebido.")

    if erros_post:
        print()
        print("PRIMEIRAS FALHAS DE POST")
        for erro in erros_post[:5]:
            print(
                f"Aluno {erro['aluno']} | "
                f"Tentativa {erro['tentativa']} | "
                f"Caso {erro['caso']} | "
                f"{erro.get('erro')}"
            )

    if timeouts:
        print()
        print("PRIMEIROS TIMEOUTS")
        for r in timeouts[:10]:
            print(
                f"Aluno {r['aluno']} | "
                f"Tentativa {r['tentativa']} | "
                f"Caso {r['caso']} | "
                f"Token {r.get('token')}"
            )

    print("=" * 72)

    if (
        len(erros_post) == 0
        and len(timeouts) == 0
        and aceitos == total_execucoes
    ):
        print("RESULTADO FINAL: 100% das execucoes foram Accepted.")
    else:
        print("RESULTADO FINAL: houve falhas, timeouts ou status nao-Accepted.")

    print("=" * 72)


if __name__ == "__main__":
    main()

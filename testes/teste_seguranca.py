import os

paths = [
    "/var/lib/containerd",
    "/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs",
    "/dev/termination-log",
    "/etc/hosts",
]

for p in paths:
    print("\n", p)
    print("existe:", os.path.exists(p))
    print("leitura:", os.access(p, os.R_OK))
    print("escrita:", os.access(p, os.W_OK))

    if os.path.isfile(p):
        try:
            print("conteudo:", open(p).read()[:500])
        except Exception as e:
            print("leitura bloqueada:", e)
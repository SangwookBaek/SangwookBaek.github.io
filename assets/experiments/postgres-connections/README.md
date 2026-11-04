# Local connection experiment

Run on Linux ARM64 containers. These images are pinned to the measured digests.
The credentials `lab/lab` are for this isolated localhost experiment.

```sh
docker compose -p blog-connection-lab up -d --build --wait
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt
.venv/bin/python -m ipykernel install --user --name connection-lab
```

Open `experiment.ipynb`, select the `connection-lab` kernel, and run cells in order.
Start from newly restarted containers for a fresh baseline. Before and after the
direct-connection cells open 40 connections, inspect each database container from
a terminal:

```sh
docker top blog-connection-lab-postgres-1 -o pid,nlwp,args
docker exec blog-connection-lab-postgres-1 cat /sys/fs/cgroup/memory.current
docker exec blog-connection-lab-postgres-1 grep '^anon ' /sys/fs/cgroup/memory.stat
```

Process and thread counts include database background workers. The experiments
use SELECT 1 and pg_sleep, with no dataset.

The old_pod/new_pod lists model groups of held client connections; they do not
create Kubernetes pods or SQLAlchemy pools. After the run, stop the lab with:

```sh
docker compose -p blog-connection-lab stop
```

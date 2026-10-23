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
Start from newly restarted containers for a fresh baseline. The two observer
connections remain open during measurement and are excluded from application
connection counts. OS counts include database background processes and threads.
Memory values are medians of five immediate cgroup samples, not five independent
benchmark runs. The experiments use SELECT 1 and pg_sleep, with no dataset.

The old_pod/new_pod lists model groups of held client connections; they do not
create Kubernetes pods or SQLAlchemy pools. After the run, stop the lab with:

```sh
docker compose -p blog-connection-lab stop
```

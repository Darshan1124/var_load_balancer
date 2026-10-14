# Workflow: Running the Project

How to start, test and stop the project, and what happens after each command.
This file covers the current state (Phase 1): Envoy in front of two test backends, plus a script to test it live. It will grow as the control plane and the AI engine are added.

---

## 1. Prerequisites

| Tool | Check with | Needed for |
|---|---|---|
| Docker Desktop (engine running) | `docker info` | Running Envoy and the backends |
| Python 3 | `python --version` | The live test script (standard library only, nothing to install) |
| Git | `git --version` | Version control |
| Go | `go version` | Control plane (Phase 2) |
| Ollama | `ollama --version` | Optional local LLM |

**Docker Desktop must be started first.** Installing it does not start it. If `docker info` shows "failed to connect to the docker API", open Docker Desktop from the Start menu and wait for "Engine running".

**Use a freshly opened terminal after installing tools.** An already-open terminal keeps the old PATH, so you get "docker is not recognized". Close and reopen it, or run:

```powershell
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
```

---

## 2. Project files and how they connect

```
docker-compose.yml          you run this with `docker compose`
   ├── envoy                image envoyproxy/envoy, config mounted from envoy/envoy.yaml
   ├── backend-1 ─┐
   └── backend-2 ─┴── build: ./backends
                         ├── Dockerfile   builds the image
                         │     └── COPY app.py
                         └── app.py       the server code, started by the Dockerfile's CMD

simulation/send_requests.py   run by you from the terminal; sends requests to Envoy
```

| File | Triggered by | Role |
|---|---|---|
| `docker-compose.yml` | You, via `docker compose up` | Defines the three services, their settings and ports |
| `envoy/envoy.yaml` | Mounted into the Envoy container; Envoy reads it at startup | Listener, route, cluster and endpoints: how Envoy splits traffic |
| `backends/Dockerfile` | Compose (`build: ./backends`) | Packages `app.py` into an image |
| `backends/app.py` | The Dockerfile's `CMD` when a container starts | The test server; reads `NAME`, `PORT`, `DELAY_MS`, `ERROR_RATE` from the environment |
| `simulation/send_requests.py` | You, manually | Sends requests through Envoy and prints which backend answered each one |

---

## 3. Start

Run from the project root, `C:\load_balancer`, because that is where `docker-compose.yml` is:

```powershell
cd C:\load_balancer
docker compose up -d --build
```

| Part | Meaning |
|---|---|
| `up` | Create and start everything in the compose file |
| `-d` | Detached: run in the background and return the terminal |
| `--build` | Build the backend image first instead of reusing an old one |

### What happens after the command

1. Compose reads `docker-compose.yml` and finds three services: `envoy`, `backend-1` and `backend-2`.
2. The backends point to `build: ./backends`, so Compose reads `backends/Dockerfile`.
3. The Dockerfile steps run:
   - `FROM python:3.12-slim` downloads a small Python base image (first time only)
   - `WORKDIR /app` sets the working folder inside the image
   - `COPY app.py .` copies the server code into the image
   - `CMD ["python", "app.py"]` records what to run when a container starts
4. One image is built; the second backend reuses it. The Envoy image is downloaded from Docker Hub (first time only).
5. Compose creates a private network, `load_balancer_default`.
6. Compose starts the containers, backends first (`depends_on`):
   - `backend-1`: `NAME=backend-1`, your PC port 8081 maps to container port 8080
   - `backend-2`: `NAME=backend-2`, your PC port 8082 maps to container port 8080
   - `envoy`: your `envoy/envoy.yaml` is mounted at `/etc/envoy/envoy.yaml`; your PC port 8080 maps to Envoy's listener and port 9901 (local only) to its admin page
7. In each backend, `python app.py` reads `NAME` and `PORT` and starts an HTTP server on port 8080.
8. Envoy reads its config, opens its listener on 8080 and its admin interface on 9901, and finds `backend-1:8080` and `backend-2:8080` through Docker's DNS.

Both backends use port 8080 internally without clashing, because each container has its own network. The `8081`/`8082` numbers are only the ports on your PC, for testing a backend directly.

---

## 4. Verify

```powershell
docker compose ps
```
Lists the containers and their status. All three should show `Up`.

Send a request through Envoy a few times:

```powershell
curl http://localhost:8080/hello
```

The response alternates between:

```json
{"backend": "backend-1", "path": "/hello"}
{"backend": "backend-2", "path": "/hello"}
```

Test a backend directly, bypassing Envoy:

```powershell
curl http://localhost:8081/hello      # always backend-1
curl http://localhost:8082/hello      # always backend-2
curl http://localhost:8081/health     # {"status": "ok", "backend": "backend-1"}
```

`/health` skips the artificial delay and errors, so health checks stay reliable.

The Envoy admin page is at http://localhost:9901 (see section 6).

---

## 5. Live test with the script

`simulation/send_requests.py` sends requests to Envoy and prints one line per request showing which backend served it, then a summary. It needs only Python; nothing to install.

### Run it

```powershell
cd C:\load_balancer
docker compose up -d
python simulation/send_requests.py
```

### Options

| Option | Meaning | Default |
|---|---|---|
| `-n 50` | Number of requests | 20 |
| `--interval 0.5` | Seconds to wait between requests (when `--workers` is 1), handy for watching it live | 0 |
| `--workers 10` | Send this many requests in parallel | 1 |
| `--url http://localhost:8080/hello` | Address to send requests to | `http://localhost:8080/hello` |
| `--timeout 5` | Per-request timeout in seconds | 5 |

Examples:

```powershell
python simulation/send_requests.py -n 10 --interval 0.5     # watch it slowly
python simulation/send_requests.py -n 500 --workers 8       # a bigger test
```

### Reading the output

```
[  1] -> backend-1      status=200     73.9 ms
[  2] -> backend-2      status=200     23.0 ms
...
==============================================================
backend          requests   share  errors    avg ms
--------------------------------------------------------------
backend-1               9   45.0%       0      18.6
backend-2              11   55.0%       0       9.2
--------------------------------------------------------------
total 20 requests in 0.27s
```

- Each line: request number, the backend that answered, the HTTP status and the latency. Failed requests are marked `<-- FAILED`.
- The summary shows, per backend, the number of requests, its share of the traffic, the error count and the average latency.
- `UNREACHABLE` as the backend means the script could not connect to Envoy at all (the stack is not running, or the port is wrong).

### Why the split is not perfectly alternating

Envoy runs several worker threads, and each keeps its own round-robin counter. A new connection lands on whichever worker accepts it, so the combined sequence can show the same backend several times in a row. Each worker still splits its own traffic evenly, so the totals approach 50/50 as the request count grows. Compare the **shares** over a few hundred requests, not the exact order. Do not force a single worker thread; it would cap Envoy at one CPU core.

### See the problem the AI will later fix

Envoy currently does plain round robin and knows nothing about latency or errors. Make `backend-2` slow and flaky:

1. In `docker-compose.yml`, add under `backend-2`'s `environment:`:
   ```yaml
   DELAY_MS: 300
   ERROR_RATE: 0.3
   ```
2. Apply it: `docker compose up -d`
3. Run the script: `python simulation/send_requests.py -n 40`

`backend-2` shows high latency and `FAILED` lines, yet it still receives about half of the traffic. This is the baseline the later phases will improve on. Remove the two lines and run `docker compose up -d` again to go back to normal.

---

## 6. Envoy admin page and stats

Open http://localhost:9901 in a browser. It is reachable from your own PC only.

| URL | Shows |
|---|---|
| `/clusters` | Every endpoint with its request count (`rq_total`), active connections and health flag |
| `/stats?filter=cluster.backends` | All counters for the `backends` cluster, e.g. `upstream_rq_total` |
| `/config_dump` | The configuration Envoy is running with |
| `/ready` | `LIVE` when Envoy is up |

From the terminal:

```powershell
curl http://localhost:9901/clusters
curl "http://localhost:9901/stats?filter=cluster.backends.upstream_rq_total"
```

The `healthy` flag only means Envoy could resolve and connect to the endpoint. Active health checks are not configured yet (Phase 3).

---

## 7. Useful commands

| Command | What it does |
|---|---|
| `docker compose logs` | Show logs from all containers |
| `docker compose logs -f envoy` | Follow Envoy's log live; its access log prints one line per request |
| `docker compose logs -f backend-1` | Follow one backend's logs live |
| `docker compose ps` | List containers and status |
| `docker compose restart envoy` | Restart Envoy to pick up changes in `envoy/envoy.yaml` |
| `docker compose restart backend-1` | Restart one container |
| `docker compose stop backend-2` | Stop one backend, to see how Envoy reacts (there are no health checks yet, so expect failed requests until Envoy notices) |
| `docker compose start backend-2` | Start it again |
| `docker compose up -d --build` | Rebuild and restart after changing `app.py` |
| `docker compose down` | Stop and remove the containers and network |

- Envoy reads `envoy.yaml` only at startup. After editing it, run `docker compose restart envoy`. No rebuild is needed because the file is mounted, not copied.
- After changing `app.py`, you must run `up -d --build` again. The image keeps the old copy of the file until it is rebuilt.
- To check a config change before applying it:
  ```powershell
  docker run --rm -v "${PWD}\envoy\envoy.yaml:/etc/envoy/envoy.yaml:ro" envoyproxy/envoy:v1.32-latest --mode validate -c /etc/envoy/envoy.yaml
  ```
  It ends with `configuration ... OK` if the file is valid.

---

## 8. Test settings (failure injection)

`app.py` reads these environment variables. Set them under `environment:` in `docker-compose.yml`, then run `docker compose up -d`.

| Variable | Default | Effect |
|---|---|---|
| `NAME` | `backend` | Name reported in responses |
| `PORT` | `8080` | Port the server listens on inside the container |
| `DELAY_MS` | `0` | Adds this much latency to every request |
| `ERROR_RATE` | `0` | Fraction of requests (0.0 to 1.0) that return HTTP 500 |

Example: make `backend-2` slow and flaky.

```yaml
backend-2:
  environment:
    NAME: backend-2
    DELAY_MS: 300
    ERROR_RATE: 0.2
```

These settings are used in Phase 3 to simulate degraded clouds.

---

## 9. Stop

```powershell
docker compose down
```

Stops and removes the three containers and the network. The built image stays cached, so the next `up` is fast.

Docker Desktop keeps running afterwards and uses RAM. To free that, quit it from the system tray.

---

## 10. Git workflow

```powershell
git status
git add -A
git commit -m "Describe the change"
git push
```

The remote is `https://github.com/Darshan1124/var_load_balancer.git` and `main` tracks `origin/main`, so a plain `git push` works.

---

## 11. Ollama (local LLM)

Ollama is separate from Docker and the backends. It is only needed for local LLM experiments (for example the optional operator assistant in later phases). The load balancer itself does not use the GPU.

### How it behaves

- The Ollama service runs in the background and starts at login (there is a shortcut in the Windows Startup folder). While idle it uses only tens of MB of RAM and no GPU.
- A model is loaded into GPU memory (VRAM) only when you send it a request. `llama3.2:3b` uses about 2.5 GB of the 6 GB.
- After 5 minutes without requests the model unloads automatically and the VRAM is freed.
- The first request after an unload is slow (up to a minute or two) because the model is read from disk again. After that it is fast (about 67 tokens/s on the RTX 4050).

### Commands

| Command | What it does |
|---|---|
| `ollama run llama3.2:3b` | Load the model and chat. This is also how you start it again after a stop. |
| `ollama stop llama3.2:3b` | Unload the model and free the VRAM right away. The model stays on disk and the service keeps running. |
| `ollama ps` | Show which models are loaded in memory right now. |
| `ollama list` | Show the models downloaded on disk. |
| `ollama rm llama3.2:3b` | Delete the model file from disk. |
| `ollama serve` | Start the Ollama service manually, if it is not running. |

### Check GPU usage

```powershell
nvidia-smi
```

`memory.used` near 0 MiB means no model is loaded.

### If a command fails with a connection error

The Ollama service is off (for example after quitting it from the system tray). Start the Ollama app from the Start menu, or run `ollama serve` in a terminal.

### Optional settings

- `OLLAMA_KEEP_ALIVE` changes how long a model stays loaded after the last request (default 5 minutes). Use a short value such as `30s` to free the GPU sooner.
- To stop Ollama starting at login, disable it in Task Manager under Startup apps, or quit it from the system tray.

---

## 12. What comes next

| Step | Adds | Changes to this workflow |
|---|---|---|
| Phase 2 | Go xDS control plane | Envoy gets its config live from the control plane instead of a file; no restart needed to change weights |
| Phase 3 | Simulated clouds, health checks, outlier detection | Failed or slow backends are removed from rotation automatically |
| Phase 4 | Prometheus, Grafana and a heuristic scorer | Weights adapt to measured latency and errors |

Update this document whenever a step changes how the project is started or tested.

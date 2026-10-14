# Workflow: Running the Project

How to start, test and stop the project, and what happens after each command.
This file covers the current state (Phase 1, step 1: two test backends). It will grow as Envoy and the other components are added.

---

## 1. Prerequisites

| Tool | Check with | Needed for |
|---|---|---|
| Docker Desktop (engine running) | `docker info` | Running the backends (and later Envoy) |
| Git | `git --version` | Version control |
| Go | `go version` | Control plane (Phase 2) |
| Python | `python --version` | AI engine (Phase 5) |
| Ollama | `ollama --version` | Optional local LLM |

**Docker Desktop must be started first.** Installing it does not start it. If `docker info` shows "failed to connect to the docker API", open Docker Desktop from the Start menu and wait for "Engine running".

---

## 2. Project files and how they connect

```
docker-compose.yml        you run this with `docker compose`
   └── build: ./backends
         ├── Dockerfile   builds the image
         │     └── COPY app.py
         └── app.py       the server code, started by the Dockerfile's CMD
```

| File | Triggered by | Role |
|---|---|---|
| `docker-compose.yml` | You, via `docker compose up` | Defines the services, their settings and ports |
| `backends/Dockerfile` | Compose (`build: ./backends`) | Packages `app.py` into an image |
| `backends/app.py` | The Dockerfile's `CMD` when a container starts | The test server; reads `NAME`, `PORT`, `DELAY_MS`, `ERROR_RATE` from the environment |

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
| `--build` | Build the images first instead of reusing old ones |

### What happens after the command

1. Compose reads `docker-compose.yml` and finds two services: `backend-1` and `backend-2`.
2. Both point to `build: ./backends`, so Compose reads `backends/Dockerfile`.
3. The Dockerfile steps run:
   - `FROM python:3.12-slim` downloads a small Python base image (first time only)
   - `WORKDIR /app` sets the working folder inside the image
   - `COPY app.py .` copies the server code into the image
   - `CMD ["python", "app.py"]` records what to run when a container starts
4. One image is built; the second service reuses it.
5. Compose creates a private network, `load_balancer_default`.
6. Compose starts two containers from the image, each with its own `NAME`:
   - `backend-1`: `NAME=backend-1`, your PC port 8081 maps to container port 8080
   - `backend-2`: `NAME=backend-2`, your PC port 8082 maps to container port 8080
7. In each container, `python app.py` runs. It reads `NAME` and `PORT` from the environment and starts an HTTP server on port 8080.

Both servers use port 8080 internally without clashing, because each container has its own network. The `8081`/`8082` numbers are only the ports on your PC.

---

## 4. Verify

```powershell
docker compose ps
```
Lists the containers and their status. Both should show `Up`.

```powershell
curl http://localhost:8081/hello
curl http://localhost:8082/hello
curl http://localhost:8081/health
```

Expected responses:

```json
{"backend": "backend-1", "path": "/hello"}
{"backend": "backend-2", "path": "/hello"}
{"status": "ok", "backend": "backend-1"}
```

What happens on a request: your PC sends it to port 8081, Docker forwards it to port 8080 in `backend-1`, and `app.py` replies with its own name.

`/health` skips the artificial delay and errors, so health checks stay reliable.

---

## 5. Useful commands

| Command | What it does |
|---|---|
| `docker compose logs` | Show logs from all containers |
| `docker compose logs -f backend-1` | Follow one container's logs live |
| `docker compose ps` | List containers and status |
| `docker compose restart backend-1` | Restart one container |
| `docker compose up -d --build` | Rebuild and restart after changing `app.py` |
| `docker compose down` | Stop and remove the containers and network |

After changing `app.py`, you must run `up -d --build` again. The image keeps the old copy of the file until it is rebuilt.

---

## 6. Test settings (failure injection)

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

## 7. Stop

```powershell
docker compose down
```

Stops and removes both containers and the network. The built image stays cached, so the next `up` is fast.

---

## 8. Git workflow

```powershell
git status
git add -A
git commit -m "Describe the change"
git push
```

The remote is `https://github.com/Darshan1124/var_load_balancer.git` and `main` tracks `origin/main`, so a plain `git push` works.

---

## 9. Ollama (local LLM)

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

## 10. What comes next

| Step | Adds | Changes to this workflow |
|---|---|---|
| Phase 1, step 2 | Envoy with a static config (`envoy/envoy.yaml`) | Compose gets an `envoy` service; you send requests to Envoy's port instead of the backends directly |
| Phase 1, step 3 | Envoy admin page and stats | Open Envoy's admin port to see the traffic split and cluster health |
| Phase 2 | Go xDS control plane | Envoy gets its config live from the control plane instead of a file |

Update this document whenever a step changes how the project is started or tested.

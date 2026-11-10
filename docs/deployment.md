# Deployment

## Local

Install requirements in a virtual environment, configure .env using scripts/setup_admin.py, and launch Uvicorn from the repository root. Run frontend npm ci and npm run dev separately. The Vite proxy routes /api to localhost:8000.

Before speech use, run `python scripts/prepare_speech_model.py --model tiny --activate`. This creates a verified local checkpoint, registers its path, and selects it for STT without changing translation defaults. Larger base/small variants can be prepared with the same command. In Docker, run `docker compose run --rm backend python scripts/prepare_speech_model.py --model tiny --activate` using the persistent runtime volume, then start the services. Do not copy a Windows model path into a Linux database configuration; prepare/activate in the deployment environment.

## Container CPU hosting

Copy .env.example to .env and configure admin/encryption/origins. Run docker compose up --build. The app is available at port 8080. The backend port is internal to the Compose network. Model adapters are mounted read-only; the Hugging Face cache and database are persistent. CPU is supported without a GPU; expect slower generation and model warmup. Allow several GB of RAM plus headroom for model loading. Benchmark actual passages on your host rather than assuming real-time speech.

The default backend image installs requirements including PyTorch. Do not place a notebook, dataset, secrets, or weights in the container build context; .dockerignore excludes these. The adapter must exist before starting inference. Docker has not been presumed available on every developer machine.

## GPU hosting

Install NVIDIA drivers and NVIDIA Container Toolkit on the host. Add gpus: all to the backend service. Use a CUDA runtime image and install the matching CUDA PyTorch distribution. Verify torch.cuda.is_available() inside the container before enabling CUDA model settings. CTranslate2 GPU Whisper also has CUDA/cuDNN requirements; the default CPU Whisper avoids those.

For an 8 GB RTX 4070 Laptop, keep one backend worker. NLLB uses CUDA float16 under auto settings, Whisper uses CPU int8 by default, and the model manager permits one heavy local model resident. Switching STT/translation may add load latency. More workers would duplicate weights and exceed the intended memory budget.

## Production ingress

Terminate TLS with a trusted ingress/reverse proxy and set SECURE_COOKIES=true. Set exact ALLOWED_ORIGINS to your production hostname. Use frontend/nginx.conf for the same-origin API proxy. Microphone APIs require HTTPS outside localhost.

Set request body limits and duration timeouts at the ingress. Enforce anonymous inference rate limits and quotas. The application has a small in-process admission limit but no distributed abuse controls. Apply tighter limits to admin login; only trust forwarded client headers from your proxy. Configure CPU/memory limits and deployment monitoring.

## PostgreSQL and backups

Install psycopg[binary] and set DATABASE_URL=postgresql+psycopg://... via secret management. SQLAlchemy tables are created at startup for initial deployments. Introduce versioned migrations before changing an existing schema. Backup database plus ENCRYPTION_KEY together; encrypted credentials cannot be recovered without the key. Rotate admin credentials and revoke existing session rows during incident response.

## Readiness and warmup

/api/health verifies API liveness, reports the loading model and elapsed time, and shows active request capacity. It does not claim the AI is loaded. Use admin model tests and real short translation/speech requests for readiness checks. Before serving speech, run `python scripts/download_speech_model.py --model small` with the same `WHISPER_CACHE` setting as the backend. Mount that cache in the backend container or download the checkpoint while building your deployment image. Missing or incomplete Whisper checkpoints fail promptly without evicting the working translation model. Request-time speech downloads are disabled. Edge is an external online service with no application-provided SLA.

## Hosting limits

Static website hosting alone cannot run PyTorch/FastAPI. Deploy the backend on a Python/container host with enough memory and connect it through a same-origin reverse proxy. The prepared Docker configuration is not evidence of a completed cloud deployment. NLLB model license and intended-use limits apply independently.


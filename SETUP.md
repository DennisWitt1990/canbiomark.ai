# CanBiomark.ai — installation

Three steps: build the image, point it at a folder, start it.

Everything the application needs is inside the image — R with Seurat, SeuratDisk
and SimBu, Python, the H2O runtime, and the web interface. You supply one
folder.

---

## Requirements

| | Minimum | Recommended |
|---|---|---|
| Docker | Desktop 4.x, or Engine 24+ with the Compose plugin | current |
| Memory **given to Docker** | 16 GB | 32 GB or more |
| Free disk | 30 GB for the image + room for your data | 100 GB+ |
| CPU | 4 cores | 8+ cores |

Memory is the setting that actually matters. SimBu holds whole expression
matrices in memory and H2O reserves its heap up front. On Docker Desktop this
is not your machine's RAM — it is the limit under **Settings → Resources**, and
the default is often 8 GB, which is too little.

---

## Step 1 — Get the files and configure

```bash
# From the root of the downloaded or cloned repository:
cd docker
cp .env.example .env
```

Open `.env` and set the two values at the top:

```ini
# The folder on your machine where everything is stored.
CANBIOMARK_DATA_DIR=/Users/you/canbiomark-data

# The first administrator's password. At least 10 characters,
# with a letter and a digit. Leave empty to have one generated.
ADMIN_PASSWORD=choose-something-strong-1
```

If Docker has less than 32 GB, lower both memory values together:

```ini
H2O_MAX_MEMORY=8g
CANBIOMARK_MEMORY_LIMIT=14g
```

Never raise `H2O_MAX_MEMORY` close to `CANBIOMARK_MEMORY_LIMIT`: SimBu needs
room beside the H2O heap, and H2O reserves its heap whether it uses it or not.

## Step 2 — Build

```bash
docker compose build
```

**This takes roughly 30 to 90 minutes the first time**, almost all of it
compiling Seurat and SimBu from source at their pinned commits. Measured on an
Apple M-series laptop: 18 minutes for the R layer, about 25 minutes in total,
producing a 4.96 GB image. On slower hardware, or on x86 under emulation,
expect longer.

It happens once. Later builds reuse the cached layers, so a code change
rebuilds in well under a minute — only changing `requirements.txt` or the R
packages forces the slow layer again.

## Step 3 — Start

```bash
docker compose up -d
docker compose logs -f
```

Wait for `Application startup complete`, then open <http://localhost:8000>.

Sign in as `admin` with the password from your `.env`. If you left
`ADMIN_PASSWORD` empty, the generated one is in the log — search for it:

```bash
docker compose logs | grep -A3 "random password"
```

It is printed **once**. Copy it, sign in, and change it under *Your account*.

---

## Verifying the installation

```bash
docker compose exec canbiomark /usr/local/bin/entrypoint.sh check
```

This checks the data folder is writable, that both Python environments have the
right anndata versions, that Seurat/SeuratDisk/SimBu are in the R library, and
that Java is present. It prints `All checks passed.` when the image is sound.

The container also has a health check, so `docker compose ps` shows `healthy`
once it is serving.

---

## What lives in your folder

Everything, which means backing up that one folder backs up the installation:

```
<CANBIOMARK_DATA_DIR>/
├── canbiomark.sqlite     accounts, sessions, the audit trail
├── catalogue/            the shared datasets every user can select from
│   ├── combined_adata_<name>.h5ad
│   └── catalog_<name>.txt
├── users/<user id>/      one private workspace per account
└── _imports/             scratch space for downloads, cleared on restart
```

### Filling the catalogue

Two ways.

**Through the interface.** Sign in as an administrator, open **Datasets**,
search CELLxGENE or enter an EBI accession, and import. The file is downloaded,
you confirm which metadata column holds the cell type, and it is converted and
published automatically.

**By hand.** Drop two files into `catalogue/`:

```
combined_adata_liver.h5ad     the dataset
catalog_liver.txt             one line:  <experiment name>;<tissue label>
```

The name after `combined_adata_` and after `catalog_` must match. The `.h5ad`
must be readable by anndata 0.7.6 — files produced by the importer always are;
files written by a recent anndata are not, and the importer exists precisely to
convert them.

---

## Everyday commands

```bash
docker compose logs -f              # follow the logs
docker compose restart              # restart
docker compose down                 # stop (your data folder is untouched)
docker compose up -d --build        # rebuild after a code change
docker compose exec canbiomark shell   # a shell inside the container
```

Back up while it is stopped, or at least while nothing is running:

```bash
docker compose down
tar czf canbiomark-backup-$(date +%F).tar.gz -C "$CANBIOMARK_DATA_DIR" .
docker compose up -d
```

---

## Troubleshooting

**`/data is not writable by uid 0`**
The mounted folder belongs to another user. Either
`chmod -R u+rwX <your folder>`, or add `user: "${UID}:${GID}"` to the service
in `docker-compose.yml`.

**The container is killed during a simulation, or exits with code 137**
It ran out of memory. Raise Docker's memory limit, then raise
`CANBIOMARK_MEMORY_LIMIT`, and only then `H2O_MAX_MEMORY`.

**The AI suite fails with `Connection refused` on the second run**
This should not happen — the session manager waits for the H2O port to be
released between jobs. If it does, report it with the log; do not simply retry.

**A dataset import fails during conversion**
The log names the offending group. Most often the dataset uses a layout that
even the conversion step cannot reduce to what anndata 0.7.6 accepts. The
import stops rather than publishing a file that SimBu would fail to read later.

**`Port 8000 is already allocated`**
Set `CANBIOMARK_PORT=8080` in `.env` and `docker compose up -d` again.

**The build fails while compiling an R package**
Almost always memory. Give Docker at least 8 GB *for the build* and run
`docker compose build --no-cache` again.

---

## Running it on a server

Two things change when this is not on your laptop.

1. **Put HTTPS in front of it** and then set `SESSION_COOKIE_SECURE=1` in
   `.env`. The session cookie is `HttpOnly` and `SameSite=Lax`, but without
   this flag it is also sent over plain HTTP.
2. **Do not publish port 8000 to the world.** Bind it to the loopback interface
   and let your reverse proxy reach it:

   ```yaml
   ports:
     - "127.0.0.1:8000:8000"
   ```

A minimal nginx site:

```nginx
server {
    listen 443 ssl;
    server_name canbiomark.example.org;

    ssl_certificate     /etc/letsencrypt/live/canbiomark.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/canbiomark.example.org/privkey.pem;

    # Datasets and result archives are large, and simulations are slow.
    client_max_body_size 20G;
    proxy_read_timeout   3600s;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

The backend is started with `--proxy-headers`, so it honours
`X-Forwarded-Proto`.

---

## Known limits

- **Quotas are shown, not enforced.** The user administration screen reports
  usage against each quota, but no upload is rejected for exceeding it.
  `MAX_DATASET_DOWNLOAD_GB` caps a single import; nothing caps the total. Watch
  your disk.
- **Job state is held in memory.** Restarting during a simulation or an import
  loses that job's progress. Files already written survive, and interrupted
  downloads are cleaned up automatically at the next start.
- **One container does everything.** SimBu, H2O and the web server share the
  same memory limit, so a large simulation and a large training run at the same
  time will compete. For heavier use, run them at different times.

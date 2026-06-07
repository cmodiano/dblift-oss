# DBLift Docker Guide

This document explains how to build, test, and use DBLift Docker images.

## Quick Start

### Using Pre-built Images

```bash
# Pull the latest image from GitHub Container Registry
docker pull ghcr.io/cmodiano/dblift:latest

# Run DBLift
docker run --rm ghcr.io/cmodiano/dblift:latest --version

# Run migrations (mount your migration directory)
docker run --rm \
  -v $(pwd)/migrations:/workspace/migrations \
  -v $(pwd)/config:/workspace/config \
  ghcr.io/cmodiano/dblift:latest migrate --config /workspace/config/dblift.yaml
```

### Create an Alias

```bash
# Add to your ~/.bashrc or ~/.zshrc
alias dblift='docker run --rm -v $(pwd):/workspace ghcr.io/cmodiano/dblift:latest'

# Then use it like a native command
dblift --version
dblift migrate --config config/dblift.yaml
dblift info --config config/dblift.yaml
```

## Building Locally

### Build the Image

```bash
# Build for linux/amd64
docker build -t dblift:local .

# Test the build
docker run --rm dblift:local --version
```

### Test with Demo Repository

```bash
# Clone the demo repo
git clone https://github.com/dblift/dblift-demo.git
cd dblift-demo

# Start PostgreSQL
docker-compose up -d postgres

# Run migrations using your local image
docker run --rm \
  -v $(pwd):/workspace \
  --network dblift-demo_default \
  dblift:local migrate --config /workspace/config/dblift-postgresql.yaml
```

## GitHub Container Registry

DBLift images are automatically built and published to GitHub Container Registry (ghcr.io) when:
- Code is pushed to `main` branch
- A version tag is created (e.g., `v0.7.0-beta`)

### Available Tags

- `latest` - Latest build from main branch
- `v0.7.0-beta` - Specific version
- `0.6` - Major.minor version
- `0` - Major version
- `main-<sha>` - Specific commit

### Example

```bash
# Latest stable
docker pull ghcr.io/cmodiano/dblift:latest

# Specific version
docker pull ghcr.io/cmodiano/dblift:v0.7.0-beta

# Specific commit
docker pull ghcr.io/cmodiano/dblift:main-abc1234
```

## Image Contents

The Docker image includes:
- Python 3.11
- DBLift application code
- All Python dependencies

**Size**: ~300MB (compressed: ~120MB)

## Configuration

### Environment Variables

```bash
docker run --rm \
  -e DBLIFT_LOG_LEVEL=DEBUG \
  ghcr.io/cmodiano/dblift:latest --version
```

### Volume Mounts

```bash
# Mount migrations directory
-v $(pwd)/migrations:/workspace/migrations

# Mount config directory
-v $(pwd)/config:/workspace/config

```

## Networking

### Connecting to Host Database

```bash
# Linux: use host.docker.internal
docker run --rm \
  -v $(pwd):/workspace \
  ghcr.io/cmodiano/dblift:latest migrate --config /workspace/config/dblift.yaml

# Docker Compose: use service name
docker run --rm \
  -v $(pwd):/workspace \
  --network my-network \
  ghcr.io/cmodiano/dblift:latest migrate --config /workspace/config/dblift.yaml
```

### Example Config for Docker

```yaml
database:
  type: postgresql
  host: postgres  # Use Docker service name
  port: 5432
  database: mydb
  username: postgres
  password: postgres
  schema: public
```

## CI/CD Usage

### GitHub Actions

```yaml
- name: Run DBLift migrations
  run: |
    docker run --rm \
      -v ${{ github.workspace }}:/workspace \
      ghcr.io/cmodiano/dblift:latest migrate \
      --config /workspace/config/dblift.yaml
```

### GitLab CI

```yaml
migrate:
  image: ghcr.io/cmodiano/dblift:latest
  script:
    - dblift migrate --config config/dblift.yaml
```

## Troubleshooting

### Permission Issues

```bash
# Run as current user
docker run --rm -u $(id -u):$(id -g) \
  -v $(pwd):/workspace \
  ghcr.io/cmodiano/dblift:latest --version
```

### Connection Issues

```bash
# Enable debug logging
docker run --rm \
  -v $(pwd):/workspace \
  ghcr.io/cmodiano/dblift:latest migrate \
  --config /workspace/config/dblift.yaml \
  --log-level debug
```

## Development

### Building Development Image

```bash
# Build with cache
docker build -t dblift:dev .

# Build without cache
docker build --no-cache -t dblift:dev .

# Build with specific Python version
docker build --build-arg PYTHON_VERSION=3.10 -t dblift:dev .
```

### Interactive Shell

```bash
# Open shell in container
docker run -it --rm \
  -v $(pwd):/workspace \
  --entrypoint /bin/bash \
  dblift:dev

# Then run commands inside
python -m cli.main --version
```

## Best Practices

1. **Always specify versions** in production (avoid `:latest`)
2. **Mount volumes read-only** when possible: `-v $(pwd)/config:/workspace/config:ro`
3. **Use Docker networks** for database connectivity
4. **Set resource limits**: `--memory=512m --cpus=1`
5. **Use multi-stage builds** to keep images small

## Security

- Images are built from official Python base images
- No secrets are baked into images
- All credentials passed via config files (mounted volumes)
- Regular security updates via automated rebuilds

## Support

- Issues: https://github.com/cmodiano/dblift/issues
- Discussions: https://github.com/cmodiano/dblift/discussions
- Docker Hub: https://hub.docker.com/r/cmodiano/dblift (coming soon)

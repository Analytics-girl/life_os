# Dockerfile for Life OS FastAPI app
# Use a minimal Python image
FROM python:3.11-slim

# Install OS build tools (if any) – none needed for pure Python deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy project files (including requirements.txt)
COPY . /app

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port FastAPI will run on
EXPOSE 8000

# Run Gunicorn with Uvicorn workers (production‑ready)
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

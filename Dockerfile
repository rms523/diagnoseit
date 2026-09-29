# Use Python 3.13 slim image
FROM python:3.13-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gcc \
        g++ \
        curl \
        && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen

# Copy project files
COPY . .

# Create non-root user first
RUN adduser --disabled-password --gecos '' appuser

# Create media and data directories (data holds the generated SECRET_KEY) and set permissions
RUN mkdir -p media/medical_reports media/prescriptions data && \
    chown -R appuser:appuser /app

# Collect static files (dummy SECRET_KEY for build-time only)
RUN SECRET_KEY=build-only uv run python manage.py collectstatic --noinput \
    && chown -R appuser:appuser /app/staticfiles

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Health check (hit a lightweight API endpoint, not /admin/ which 302-redirects)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -fs http://localhost:8000/api/auth/csrf-token/ >/dev/null || exit 1

ENTRYPOINT ["/app/docker/entrypoint.sh"]

# Run the application with Gunicorn (production WSGI server)
CMD ["uv", "run", "gunicorn", "diagnoseit_backend.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "300", "--keep-alive", "300"]


FROM python:3.12-slim


ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    # Set project directory
    APP_HOME=/app

# Create working directory
WORKDIR $APP_HOME

# Install necessary system dependencies
# NOTE: xmlsec1 is ABSOLUTELY REQUIRED for pysaml2 to work
# libpq-dev and gcc are needed to compile psycopg2 (PostgreSQL)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    xmlsec1 \
    libxmlsec1-dev \
    libxmlsec1-openssl \
    libffi-dev \
    libssl-dev \
    pkg-config \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    # Ensure gunicorn and gevent are installed
    && pip install --no-cache-dir gunicorn gevent

# Copy all project code into the container
COPY . .

# Create a non-root user for security reasons 
RUN addgroup --system django \
    && adduser --system --ingroup django django \
    && chown -R django:django $APP_HOME

# Collect static files (if using whitenoise or nginx to serve them)
# RUN python manage.py collectstatic --noinput

# Change user to \'django\'
USER django

# Expose the port Gunicorn runs on
EXPOSE 8000

# Production startup command: Gunicorn with gevent workers
# Replace \'config.wsgi:application\' with your actual Django config folder name
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gevent", "config.wsgi:application"]
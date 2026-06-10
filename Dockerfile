# Dockerfile for Echelon

# Use Python 3.12 slim image
FROM mcr.microsoft.com/playwright/python:v1.49.1-noble

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV SCRAPER_MODE=avito

# Set working directory
WORKDIR /app

# Install system dependencies (already mostly present in playwright image)
RUN apt-get update && apt-get install -y --no-install-recommends \
    sqlite3 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers
# Note: Playwright browsers are already in the image, but we might need to ensure they are accessible
# RUN playwright install chromium

# Copy the rest of the application
COPY . .

# Create directory for storage
RUN mkdir -p storage/db storage/logs storage/browser

# Expose the admin dashboard port
EXPOSE 8080

# Command to run the bot and dashboard (using a small shell script or just the bot)
# In production, you might want to run them as separate containers.
# Here we'll provide a script to run both for simplicity in small deployments.
RUN echo "#!/bin/bash\npython bot.py & python admin_dashboard.py\nwait -n\nexit \$?" > /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]

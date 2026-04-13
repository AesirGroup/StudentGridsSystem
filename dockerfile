# Use Python 3.12 slim for a lightweight base image
FROM python:3.12-slim

# Prevent Python from writing .pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set the working directory
WORKDIR /app

# Install the uv package manager.
RUN pip install --no-cache-dir uv

# Copy only the dependency files first to leverage Docker layer caching.
COPY pyproject.toml uv.lock ./

# Install production dependencies using uv strictly from the lockfile.
# --no-group dev excludes development-only tools (e.g. black) from the image.
RUN uv sync --frozen --no-group dev

# Copy the rest of the Django project.
COPY . .

# Expose the port Django runs on.
EXPOSE 8000

# Run the development server using uv's virtual environment.
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
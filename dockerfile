# Use Python 3.12 as requested
FROM python:3.12-slim

# Set the working directory
WORKDIR /app

# Prevent Python from writing .pyc files and keep stdout unbuffered
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install the uv package manager
RUN pip install uv

# Copy only the dependency files first to leverage Docker layer caching
COPY pyproject.toml uv.lock ./

# Install dependencies using uv. 
# --frozen ensures it strictly uses the lockfile without trying to update packages.
RUN uv sync --frozen

# Copy the rest of your Django project (including the grids module)
COPY . .

# Expose the port Django runs on
EXPOSE 8000

# Run the development server using uv's virtual environment
CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
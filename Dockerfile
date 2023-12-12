# Use an official Python runtime as the base image
FROM python:3.8
# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
# Set the working directory in the container
COPY  . /app
WORKDIR /app
# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        default-libmysqlclient-dev python3-dev \
    && rm -rf /var/lib/apt/lists/*
# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

EXPOSE 5000
# Set the entrypoint command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
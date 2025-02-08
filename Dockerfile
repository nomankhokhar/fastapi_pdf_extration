# Use a lightweight Python base image
FROM python:3.12

# Set the working directory
WORKDIR /app

# Upgrade pip and install dependencies separately for better caching
RUN pip install --upgrade pip setuptools wheel

# Copy only the requirements file first for better caching
COPY requirements.txt .

# Installing LibGl1-mesa-dev for PaddleOCR
RUN apt-get update && apt-get install -y \
    libgl1-mesa-dev

RUN apt-get install -y poppler-utils libpoppler-cpp-dev

# Install Python dependencies using --no-cache-dir to avoid cache bloat
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application files
COPY . .

# Expose FastAPI default port
EXPOSE 8000

# Run FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

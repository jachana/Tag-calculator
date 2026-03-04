FROM python:3.12-slim

WORKDIR /app

# Copy everything needed for install
COPY pyproject.toml ./
COPY src/ src/
COPY toll_data/ toll_data/
COPY frontend/ frontend/

# Install the project and its dependencies
RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]

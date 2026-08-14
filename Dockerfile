FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY python_parte_fuerza/requirements.txt python_parte_fuerza/requirements.txt
RUN pip install --no-cache-dir -r python_parte_fuerza/requirements.txt

COPY python_parte_fuerza python_parte_fuerza
COPY ["personal del distrito.xlsx", "personal del distrito.xlsx"]

EXPOSE 8000

CMD ["python", "python_parte_fuerza/app.py"]

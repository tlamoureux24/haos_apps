FROM python:3.13-alpine
WORKDIR /runner
COPY requirements.txt .
RUN pip install --no-cache-dir --requirement requirements.txt
COPY runner.py .
ENTRYPOINT ["python", "/runner/runner.py"]

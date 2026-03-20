FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .
COPY scenarios/ scenarios/

EXPOSE 8888

ENTRYPOINT ["python", "server.py"]
CMD ["--port", "8888"]

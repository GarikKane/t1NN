FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
VOLUME /data
ENV DB_FILE=/data/monitor.db
EXPOSE 8080
CMD ["python", "monitor.py"]

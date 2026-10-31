FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/railradar ./backend/railradar
COPY web ./web
WORKDIR /app/backend
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "railradar.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]

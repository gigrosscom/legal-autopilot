FROM python:3.12-slim
WORKDIR /app/apps/bot
COPY apps/bot/ ./
RUN pip install --no-cache-dir .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "konsilier_bot.main"]

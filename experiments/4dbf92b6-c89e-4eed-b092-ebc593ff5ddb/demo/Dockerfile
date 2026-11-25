FROM python:3.12-alpine
WORKDIR /app
COPY app.py index.html ./
USER 10001
ENV PORT=8080
EXPOSE 8080
CMD ["python", "app.py"]

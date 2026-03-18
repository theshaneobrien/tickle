FROM python:3.12-slim
WORKDIR /app
COPY server.py .
COPY admin/ admin/
COPY templates/ templates/
COPY static/ static/
EXPOSE 8080 8081
VOLUME ["/app/output"]
SHELL ["/bin/bash", "-c"]
CMD ["python", "-u", "server.py"]

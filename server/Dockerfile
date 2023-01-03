FROM python:3.9-slim-buster
WORKDIR /app
COPY requirements.txt /app
RUN python3 -m pip install -r requirements.txt
COPY server.py /app
CMD ["python3", "server.py"]
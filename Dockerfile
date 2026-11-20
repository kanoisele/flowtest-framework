FROM python:3.12-slim

WORKDIR /app
COPY . /app

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

# The demo SUT binds 127.0.0.1 inside the container, so no port publishing is needed.
CMD ["flowtest", "demo", "--parallel", "3"]

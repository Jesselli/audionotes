FROM python:3.10.11-slim-buster
ARG PIP_NO_CACHE_DIR=1
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install -r requirements.txt
RUN apt update && apt install -y ffmpeg
COPY . /app
EXPOSE 8080
ENTRYPOINT [ "waitress-serve" ]
CMD [ "--call", "app:create_app" ]
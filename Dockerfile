FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir . && useradd --create-home --uid 10001 longbook \
    && mkdir -p /home/longbook/data && chown longbook:longbook /home/longbook/data
USER longbook
ENV LONGBOOK_DATA_DIR=/home/longbook/data GRADIO_ANALYTICS_ENABLED=False HF_HUB_DISABLE_TELEMETRY=1
EXPOSE 7860
CMD ["longbook", "ui", "--host", "0.0.0.0", "--no-browser"]

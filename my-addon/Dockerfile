FROM python:3.11-alpine

# 安裝 paho-mqtt 套件
RUN pip install paho-mqtt requests

COPY run.py /run.py
COPY external_bridge.conf /external_bridge.conf
CMD ["python3", "/run.py"]
CMD ["python3", "/3drp_show.py"]
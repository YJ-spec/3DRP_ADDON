FROM python:3.11-alpine

# 安裝 paho-mqtt 套件
RUN pip install paho-mqtt requests flask

COPY run.py /run.py
COPY external_bridge.conf /external_bridge.conf
CMD ["python3", "/run.py"]

COPY 3drp_show.py /3drp_show.py
CMD ["python3", "/3drp_show.py"]
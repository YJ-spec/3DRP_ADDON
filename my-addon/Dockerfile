FROM python:3.11-alpine

# 安裝 paho-mqtt 套件
RUN pip install --no-cache-dir paho-mqtt requests flask PyYAML

# 拷貝檔案
COPY config.yaml /config.yaml
COPY run.py /run.py
COPY 3drp_show.py /3drp_show.py
COPY external_bridge.conf /external_bridge.conf
COPY launcher.py /launcher.py

# 拷貝前端模板 (整個資料夾)
COPY templates/ /templates/
COPY static/ /static/

# 單一入口：同時啟兩支程式
CMD ["python3", "/launcher.py"]

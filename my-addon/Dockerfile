FROM python:3.11-alpine

# 安裝 paho-mqtt 套件
RUN pip install paho-mqtt requests flask

# 拷貝檔案
COPY run.py /run.py
COPY 3drp_show.py /3drp_show.py
COPY external_bridge.conf /external_bridge.conf
COPY launcher.py /launcher.py

# 拷貝前端模板 (整個資料夾)
COPY templates/ /templates/

# 單一入口：同時啟兩支程式
CMD ["python3", "/launcher.py"]

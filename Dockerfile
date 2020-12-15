# sensor_monitor
# 202012151337  

FROM python:3
ENV PIP_NO_CACHE_DIR=1

RUN useradd -m -r -u 1000 user && \
    chown user /

USER user

# for pip
ENV PATH $PATH:/home/user/.local/bin

RUN pip3 install -U \
    pip \
    setuptools \
    wheel

COPY requirements.txt ./
RUN pip3 install -r requirements.txt

STOPSIGNAL SIGINT

CMD [ "python", "/home/user/sensor_monitor/sensor_monitor.py" ]


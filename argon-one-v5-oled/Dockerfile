ARG BUILD_FROM
FROM $BUILD_FROM

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apk add --no-cache \
    python3 \
    py3-pip \
    i2c-tools \
    bash \
    py3-pillow

COPY requirements.txt /tmp/
RUN pip3 install --no-cache-dir -r /tmp/requirements.txt
RUN pip3 install --no-cache-dir --no-deps luma.core luma.oled

COPY run.sh /
COPY argon_oled.py /
COPY system_info.py /
COPY supervisor_api.py /
COPY home_context.py /
COPY interruptions.py /
COPY visual_modes.py /
COPY screens.py /
COPY faults.py /
COPY logo.png /

RUN chmod a+x /run.sh

CMD [ "/run.sh" ]
